"""Haalt actueel nieuws, koersen en weer op en schrijft data.json voor de teletekst-app."""
import json, re, html, sys, os
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weetjes import WEETJES

UA = {"User-Agent": "Mozilla/5.0 (ElenetTeletekst)"}
OUT = os.environ.get("OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "data.json")
MAX_PER_SECTION = 80  # artikels op X10..X89


def get(url, timeout=20, tries=3):
    """Haalt een URL op; bij een time-out of netwerkfout nog twee keer opnieuw proberen."""
    import time
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError:
            raise  # 404 en dergelijke: opnieuw proberen helpt niet
        except Exception:
            if n == tries - 1:
                raise
            time.sleep(2 * (n + 1))


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def parse_feed(url, source):
    """Leest Atom of RSS. Geeft items met titel, samenvatting, tijd, link en tags."""
    root = ET.fromstring(get(url))
    items = []
    atom = "{http://www.w3.org/2005/Atom}"
    if root.tag == atom + "feed":
        for e in root.findall(atom + "entry"):
            link = ""
            for l in e.findall(atom + "link"):
                if l.get("rel") in (None, "alternate"):
                    link = l.get("href")
            tags = [clean(t.text) for t in e if t.tag.endswith("nstag") and t.text]
            tags += [c.get("term") for c in e.findall(atom + "category") if c.get("term")]
            pub = e.findtext(atom + "published") or e.findtext(atom + "updated")
            items.append(dict(t=clean(e.findtext(atom + "title")), s=clean(e.findtext(atom + "summary") or e.findtext(atom + "content")),
                              time=pub, url=link, tags=tags, src=source))
    else:
        for e in root.iter("item"):
            pub = e.findtext("pubDate")
            try:
                pub = iso(parsedate_to_datetime(pub))
            except Exception:
                pass
            items.append(dict(t=clean(e.findtext("title")), s=clean(e.findtext("description")), time=pub,
                              url=e.findtext("link") or "", tags=[clean(c.text) for c in e.findall("category") if c.text], src=source))
    return [i for i in items if i["t"]]


WORLD = {"Europa", "Wereld", "Europese Unie", "Verenigd Koninkrijk", "Verenigde Staten", "Noord-Amerika", "Zuid-Amerika", "Latijns-Amerika",
         "Duitsland", "Frankrijk", "Nederland", "Midden-Oosten", "Azië", "Afrika", "Oceanië", "Rusland", "Oekraïne", "China", "Israël",
         "Gaza", "Iran", "India", "Japan", "Italië", "Spanje", "Turkije", "Defensie", "Buitenland"}
FIN = {"Economie", "Energie", "Financiën", "Beurs", "Werk"}
TECH = {"Technologie & Wetenschap", "Ruimtevaart", "Artificiële intelligentie", "Milieu & Klimaat", "Gezondheid", "Wetenschap", "Natuur"}
CULT = {"Cultuur & Media", "Muziek", "Films & Series", "Cultuur", "Media", "Boeken", "Kunst", "Lifestyle"}
SPORT = {"Sport"}


# Trefwoorden in categorieën of in het pad van de link bepalen de sectie bij gemengde feeds
KEYS = [
    ("sport", ("sport", "voetbal", "wielrennen", "tennis", "formule-1", "football", "soccer", "cycling", "olympics")),
    ("fin", ("economie", "geld", "beurs", "markten", "markets", "financ", "ondernemen", "business", "money", "economy", "investing", "energie")),
    ("tech", ("tech", "wetenschap", "science", "technology", "ruimtevaart", "artificiele-intelligentie", "klimaat", "climate", "gezondheid", "health")),
    ("cultuur", ("cultuur", "muziek", "film", "media", "entertainment", "showbizz", "boeken", "culture", "sterren", "celebrity", "tv-en-media")),
    ("wereld", ("buitenland", "wereld", "world", "internationaal", "europa", "europe", "international", "middle-east", "us-news")),
]


def classify(tags, url="", default="be"):
    t = set(tags)
    if t & SPORT: return "sport"
    if t & FIN: return "fin"
    if t & TECH: return "tech"
    if t & CULT: return "cultuur"
    if t & WORLD: return "wereld"
    words = [x.lower() for x in tags] + urllib.parse.urlparse(url or "").path.lower().split("/")[:4]
    for sec, keys in KEYS:
        if any(k == w or (len(k) > 5 and k in w) for w in words for k in keys):
            return sec
    return default


def norm_time(s):
    if not s:
        return None
    try:
        return iso(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except Exception:
        try:
            return iso(parsedate_to_datetime(s))
        except Exception:
            return None


YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^BFX,^STOXX50E,^GSPC,^IXIC,ABI.BR,KBC.BR,UCB.BR,ARGX.BR,ASML.AS,NVDA,AAPL,MSFT&region=US&lang=en-US"
# (url, bron, sectie, vast)  vast=True: altijd die sectie; False: trefwoorden kiezen, met de sectie als standaard
FEEDS = [
    # België
    ("https://www.vrt.be/vrtnws/nl.rss.headlines.xml", "VRT NWS", "be", False),
    ("https://www.vrt.be/vrtnws/nl.rss.articles.xml", "VRT NWS", "be", False),
    ("https://www.hln.be/binnenland/rss.xml", "HLN", "be", True),
    ("https://www.hln.be/nieuws/rss.xml", "HLN", "be", False),
    ("https://www.demorgen.be/nieuws/rss.xml", "De Morgen", "be", False),
    ("https://www.nieuwsblad.be/rss", "Nieuwsblad", "be", False),
    ("https://www.standaard.be/rss", "De Standaard", "be", False),
    ("https://www.gva.be/rss", "GVA", "be", False),
    ("https://www.hbvl.be/rss", "HBVL", "be", False),
    ("https://www.knack.be/feed/", "Knack", "be", False),
    ("https://www.bruzz.be/rss.xml", "Bruzz", "be", False),
    # Wereld
    ("https://www.hln.be/buitenland/rss.xml", "HLN", "wereld", True),
    ("https://feeds.nos.nl/nosnieuwsbuitenland", "NOS", "wereld", True),
    ("https://www.nu.nl/rss/Buitenland", "NU.nl", "wereld", True),
    ("http://rss.cnn.com/rss/edition_world.rss", "CNN", "wereld", True),
    ("http://rss.cnn.com/rss/edition.rss", "CNN", "wereld", False),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC", "wereld", True),
    ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", "wereld", True),
    ("https://www.theguardian.com/world/rss", "The Guardian", "wereld", True),
    ("https://rss.dw.com/rdf/rss-en-all", "DW", "wereld", False),
    ("https://www.euronews.com/rss", "Euronews", "wereld", False),
    ("https://www.france24.com/en/rss", "France 24", "wereld", True),
    # Financieel
    ("https://www.tijd.be/rss/nieuws.xml", "De Tijd", "fin", True),
    ("https://www.tijd.be/rss/ondernemen.xml", "De Tijd", "fin", True),
    ("https://www.tijd.be/rss/politiek.xml", "De Tijd", "fin", True),
    ("https://www.tijd.be/rss/markten_live.xml", "De Tijd", "fin", True),
    ("https://kanaalz.knack.be/nieuws/feed/", "Kanaal Z", "fin", True),
    ("https://trends.knack.be/feed/", "Trends", "fin", True),
    ("https://www.lecho.be/rss/actualite.xml", "L'Echo", "fin", True),
    ("https://feeds.nos.nl/nosnieuwseconomie", "NOS", "fin", True),
    ("https://www.nu.nl/rss/Economie", "NU.nl", "fin", True),
    ("https://fd.nl/?rss", "FD", "fin", True),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", "fin", True),
    ("https://www.cnbc.com/id/15839069/device/rss/rss.html", "CNBC", "fin", True),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC", "fin", True),
    ("http://rss.cnn.com/rss/money_news_international.rss", "CNN Business", "fin", True),
    ("https://feeds.content.dowjones.io/public/rss/mw_topstories", "MarketWatch", "fin", True),
    ("https://nl.investing.com/rss/news.rss", "Investing.com", "fin", True),
    ("https://www.investing.com/rss/news.rss", "Investing.com", "fin", True),
    ("https://www.theguardian.com/business/rss", "The Guardian", "fin", True),
    # Sport
    ("https://sporza.be/nl.rss.xml", "Sporza", "sport", True),
    ("https://www.hln.be/sport/rss.xml", "HLN", "sport", True),
    ("https://feeds.nos.nl/nossportalgemeen", "NOS", "sport", True),
    ("https://www.nu.nl/rss/Sport", "NU.nl", "sport", True),
    ("https://www.voetbalkrant.com/rss", "Voetbalkrant", "sport", True),
    ("https://www.voetbalprimeur.be/rss/", "Voetbalprimeur", "sport", True),
    ("https://www.wielerflits.be/feed/", "WielerFlits", "sport", True),
    ("http://rss.cnn.com/rss/edition_sport.rss", "CNN", "sport", True),
    # Wetenschap & tech
    ("https://feeds.nos.nl/nosnieuwstech", "NOS", "tech", True),
    ("https://www.nu.nl/rss/Tech", "NU.nl", "tech", True),
    ("https://www.nu.nl/rss/Wetenschap", "NU.nl", "tech", True),
    ("https://feeds.feedburner.com/tweakers/mixed", "Tweakers", "tech", True),
    ("https://datanews.knack.be/feed/", "Data News", "tech", True),
    ("http://rss.cnn.com/rss/edition_technology.rss", "CNN", "tech", True),
    ("https://www.cnbc.com/id/19854910/device/rss/rss.html", "CNBC", "tech", True),
    # Cultuur & media
    ("https://feeds.nos.nl/nosnieuwscultuurenmedia", "NOS", "cultuur", True),
    ("https://www.nu.nl/rss/Media-en-cultuur", "NU.nl", "cultuur", True),
    ("https://focus.knack.be/feed/", "Focus Knack", "cultuur", True),
    # Klimaat (vaste feeds; daarnaast komen klimaatberichten uit alle andere bronnen via THEMES)
    ("https://www.theguardian.com/environment/climate-crisis/rss", "The Guardian", "klimaat", True),
    ("https://www.nu.nl/rss/klimaat", "NU.nl", "klimaat", True),
    ("https://insideclimatenews.org/feed/", "Inside Climate News", "klimaat", True),
    ("https://grist.org/feed/", "Grist", "klimaat", True),
    ("https://news.un.org/feed/subscribe/en/news/topic/climate-change/feed/rss.xml", "VN Nieuws", "klimaat", True),
    ("https://www.theguardian.com/environment/rss", "The Guardian", "tech", True),
    ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "BBC", "tech", True),
    ("https://www.newscientist.nl/feed/", "New Scientist", "tech", True),
    # Oorlog & brandhaarden (idem)
    ("https://www.crisisgroup.org/rss", "Crisis Group", "oorlog", True),
    ("https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml", "Defense News", "oorlog", True),
    # Macro-economie
    ("https://www.ft.com/global-economy?format=rss", "Financial Times", "macro", True),
    ("https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC", "macro", True),
    ("https://www.theguardian.com/business/economics/rss", "The Guardian", "macro", True),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve", "macro", True),
    ("https://www.ecb.europa.eu/rss/press.html", "ECB", "macro", True),
    ("https://www.economist.com/finance-and-economics/rss.xml", "The Economist", "macro", True),
    ("https://www.investing.com/rss/news_14.rss", "Investing.com", "macro", True),
    ("https://nl.investing.com/rss/news_14.rss", "Investing.com", "macro", True),
    # Verenigde Staten
    ("http://rss.cnn.com/rss/cnn_us.rss", "CNN", "vs", True),
    ("https://rss.nytimes.com/services/xml/rss/nyt/US.xml", "New York Times", "vs", True),
    ("https://feeds.npr.org/1001/rss.xml", "NPR", "vs", True),
    ("https://rss.politico.com/politics-news.xml", "Politico", "vs", True),
    ("https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "BBC", "vs", True),
    ("https://www.theguardian.com/us-news/rss", "The Guardian", "vs", True),
    # China & Azië
    ("https://www.scmp.com/rss/4/feed", "South China Morning Post", "china", True),
    ("https://www.scmp.com/rss/318421/feed", "South China Morning Post", "china", True),
    ("https://www.scmp.com/rss/3/feed", "South China Morning Post", "china", True),
    ("https://www.theguardian.com/world/china/rss", "The Guardian", "china", True),
    ("https://feeds.bbci.co.uk/news/world/asia/rss.xml", "BBC", "china", True),
    ("https://asia.nikkei.com/rss/feed/nar", "Nikkei Asia", "china", True),
    ("https://thediplomat.com/feed/", "The Diplomat", "china", True),
    ("https://rss.nytimes.com/services/xml/rss/nyt/AsiaPacific.xml", "New York Times", "china", True),
    # AI
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch", "ai", True),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge", "ai", True),
    ("https://www.technologyreview.com/topic/artificial-intelligence/feed", "MIT Technology Review", "ai", True),
    ("https://arstechnica.com/ai/feed/", "Ars Technica", "ai", True),
    ("https://www.wired.com/feed/tag/ai/latest/rss", "Wired", "ai", True),
    # Extra tech
    ("https://www.theverge.com/rss/index.xml", "The Verge", "tech", True),
    ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica", "tech", True),
    ("https://techcrunch.com/feed/", "TechCrunch", "tech", True),
    ("https://www.engadget.com/rss.xml", "Engadget", "tech", True),
    ("https://www.bright.nl/rss", "Bright", "tech", True),
]
# Thema's: berichten uit België, wereld, financieel en tech die over deze onderwerpen gaan, komen (ook) in het thema
THEMES = {
    "oorlog": re.compile(r"\b(oorlog\w*|war|wars|invasie|invasion|bombardement\w*|bombing\w*|airstrikes?|luchtaanval\w*|raketaanval\w*|missiles?"
                         r"|drone-?aanval\w*|staakt-het-vuren|wapenstilstand|ceasefire|gijzelaar\w*|hostages?|troepen|troops|militair\w*|military"
                         r"|leger|army|soldaten|soldiers|navo|nato|oekraïn\w*|ukrain\w*|kyiv|kiev|gaza\w*|hamas|hezbollah|houthi\w*|jemen|yemen"
                         r"|soedan\w*|sudan\w*|syri\w*|rebellen|rebels|milities|militia\w*|genocide|frontlinie|frontline|gevechten|fighting|m23"
                         r"|taliban|jihadist\w*|beschieting\w*|shelling|kernwapen\w*|nuclear weapons?)\b", re.I),
    "klimaat": re.compile(r"\b(klimaat\w*|climate|opwarming|global warming|co2|uitstoot|emissies|emissions|broeikas\w*|greenhouse|hittegolf\w*"
                          r"|heatwaves?|droogte|droughts?|overstroming\w*|floods?|flooding|bosbrand\w*|wildfires?|orkaan|orkanen|hurricanes?"
                          r"|typhoons?|gletsjer\w*|glaciers?|zeespiegel|sea levels?|poolijs|arctic|antarcti\w*|biodiversiteit|biodiversity"
                          r"|ontbossing|deforestation|hernieuwbare|renewables?|zonne-?energie|windmolen\w*|windturbine\w*|windparken|wind farms?"
                          r"|fossiele|fossil fuels?|steenkool|cop\d\d|el niño|luchtvervuiling|air pollution|stikstof|energietransitie|natuurramp\w*)\b", re.I),
}
THEMES_TITLE = {
    "vs": re.compile(r"\b(Trump|Biden|Vance|Witte Huis|White House|Washington|Congres|Congress|Senaat|Senate|Republikein\w*|Republican\w*"
                     r"|Pentagon|Amerikaans\w*|Verenigde Staten|United States|U\.S\.|VS|USA|FBI|CIA|Wall Street|New York|Californi\w*|Texas)\b"),
    "china": re.compile(r"\b(China|Chinese?|Chinees|Chinezen|Beijing|Peking|Xi( Jinping)?|Taiwan\w*|Hongkong|Hong Kong|Shanghai|Shenzhen"
                        r"|Tibet\w*|Oeigoer\w*|Uyghur\w*|Huawei|BYD|Alibaba|Tencent|Japan\w*|Tokio|Tokyo|Korea\w*|Seoul|Pyongyang"
                        r"|Filipijn\w*|Philippines?|Vietnam\w*|Indonesi\w*|Asia\w*|Azi[ëe]\w*)\b"),
    "ai": re.compile(r"\b(AI|A\.I\.|GenAI|ChatGPT|OpenAI|Anthropic|Claude|Gemini|Copilot|LLMs?|[Cc]hatbots?|DeepSeek|Mistral AI|deepfakes?"
                     r"|(?i:artifici[ëe]le intelligentie|kunstmatige intelligentie|artificial intelligence|machine learning|taalmodel\w*))\b"),
}
THEMES_TITLE["macro"] = re.compile(
    r"(?i:\b(inflatie\w*|inflation\w*|rentes?|rentevoet\w*|renteverlaging\w*|renteverhoging\w*|interest rates?|rate (cut|hike)s?|ECB|Fed|Federal Reserve"
    r"|centrale bank\w*|central banks?|Lagarde|Powell|bbp|gdp|economische groei|economic growth|economie|economy|recessie|recession"
    r"|werkloosheid|unemployment|jobs report|payrolls|consumentenvertrouwen|consumer (confidence|sentiment)|PMI|CPI|koopkracht"
    r"|staatsschuld|begrotingstekort|budget deficit|obligatie\w*|bond yields?|treasur(y|ies)|handelsoorlog|trade war|tariffs?|importheffing\w*"
    r"|invoerheffing\w*|olieprijs\w*|oil prices?|OPEC\+?|Eurostat|IMF|Wereldbank|World Bank|Nationale Bank|Planbureau)\b)")
THEME_FROM = {"be", "wereld", "fin", "tech"}
THEME_NAMES = ("oorlog", "klimaat", "vs", "china", "ai", "macro")


def theme_of(it):
    """Alle thema's waar een bericht bij hoort (trefwoorden)."""
    out = [name for name, rx in THEMES.items()
           if rx.search(it["t"]) or len({m.lower() for m in rx.findall(it["s"] or "")}) >= 2]
    out += [name for name, rx in THEMES_TITLE.items() if rx.search(it["t"])]
    return out


THEME_MODEL = os.environ.get("THEMA_MODEL", "claude-opus-5-5")
THEME_PROMPT = """Je deelt nieuwskoppen in voor zes themapagina's van een teletekstdienst.

oorlog: gewapende conflicten en brandhaarden in de wereld. Oorlogen, militaire aanvallen of escalaties, staakt-het-vuren
en vredesonderhandelingen, terreuraanslagen, opstanden en gewapende groepen, militaire spanningen tussen landen,
defensie en wapenleveringen die met zo'n conflict te maken hebben, en humanitaire gevolgen ervan.
Niet: sport, films, games, boeken, historische herdenkingen zonder actueel conflict, beeldspraak ("prijzenoorlog").

klimaat: klimaatverandering en het milieu. Opwarming, uitstoot en klimaatbeleid, extreem weer en natuurrampen,
energietransitie (hernieuwbare energie, fossiele brandstoffen in klimaatcontext), biodiversiteit, vervuiling, natuurbehoud.
Niet: gewone weerberichten, energieprijzen zonder klimaat- of transitiehoek, gewone bedrijfsresultaten.

vs: nieuws dat vooral over de Verenigde Staten gaat: Amerikaanse politiek, beleid, economie, samenleving, of
beslissingen van de Amerikaanse regering die elders gevolgen hebben. Niet: een Amerikaans bedrijf dat enkel terloops vermeld wordt.

china: nieuws dat vooral over China of de rest van Azië gaat: politiek, economie, technologie, samenleving,
Taiwan, Hongkong, Japan, Korea, Zuidoost-Azië, India.

ai: artificiële intelligentie: AI-modellen en -bedrijven, chatbots, AI-regelgeving, AI-chips en datacenters voor AI,
gevolgen van AI voor werk en samenleving, deepfakes. Niet: gewone software of gadgets zonder AI-hoek.

macro: macro-economie: rente en centrale banken (ECB, Fed), inflatie, groei en bbp, werkloosheid, consumenten- en
producentenvertrouwen, overheidsfinanciën en obligatierentes, handel en invoerheffingen, olieprijs en grondstoffen als
economische factor. Niet: nieuws over één bedrijf (resultaten, overnames), tenzij het de hele economie raakt.

Een kop mag bij meerdere thema's horen als hij echt over beide gaat (bv. Amerikaanse chipsancties tegen China: vs en china,
en ai als het over AI-chips gaat). De meeste koppen horen bij geen enkel thema. Geef per thema de nummers van de koppen."""


def ai_themes(items):
    """Laat Claude bepalen welke berichten bij welk thema horen. Geeft None terug als dat niet lukt."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not items:
        return None
    try:
        import anthropic
    except ImportError:
        print("anthropic-pakket ontbreekt, thema's via trefwoorden", file=sys.stderr)
        return None
    lines = "\n".join(f"{i}: {it['t'][:160]}" for i, it in enumerate(items))
    try:
        response = anthropic.Anthropic().messages.create(
            model=THEME_MODEL,
            max_tokens=16000,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {t: {"type": "array", "items": {"type": "integer"}} for t in THEME_NAMES},
                    "required": list(THEME_NAMES),
                    "additionalProperties": False}},
            },
            system=THEME_PROMPT,
            messages=[{"role": "user", "content": lines}],
        )
    except anthropic.APIStatusError as e:
        print(f"Claude-fout {e.status_code}: {e.message}", file=sys.stderr)
        return None
    except anthropic.APIConnectionError as e:
        print("Claude onbereikbaar:", e, file=sys.stderr)
        return None
    if response.stop_reason != "end_turn":
        print("Claude stopte met", response.stop_reason, file=sys.stderr)
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text)
    out = {}
    for theme in THEME_NAMES:
        for i in data[theme]:
            if 0 <= i < len(items) and theme not in out.setdefault(i, []):
                out[i].append(theme)
    u = response.usage
    print(f"thema's via {THEME_MODEL}: {len(items)} koppen, " + ", ".join(f"{t} {len(data[t])}" for t in THEME_NAMES) +
          f", tokens in {u.input_tokens} uit {u.output_tokens}")
    return out


# Begint de kop hiermee, dan is het geen nieuwsbericht (liveblog, video, quiz, deals, nieuwsbrief ...)
JUNK = re.compile(r"^(here.?s the latest|here.?s (why|how|what)\b|live[: ]|liveblog|live updates|watch[: ]|video[: ]|podcast|listen[: ]"
                  r"|kijk[: ]|luister[: ]|the morning|the evening|briefing|newsletter|quiz|crossword|puzzle|horoscope|deals?\b|the best .* deals"
                  r"|[ée]dito\b|editorial\b|the guardian view)"
                  # ... of ergens in de kop: lezersbrieven en klikaas over beleggen
                  r"|\| ?letters$|\bhistory says\b", re.I)
# Opinie, columns en gesponsorde inhoud (op basis van de link) en klikaas over beleggen (op basis van de titel)
OPINION_URL = re.compile(r"/(opinion|opinions|commentisfree|opinie|columns?|blogs?|sponsored|partner|advertorial|brandstudio)/", re.I)
CLICKBAIT = re.compile(r"(^opinie\b|^column\b|^commentaar\b|^lezersbrief|^brief:|gesponsord|advertorial|in samenwerking met|"
                       r"\bstocks? to buy\b|\bshould you buy\b|\bbuy (now|today|and hold)\b|\bmillionaire\b|passive income|"
                       r"\bbest .{0,30}(stocks?|shares|etfs?)\b|\bmotley fool\b|\b(could|will) (soar|skyrocket|double)\b|\bretire (early|rich)\b)", re.I)
STOP = set("de het een en van in op te voor met is dat die niet aan om bij als ook door over naar uit tot zijn wordt worden heeft"
           " the a an and of to in on for with is are was were by at from as that this it its after over new says".split())


def words(t):
    return {w for w in re.findall(r"[a-zà-ÿ0-9]+", t.lower()) if len(w) > 3 and w not in STOP}


def merge_same_story(items):
    """Hetzelfde verhaal van meerdere bronnen wordt één bericht (met de beste samenvatting) + 'ook bij'."""
    groups = []
    for it in items:
        w = words(it["t"])
        for g in groups:
            if w and len(w & g["w"]) / len(w | g["w"]) >= 0.45:
                g["items"].append(it)
                g["w"] |= w
                break
        else:
            groups.append({"w": set(w), "items": [it]})
    out = []
    for g in groups:
        best = max(g["items"], key=lambda i: (len(i["s"] or "") >= 200, PRIORITY.get(i["src"], 0), len(i["s"] or "")))
        also = []
        for i in g["items"]:
            if i["src"] != best["src"] and i["src"] not in also:
                also.append(i["src"])
        best = dict(best)
        if also:
            best["also"] = also[:4]
        best["time"] = max((i["time"] or "") for i in g["items"]) or best["time"]
        out.append(best)
    return out


PER_SOURCE = 14  # max. berichten per bron per sectie, zodat geen enkele site alles overneemt
PRIORITY = {"VRT NWS": 9, "CNN": 8, "CNBC": 8, "Kanaal Z": 8, "Yahoo Finance": 8, "Al Jazeera": 7, "CNN Business": 7, "Sporza": 7, "De Tijd": 6,
            "South China Morning Post": 7, "TechCrunch": 6, "MIT Technology Review": 6,
            "Financial Times": 8, "ECB": 8, "Federal Reserve": 8, "The Economist": 7}


def news():
    sec = {k: [] for k in ("be", "wereld", "fin", "sport", "tech", "cultuur") + THEME_NAMES}
    seen = {"main": set(), **{t: set() for t in THEME_NAMES}}
    count = {}

    def add(k, it):
        if JUNK.search(it["t"]) or CLICKBAIT.search(it["t"]) or OPINION_URL.search(it["url"] or "") or len(it["t"]) < 25:
            return  # nietszeggende koppen, opinie, klikaas en gesponsorde inhoud: enkel degelijk nieuws
        it = dict(it)
        group = seen.get(k, seen["main"])
        key = re.sub(r"\W+", "", it["t"].lower())[:50]
        if key in group or count.get((k, it["src"]), 0) >= PER_SOURCE: return
        group.add(key)
        count[(k, it["src"])] = count.get((k, it["src"]), 0) + 1
        s = it["s"]
        if len(s) > 650:
            cut = s[:650]
            s = cut[:cut.rfind(". ") + 1] if ". " in cut else cut.rsplit(" ", 1)[0] + "..."
        it["s"] = s
        it["time"] = norm_time(it["time"])
        sec[k].append({x: it[x] for x in ("t", "s", "time", "url", "src")})

    def fetch(f):
        try:
            return f, parse_feed(f[0], f[1])
        except Exception as e:
            print("feed mislukt:", f[0], e, file=sys.stderr)
            return f, []

    with ThreadPoolExecutor(16) as ex:
        results = list(ex.map(fetch, FEEDS))
    cands, cand_keys = [], set()
    for (url, src, default, fixed), items in results:  # volgorde van FEEDS: eerste bron wint bij dubbels
        for it in items:
            k = default if fixed else classify(it["tags"], it["url"], default)
            add(k, it)
            key = re.sub(r"\W+", "", it["t"].lower())[:50]
            if k in THEME_FROM and key not in cand_keys:
                cand_keys.add(key)
                cands.append(it)
    themes = ai_themes(cands[:700])
    if themes is None:  # geen sleutel of fout: trefwoorden
        themes = {i: th for i, it in enumerate(cands) if (th := theme_of(it))}
    for i, ths in themes.items():
        for th in ths:
            add(th, cands[i])
    for k in sec:
        sec[k] = merge_same_story(sorted(sec[k], key=lambda i: i["time"] or "", reverse=True))
        # Om beurten per bron kiezen, zodat elke site aan bod komt; berichten met een echte samenvatting eerst,
        # daarna op tijd sorteren. Verhalen die meerdere bronnen brengen, krijgen voorrang.
        by_src = {}
        for it in sorted(sec[k], key=lambda i: (len(i.get("also", [])) > 0, len(i["s"] or "") >= 120, i["time"] or ""), reverse=True):
            by_src.setdefault(it["src"], []).append(it)
        order = sorted(by_src, key=lambda s: -PRIORITY.get(s, 0))
        picked = []
        while len(picked) < MAX_PER_SECTION and any(by_src.values()):
            for s in order:
                if by_src[s] and len(picked) < MAX_PER_SECTION:
                    picked.append(by_src[s].pop(0))
        picked.sort(key=lambda i: i["time"] or "", reverse=True)
        sec[k] = picked
    return sec


QUOTES = [
    ("idx", "BEURSINDEXEN", [("^BFX", "BEL 20"), ("^AEX", "AEX"), ("^FCHI", "CAC 40"), ("^GDAXI", "DAX"), ("^STOXX50E", "Euro Stoxx 50"),
                             ("^FTSE", "FTSE 100"), ("^DJI", "Dow Jones"), ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^N225", "Nikkei 225")]),
    ("bel20", "BEL 20  AANDELEN", [("ABI.BR", "AB InBev"), ("ACKB.BR", "Ackermans & vH"), ("AED.BR", "Aedifica"), ("AGS.BR", "Ageas"),
                                  ("ARGX.BR", "argenx"), ("AZE.BR", "Azelis"), ("BEKB.BR", "Bekaert"),
                                  ("DIE.BR", "D'Ieteren"), ("ELI.BR", "Elia"), ("GBLB.BR", "GBL"), ("KBC.BR", "KBC"), ("LOTB.BR", "Lotus Bakeries"),
                                  ("MELE.BR", "Melexis"), ("PROX.BR", "Proximus"), ("SOF.BR", "Sofina"), ("SOLB.BR", "Solvay"),
                                  ("SYENS.BR", "Syensqo"), ("UCB.BR", "UCB"), ("UMI.BR", "Umicore"), ("WDP.BR", "WDP")]),
    ("eu", "EUROPA  AANDELEN", [("ASML.AS", "ASML"), ("SAP.DE", "SAP"), ("NOVO-B.CO", "Novo Nordisk"), ("MC.PA", "LVMH"), ("NESN.SW", "Nestle"),
                                ("SIE.DE", "Siemens"), ("TTE.PA", "TotalEnergies"), ("SHELL.AS", "Shell"), ("INGA.AS", "ING"), ("AD.AS", "Ahold Delhaize")]),
    ("us", "VS  AANDELEN", [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"), ("AMZN", "Amazon"), ("GOOGL", "Alphabet"),
                            ("META", "Meta"), ("TSLA", "Tesla"), ("BRK-B", "Berkshire B"), ("JPM", "JPMorgan"), ("NFLX", "Netflix")]),
    ("fx", "VALUTA & GRONDSTOFFEN", [("EURUSD=X", "EUR/USD"), ("EURGBP=X", "EUR/GBP"), ("EURCHF=X", "EUR/CHF"), ("EURJPY=X", "EUR/JPY"),
                                     ("GC=F", "Goud $/oz"), ("SI=F", "Zilver $/oz"), ("BZ=F", "Brent $/vat"), ("NG=F", "Aardgas $")]),
    ("crypto", "CRYPTO", [("BTC-EUR", "Bitcoin"), ("ETH-EUR", "Ethereum"), ("SOL-EUR", "Solana"), ("XRP-EUR", "XRP")]),
    ("rente", "RENTE & VOLATILITEIT", [("^IRX", "VS 3 maanden"), ("^FVX", "VS 5 jaar"), ("^TNX", "VS 10 jaar"), ("^TYX", "VS 30 jaar"),
                                     ("^VIX", "VIX angstindex"), ("DX-Y.NYB", "Dollarindex")]),
]


def quote(sym):
    """Koers, verschil, dag- en 52-wekenbereik, volume, handelsuren en de slotkoersen van de laatste maand."""
    try:
        d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=1mo&interval=1d", 15))
        r = d["chart"]["result"][0]
        m = r["meta"]
        p = m.get("regularMarketPrice")
        closes = [c for c in (r["indicators"]["quote"][0].get("close") or []) if c]
        # Is de laatste slotkoers die van vandaag (= huidige koers)? Dan is de voorlaatste de vorige slot.
        same = bool(closes) and p and abs(closes[-1] - p) <= abs(p) * 1e-4
        prev = closes[-2] if same and len(closes) >= 2 else (closes[-1] if closes else m.get("chartPreviousClose"))
        closes = [round(c, 4) for c in closes]
        chg = (p / prev - 1) * 100 if p and prev else None
        month = (p / closes[0] - 1) * 100 if p and closes else None
        tp = (m.get("currentTradingPeriod") or {}).get("regular") or {}
        now = datetime.now(timezone.utc).timestamp()
        is_open = bool(tp) and tp.get("start", 0) <= now <= tp.get("end", 0)
        return dict(p=p, chg=chg, month=month, cur=m.get("currency"), hi=m.get("regularMarketDayHigh"), lo=m.get("regularMarketDayLow"),
                    hi52=m.get("fiftyTwoWeekHigh"), lo52=m.get("fiftyTwoWeekLow"), vol=m.get("regularMarketVolume"),
                    name=m.get("longName") or m.get("shortName"), open=is_open, spark=closes[-22:],
                    t=iso(datetime.fromtimestamp(m.get("regularMarketTime", 0), timezone.utc)))
    except Exception as e:
        print("koers mislukt:", sym, e, file=sys.stderr)
        return None


def quotes():
    syms = [s for _, _, lst in QUOTES for s, _ in lst]
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(syms, ex.map(quote, syms)))
    return [dict(id=g, title=title, items=[dict(n=n, sym=s, **res[s]) for s, n in lst if res[s]]) for g, title, lst in QUOTES]


BE_CITIES = [("Brugge", 51.21, 3.22), ("Oostende", 51.23, 2.92), ("Gent", 51.05, 3.72), ("Antwerpen", 51.22, 4.40), ("Brussel", 50.85, 4.35),
             ("Leuven", 50.88, 4.70), ("Hasselt", 50.93, 5.34), ("Kortrijk", 50.83, 3.27), ("Mons", 50.45, 3.95), ("Namur", 50.47, 4.87),
             ("Liège", 50.63, 5.57), ("Arlon", 49.68, 5.82)]
EU_CITIES = [("Amsterdam", 52.37, 4.90), ("Parijs", 48.86, 2.35), ("Londen", 51.51, -0.13), ("Berlijn", 52.52, 13.40), ("Madrid", 40.42, -3.70),
             ("Rome", 41.90, 12.50), ("Wenen", 48.21, 16.37), ("Stockholm", 59.33, 18.07), ("Athene", 37.98, 23.73), ("Lissabon", 38.72, -9.14),
             ("Barcelona", 41.39, 2.17), ("Nice", 43.70, 7.27)]


def weather(cities, days=5):
    lat = ",".join(str(c[1]) for c in cities)
    lon = ",".join(str(c[2]) for c in cities)
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m,wind_direction_10m"
           f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset&timezone=Europe%2FBrussels&forecast_days={days}")
    data = json.loads(get(url))
    out = []
    for (n, _, _), d in zip(cities, data):
        c, dl = d["current"], d["daily"]
        out.append(dict(n=n, now=c["temperature_2m"], code=c["weather_code"], wind=c["wind_speed_10m"], wdir=c["wind_direction_10m"],
                        days=[dict(d=dl["time"][i], code=dl["weather_code"][i], max=dl["temperature_2m_max"][i], min=dl["temperature_2m_min"][i],
                                   rain=dl["precipitation_probability_max"][i], rise=dl["sunrise"][i][-5:], set=dl["sunset"][i][-5:]) for i in range(len(dl["time"]))]))
    return out


def warnings():
    """Actuele KMI-weerwaarschuwingen (geel, oranje, rood) via Meteoalarm, gegroepeerd per type en kleur."""
    d = json.loads(get("https://feeds.meteoalarm.org/api/v1/warnings/feeds-belgium"))
    now = datetime.now(timezone.utc)
    groups = {}
    for w in d.get("warnings", []):
        for info in w.get("alert", {}).get("info", []):
            if info.get("language") != "nl-BE":
                continue
            params = {p.get("valueName"): p.get("value", "") for p in info.get("parameter", [])}
            level = params.get("awareness_level", "").split(";")[1].strip().lower() if ";" in params.get("awareness_level", "") else ""
            if level not in ("yellow", "orange", "red"):
                continue
            try:
                if datetime.fromisoformat(info["expires"]) < now:
                    continue
            except Exception:
                pass
            key = (info.get("event", "Waarschuwing"), level)
            g = groups.setdefault(key, {"event": key[0], "level": level, "areas": [], "onset": info.get("onset"),
                                        "expires": info.get("expires"), "desc": clean(info.get("description", ""))[:400]})
            for a in info.get("area", []):
                if a.get("areaDesc") and a["areaDesc"] not in g["areas"]:
                    g["areas"].append(a["areaDesc"])
            g["onset"] = min(g["onset"] or "", info.get("onset") or "") or g["onset"]
            g["expires"] = max(g["expires"] or "", info.get("expires") or "")
    rank = {"red": 0, "orange": 1, "yellow": 2}
    return sorted(groups.values(), key=lambda g: (rank[g["level"]], g["onset"] or ""))


ESPN = "https://site.api.espn.com/apis"
# (ESPN-pad, naam, korte naam, klassement?, teletekstpagina, categorie)
LEAGUES = [("soccer/bel.1", "JUPILER PRO LEAGUE", "Pro League", True, 591, "club"),
           ("soccer/eng.1", "PREMIER LEAGUE", "Premier L.", True, 592, "club"),
           ("soccer/ned.1", "EREDIVISIE", "Eredivisie", True, 593, "club"),
           ("soccer/uefa.champions", "CHAMPIONS LEAGUE", "Champions L.", True, 594, "club"),
           ("soccer/uefa.europa", "EUROPA LEAGUE", "Europa L.", False, 595, "club"),
           ("soccer/uefa.europa.conf", "CONFERENCE LEAGUE", "Conference L.", False, 596, "club"),
           ("soccer/uefa.nations", "NATIONS LEAGUE", "Nations L.", False, 580, "interland"),
           ("soccer/uefa.euroq", "EK-KWALIFICATIE", "EK-kwalif.", True, 581, "interland"),
           ("soccer/fifa.worldq.uefa", "WK-KWALIFICATIE", "WK-kwalif.", True, 582, "interland"),
           ("soccer/uefa.euro_u21_qual", "JONGE DUIVELS  U21", "Jonge Duivels", False, 583, "interland"),
           ("soccer/fifa.friendly", "VRIENDSCHAPPELIJK", "Vriendsch.", False, 584, "interland"),
           ("basketball/nba", "BASKETBAL  NBA", "Basket NBA", False, 587, "ander"),
           ("football/nfl", "AMERICAN FOOTBALL  NFL", "NFL", False, 588, "ander"),
           ("hockey/nhl", "IJSHOCKEY  NHL", "IJshockey NHL", False, 589, "ander")]
LANDEN = {"Belgium": "België", "Netherlands": "Nederland", "France": "Frankrijk", "Germany": "Duitsland", "Italy": "Italië",
          "Spain": "Spanje", "England": "Engeland", "Scotland": "Schotland", "Wales": "Wales", "Northern Ireland": "Noord-Ierland",
          "Republic of Ireland": "Ierland", "Ireland": "Ierland", "Portugal": "Portugal", "Switzerland": "Zwitserland", "Austria": "Oostenrijk",
          "Denmark": "Denemarken", "Sweden": "Zweden", "Norway": "Noorwegen", "Finland": "Finland", "Iceland": "IJsland", "Poland": "Polen",
          "Czechia": "Tsjechië", "Czech Republic": "Tsjechië", "Slovakia": "Slowakije", "Hungary": "Hongarije", "Romania": "Roemenië",
          "Bulgaria": "Bulgarije", "Greece": "Griekenland", "Türkiye": "Turkije", "Turkey": "Turkije", "Croatia": "Kroatië", "Serbia": "Servië",
          "Slovenia": "Slovenië", "Bosnia-Herzegovina": "Bosnië", "Montenegro": "Montenegro", "Albania": "Albanië", "North Macedonia": "N.-Macedonië",
          "Ukraine": "Oekraïne", "Russia": "Rusland", "Belarus": "Wit-Rusland", "Georgia": "Georgië", "Armenia": "Armenië", "Azerbaijan": "Azerbeidzjan",
          "Kazakhstan": "Kazachstan", "Lithuania": "Litouwen", "Latvia": "Letland", "Estonia": "Estland", "Luxembourg": "Luxemburg",
          "Cyprus": "Cyprus", "Malta": "Malta", "Moldova": "Moldavië", "Kosovo": "Kosovo", "Israel": "Israël", "Faroe Islands": "Faeröer",
          "Morocco": "Marokko", "United States": "Verenigde Staten", "USA": "Verenigde Staten", "Brazil": "Brazilië", "Argentina": "Argentinië",
          "Mexico": "Mexico", "Japan": "Japan", "South Korea": "Zuid-Korea", "Egypt": "Egypte", "Tunisia": "Tunesië", "Algeria": "Algerije"}


def nl(name):
    for en, n in LANDEN.items():
        if name == en or name.startswith(en + " "):
            return n + name[len(en):]
    return name


def espn(path):
    try:
        return json.loads(get(path, 20))
    except Exception:
        return None


def league(lid, name, short, with_table, page, cat):
    """Uitslagen van de voorbije 30 dagen (recentste eerst), programma voor de komende 7 dagen en (optioneel) het klassement."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    # ESPN aanvaardt hier enkel een maand (JJJJMM); zo dekken we 30 dagen terug en 14 vooruit
    months = sorted({(now + timedelta(days=i)).strftime("%Y%m") for i in (-30, 0, 14)})
    boards = [espn(f"{ESPN}/site/v2/sports/{lid}/scoreboard?dates={m}&limit=300") for m in months]
    lo, hi = iso(now - timedelta(days=30)), iso(now + timedelta(days=14))
    boards = [{"events": [e for e in (b or {}).get("events", []) if lo <= norm_time(e["date"]) <= hi]} for b in boards]
    results, upcoming, seen_ev = [], [], set()
    for b in boards:
        for ev in (b or {}).get("events", []):
            if ev["id"] in seen_ev:
                continue
            seen_ev.add(ev["id"])
            c = ev["competitions"][0]
            teams = {x["homeAway"]: x for x in c["competitors"]}
            st = ev["status"]["type"]
            m = dict(d=ev["date"], home=nl(teams["home"]["team"]["shortDisplayName"]), away=nl(teams["away"]["team"]["shortDisplayName"]),
                     hs=teams["home"].get("score"), as_=teams["away"].get("score"), state=st["state"], detail=st.get("shortDetail", ""))
            (upcoming if st["state"] == "pre" else results).append(m)
    results.sort(key=lambda m: m["d"], reverse=True)
    upcoming.sort(key=lambda m: m["d"])
    table = []
    if with_table and (results or upcoming):  # geen oud klassement tonen voor een competitie die stilligt
        st = espn(f"https://site.web.api.espn.com/apis/v2/sports/{lid}/standings")
        for ch in (st or {}).get("children", [])[:1]:
            for e in ch["standings"]["entries"]:
                s = {x["name"]: x.get("displayValue") for x in e["stats"]}
                table.append(dict(team=nl(e["team"].get("shortDisplayName") or e["team"]["displayName"]), pl=s.get("gamesPlayed"), w=s.get("wins"),
                                  d=s.get("ties"), l=s.get("losses"), gd=s.get("pointDifferential"), pts=s.get("points"), rank=s.get("rank")))
        table.sort(key=lambda t: int(t["rank"] or 99))
    # Wedstrijden van België eerst bij interlands met veel wedstrijden
    if cat == "interland":
        results.sort(key=lambda m: "België" not in (m["home"] + m["away"]))
        upcoming.sort(key=lambda m: "België" not in (m["home"] + m["away"]))
    return dict(id=lid, name=name, short=short, page=page, cat=cat, results=results[:40], upcoming=upcoming[:40], table=table)


def tennis(tour):
    """Enkelspel van de lopende toernooien: recente uitslagen, komende partijen en de wereldranglijst."""
    d = espn(f"{ESPN}/site/v2/sports/tennis/{tour}/scoreboard") or {}
    events = []
    for ev in d.get("events", []):
        done, todo = [], []
        for gr in ev.get("groupings", []):
            gname = gr.get("grouping", {}).get("displayName", "")
            if "Singles" not in gname or ("Women" in gname) != (tour == "wta"):  # gemengde toernooien: enkel heren (ATP) of dames (WTA)
                continue
            for c in gr.get("competitions", []):
                comp = c.get("competitors", [])
                if len(comp) != 2:
                    continue
                st = c.get("status", {}).get("type", {})
                ath = [x.get("athlete") or {} for x in comp]
                names = [a.get("shortName") or a.get("displayName") or "?" for a in ath]
                be = any(a.get("flag", {}).get("alt") == "Belgium" for a in ath)
                rnd = (c.get("round") or {}).get("displayName", "")
                if st.get("state") == "post":
                    w = 0 if comp[0].get("winner") else 1
                    l = 1 - w
                    ls = [comp[w].get("linescores", []), comp[l].get("linescores", [])]
                    score = " ".join(f"{int(a.get('value', 0))}-{int(b.get('value', 0))}" for a, b in zip(*ls))
                    done.append(dict(d=c.get("date"), r=rnd, p1=names[w], p2=names[l], score=score, be=be))
                elif st.get("state") == "pre":
                    todo.append(dict(d=c.get("date"), r=rnd, p1=names[0], p2=names[1], be=be))
        done.sort(key=lambda m: (not m["be"], -(datetime.fromisoformat(m["d"].replace("Z", "+00:00")).timestamp() if m["d"] else 0)))
        todo.sort(key=lambda m: (not m["be"], m["d"] or ""))
        if done or todo:
            events.append(dict(name=ev.get("name", ""), done=done[:36], todo=todo[:18]))
    rk = espn(f"{ESPN}/site/v2/sports/tennis/{tour}/rankings") or {}
    ranks = [dict(rank=r.get("current"), name=r["athlete"].get("displayName"), be=r["athlete"].get("flagAltText") == "Belgium",
                  pts=r.get("points")) for r in (rk.get("rankings") or [{}])[0].get("ranks", [])[:30]]
    # Belgen buiten de top 30 er toch bij
    ranks += [dict(rank=r.get("current"), name=r["athlete"].get("displayName"), be=True, pts=r.get("points"))
              for r in (rk.get("rankings") or [{}])[0].get("ranks", [])[30:] if r["athlete"].get("flagAltText") == "Belgium"]
    return dict(events=events, ranks=ranks)


def golf():
    d = espn(f"{ESPN}/site/v2/sports/golf/pga/scoreboard") or {}
    for ev in d.get("events", [])[:1]:
        c = ev["competitions"][0]
        players = sorted(c.get("competitors", []), key=lambda x: x.get("order") or 999)
        return dict(name=ev.get("name"), status=ev.get("status", {}).get("type", {}).get("detail", ""),
                    board=[dict(pos=x.get("order"), name=x["athlete"]["displayName"], score=x.get("score")) for x in players[:30]])
    return None


def f1():
    sb = espn(f"{ESPN}/site/v2/sports/racing/f1/scoreboard") or {}
    out = {"race": None, "drivers": [], "teams": []}
    for ev in sb.get("events", [])[:1]:
        race = next((c for c in ev["competitions"] if c.get("type", {}).get("abbreviation") == "Race"), ev["competitions"][-1])
        out["race"] = dict(name=ev["name"], date=ev["date"], state=race.get("status", {}).get("type", {}).get("state"),
                           results=[dict(pos=r.get("order"), name=r["athlete"]["displayName"]) for r in sorted(race["competitors"], key=lambda r: r.get("order") or 99)][:20])
    st = espn(f"{ESPN}/v2/sports/racing/f1/standings") or {}
    for ch, key in zip(st.get("children", [])[:2], ("drivers", "teams")):
        for e in ch["standings"]["entries"]:
            s = {x["name"]: x.get("displayValue") for x in e["stats"]}
            name = e.get("athlete", {}).get("displayName") or e.get("team", {}).get("displayName")
            out[key].append(dict(rank=s.get("rank"), name=name, pts=s.get("championshipPts") or s.get("points")))
    return out


def sport():
    with ThreadPoolExecutor(3) as ex:
        leagues = list(ex.map(lambda l: league(*l), LEAGUES))
    return dict(leagues=leagues, f1=f1(), atp=tennis("atp"), wta=tennis("wta"), golf=golf())


MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"]


def wiki_clean(s):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def vandaag():
    """Gebeurtenissen en geboortes van vandaag uit de Nederlandstalige Wikipedia-dagpagina."""
    now = datetime.now()
    page = f"{now.day}_{MAANDEN[now.month - 1]}"
    d = json.loads(get(f"https://nl.wikipedia.org/w/api.php?action=parse&page={page}&prop=wikitext&format=json&formatversion=2"))
    text = d["parse"]["wikitext"]
    out = {"events": [], "births": []}
    section, year = None, None
    for line in text.splitlines():
        h = re.match(r"^==\s*([^=]+?)\s*==\s*$", line)
        if h:
            name = h.group(1).lower()
            section = "events" if name.startswith("gebeurtenissen") else "births" if name.startswith("geboren") else None
            continue
        if not section or not line.startswith("*"):
            continue
        m = re.match(r"^\*+\s*(?:\[\[)?(\d{1,4})(?:\]\])?\s*[-–]\s*(.+)$", line)
        if not m:
            continue
        year, rest = m.group(1), wiki_clean(m.group(2))
        if rest and len(out[section]) < 150:
            out[section].append({"y": int(year), "t": rest[:300]})
    return out


def previous():
    """Vorige data.json (van de live site) als terugval wanneer een bron even niet antwoordt."""
    url = os.environ.get("PREV_URL")
    try:
        if url:
            return json.loads(get(url))
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    prev = previous()
    data = dict(updated=datetime.now(timezone.utc).isoformat(), news=news(), quotes=quotes())
    for k, v in data["news"].items():
        if not v and prev.get("news", {}).get(k):
            data["news"][k] = prev["news"][k]
    old_q = {g["id"]: g for g in prev.get("quotes", [])}
    data["quotes"] = [g if len(g["items"]) or g["id"] not in old_q else old_q[g["id"]] for g in data["quotes"]]
    try:
        data["weather"] = dict(be=weather(BE_CITIES), eu=weather(EU_CITIES, 2))
    except Exception as e:
        print("weer mislukt:", e, file=sys.stderr)
        if prev.get("weather"):
            data["weather"] = prev["weather"]
    try:
        data["sport"] = sport()
        if not any(l["results"] or l["table"] for l in data["sport"]["leagues"]) and prev.get("sport"):
            data["sport"] = prev["sport"]
    except Exception as e:
        print("sportuitslagen mislukt:", e, file=sys.stderr)
        if prev.get("sport"):
            data["sport"] = prev["sport"]
    try:
        data["warnings"] = warnings()
    except Exception as e:
        print("weerwaarschuwingen mislukt:", e, file=sys.stderr)
    data["weetjes"] = [{"cat": c, "items": items} for c, items in WEETJES]
    try:
        data["vandaag"] = vandaag()
    except Exception as e:
        print("wikipedia mislukt:", e, file=sys.stderr)
        if prev.get("vandaag"):
            data["vandaag"] = prev["vandaag"]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    n = {k: len(v) for k, v in data["news"].items()}
    q = sum(len(g["items"]) for g in data["quotes"])
    print(f"data.json: nieuws {n}, koersen {q}, weer {'ok' if 'weather' in data else 'NEE'}, {os.path.getsize(OUT)//1024} KB")


if __name__ == "__main__":
    main()
