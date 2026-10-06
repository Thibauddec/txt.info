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


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


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
    ("https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC", "fin", True),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC", "fin", True),
    ("http://rss.cnn.com/rss/money_news_international.rss", "CNN Business", "fin", True),
    (YAHOO, "Yahoo Finance", "fin", True),
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
THEME_FROM = {"be", "wereld", "fin", "tech"}


def theme_of(it):
    for name, rx in THEMES.items():
        if rx.search(it["t"]) or len({m.lower() for m in rx.findall(it["s"] or "")}) >= 2:
            return name
    return None


THEME_MODEL = os.environ.get("THEMA_MODEL", "claude-opus-5-5")
THEME_PROMPT = """Je deelt nieuwskoppen in voor twee themapagina's van een teletekstdienst.

oorlog: gewapende conflicten en brandhaarden in de wereld. Oorlogen, militaire aanvallen of escalaties, staakt-het-vuren
en vredesonderhandelingen, terreuraanslagen, opstanden en gewapende groepen, militaire spanningen tussen landen,
defensie en wapenleveringen die met zo'n conflict te maken hebben, en humanitaire gevolgen ervan.
Niet: sport, films, games, boeken, historische herdenkingen zonder actueel conflict, beeldspraak ("prijzenoorlog").

klimaat: klimaatverandering en het milieu. Opwarming, uitstoot en klimaatbeleid, extreem weer en natuurrampen,
energietransitie (hernieuwbare energie, fossiele brandstoffen in klimaatcontext), biodiversiteit, vervuiling, natuurbehoud.
Niet: gewone weerberichten, energieprijzen zonder klimaat- of transitiehoek, gewone bedrijfsresultaten.

Een kop hoort bij hoogstens één thema; kies het thema waar het bericht vooral over gaat. De meeste koppen horen bij geen
van beide. Geef enkel de nummers van de koppen die wel bij een thema horen."""


def ai_themes(items):
    """Laat Claude bepalen welke berichten over oorlog of klimaat gaan. Geeft None terug als dat niet lukt."""
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
                    "properties": {"oorlog": {"type": "array", "items": {"type": "integer"}},
                                   "klimaat": {"type": "array", "items": {"type": "integer"}}},
                    "required": ["oorlog", "klimaat"],
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
    for theme in ("oorlog", "klimaat"):
        for i in data[theme]:
            if 0 <= i < len(items):
                out.setdefault(i, theme)
    u = response.usage
    print(f"thema's via {THEME_MODEL}: {len(items)} koppen, oorlog {len(data['oorlog'])}, klimaat {len(data['klimaat'])}, "
          f"tokens in {u.input_tokens} uit {u.output_tokens}")
    return out


PER_SOURCE = 14  # max. berichten per bron per sectie, zodat geen enkele site alles overneemt
PRIORITY = {"VRT NWS": 9, "CNN": 8, "CNBC": 8, "Kanaal Z": 8, "Yahoo Finance": 8, "Al Jazeera": 7, "CNN Business": 7, "Sporza": 7, "De Tijd": 6}


def news():
    sec = {k: [] for k in ("be", "wereld", "fin", "sport", "tech", "cultuur", "oorlog", "klimaat")}
    seen = {"main": set(), "oorlog": set(), "klimaat": set()}
    count = {}

    def add(k, it):
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
    for i, th in themes.items():
        add(th, cands[i])
    for k in sec:
        # Om beurten per bron kiezen (nieuwste eerst), zodat elke site aan bod komt; daarna op tijd sorteren
        by_src = {}
        for it in sorted(sec[k], key=lambda i: i["time"] or "", reverse=True):
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
]


def quote(sym):
    try:
        d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range=5d&interval=1d", 15))
        m = d["chart"]["result"][0]["meta"]
        p = m.get("regularMarketPrice")
        prev = m.get("chartPreviousClose") or m.get("previousClose")
        closes = [c for c in (d["chart"]["result"][0]["indicators"]["quote"][0].get("close") or []) if c]
        if len(closes) >= 2 and abs(closes[-1] - p) < 1e-6:
            prev = closes[-2]
        chg = (p / prev - 1) * 100 if p and prev else None
        return dict(p=p, chg=chg, cur=m.get("currency"), hi=m.get("regularMarketDayHigh"), lo=m.get("regularMarketDayLow"),
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
