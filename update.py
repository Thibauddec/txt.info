"""Haalt actueel nieuws, koersen en weer op en schrijft data.json voor de teletekst-app."""
import json, re, html, sys, os
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

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
]
PER_SOURCE = 14  # max. berichten per bron per sectie, zodat geen enkele site alles overneemt
PRIORITY = {"VRT NWS": 9, "CNN": 8, "CNBC": 8, "Kanaal Z": 8, "Yahoo Finance": 8, "Al Jazeera": 7, "CNN Business": 7, "Sporza": 7, "De Tijd": 6}


def news():
    sec = {k: [] for k in ("be", "wereld", "fin", "sport", "tech", "cultuur")}
    seen = set()
    count = {}

    def add(k, it):
        key = re.sub(r"\W+", "", it["t"].lower())[:50]
        if key in seen or count.get((k, it["src"]), 0) >= PER_SOURCE: return
        seen.add(key)
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
    for (url, src, default, fixed), items in results:  # volgorde van FEEDS: eerste bron wint bij dubbels
        for it in items:
            add(default if fixed else classify(it["tags"], it["url"], default), it)
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
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    n = {k: len(v) for k, v in data["news"].items()}
    q = sum(len(g["items"]) for g in data["quotes"])
    print(f"data.json: nieuws {n}, koersen {q}, weer {'ok' if 'weather' in data else 'NEE'}, {os.path.getsize(OUT)//1024} KB")


if __name__ == "__main__":
    main()
