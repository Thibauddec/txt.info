"""Herschrijft de belangrijkste nieuwsberichten met een lokaal model (Ollama) tot Nederlandstalige teletekstberichten.

Draait op de laptop (geplande taak om 2u15 en 10u15). Elk herschreven bericht wordt daarna door het model
gecontroleerd tegen de bron; wat niet klopt, wordt niet gebruikt. Het resultaat komt in rewrites.json,
dat update.py op GitHub gebruikt om de oorspronkelijke tekst te vervangen.

Gebruik:  py rewrite.py              (alles)
          py rewrite.py --max 3      (test: hoogstens 3 nieuwe berichten)
"""
import argparse, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import update  # hergebruikt het ophalen en selecteren van het nieuws

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("REWRITE_MODEL", "gpt-oss:20b")
OUT = os.path.join(HERE, "rewrites.json")
NL_WORDS = set("de het een en van niet op voor met dat die is zijn wordt naar ook bij uit om over".split())
EN_WORDS = set("the a an and of to in is for with that on was are by from has have will says said".split())


def is_english(it):
    """Enkel Engelstalige berichten worden vertaald; Nederlandstalige blijven zoals de redactie ze schreef."""
    w = re.findall(r"[a-z]+", (it["t"] + " " + (it.get("s") or "")).lower())
    return sum(x in EN_WORDS for x in w) > 2 * max(1, sum(x in NL_WORDS for x in w))


def numbers(text):
    """Alle getallen, zonder scheidingstekens (70,000 / 70.000 / 70 000 -> 70000)."""
    return {re.sub(r"[.,\s]", "", n) for n in re.findall(r"\d[\d.,\s]*\d|\d", text)}


MIN_SOURCE = 150   # alleen herschrijven als de bron genoeg inhoud heeft; een kale titel blijft zoals hij is
PER_SECTION = 10   # de eerste berichten van elke rubriek (wat je op de eerste schermen ziet)
KEEP_DAYS = 4      # oudere herschrijvingen worden opgeruimd
SECTIONS = ["be", "wereld", "vs", "china", "fin", "macro", "oorlog", "klimaat", "ai", "tech", "sport", "cultuur"]

WRITE_SYSTEM = """Je bent eindredacteur van een Vlaamse teletekstdienst. Je vertaalt een Engelstalig nieuwsbericht tot een kort,
helder teletekstbericht in correct, vlot Nederlands voor Vlaamse lezers.

Strikte regels:
- Gebruik ENKEL feiten die in de bron staan. Voeg geen achtergrond, context, verklaring of gevolgen toe die er niet staan.
- Neem namen, cijfers, bedragen, data en citaten exact over. Vertaal bedragen niet naar een andere munt.
- Let precies op wie wat doet, wie wat zegt en wie wat betaalt.
- Geen mening, geen speculatie, geen sensatie. Schrijf zakelijk.
- Kop: maximaal 60 tekens, informatief, geen clickbait.
- Tekst: 2 tot 5 volledige, vlotte zinnen (samen hoogstens 90 woorden). Geen opsomming, geen losse zinsdelen.
- Staat er te weinig in de bron voor meer dan één zin, schrijf dan één zin.

Voorbeeld van de gewenste stijl:
kop: "ECB houdt rente op 2 procent"
tekst: "De Europese Centrale Bank laat haar depositorente ongewijzigd op 2 procent. Volgens de bank is de inflatie in de eurozone in september gedaald tot 2,1 procent."
"""

CHECK_SYSTEM = """Je controleert een herschreven nieuwsbericht tegen de bron. Antwoord 'klopt': false als de herschreven tekst
iets bevat dat NIET in de bron staat, of iets anders weergeeft dan de bron (andere persoon, ander cijfer, andere richting,
wie betaalt/beslist/zegt omgewisseld, verkeerde tijd). Weglaten van details is wel toegestaan.
Wees streng: bij twijfel, bij een dubbelzinnige bron of als de bron niet duidelijk genoeg is om de bewering zeker te stellen
(bijvoorbeeld: werd een bedrijf overgenomen, of nam het zelf iets over?), antwoord 'klopt': false. Leg kort uit wat er fout is."""

SCHEMA_WRITE = {"type": "object", "properties": {"kop": {"type": "string"}, "tekst": {"type": "string"}}, "required": ["kop", "tekst"]}
SCHEMA_CHECK = {"type": "object", "properties": {"klopt": {"type": "boolean"}, "fout": {"type": "string"}}, "required": ["klopt", "fout"]}


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def ollama(system, user, schema, timeout=900):
    body = json.dumps({"model": MODEL, "stream": False, "format": schema, "options": {"temperature": 0.1},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body, headers={"Content-Type": "application/json"})
    for attempt in range(3):  # het model geeft soms een leeg antwoord: opnieuw proberen
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = json.loads(r.read())["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            if attempt == 2:
                raise


def key_of(it):
    return it.get("url") or re.sub(r"\W+", "", it["t"].lower())[:80]


def source_text(it):
    return f"Bron: {it['src']}\nTitel: {it['t']}\nTekst: {it.get('s') or '(geen samenvatting, enkel de titel)'}"


def rewrite(it):
    src = source_text(it)
    out = ollama(WRITE_SYSTEM, src, SCHEMA_WRITE)
    kop, tekst = out["kop"].strip().strip('"'), re.sub(r"\s*\n\s*", " ", out["tekst"]).strip().strip('"')
    if not kop or len(kop) > 90:
        return None, "kop ontbreekt of te lang"
    extra = numbers(kop + " " + tekst) - numbers(src)
    if extra:
        return None, "cijfer(s) niet in de bron: " + ", ".join(sorted(extra))
    check = ollama(CHECK_SYSTEM, f"BRON\n{src}\n\nHERSCHREVEN\nKop: {kop}\nTekst: {tekst}", SCHEMA_CHECK)
    if not check.get("klopt"):
        return None, "controle: " + (check.get("fout") or "klopt niet")[:160]
    return {"t": kop, "s": tekst}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="hoogstens zoveel nieuwe berichten (0 = geen limiet)")
    args = ap.parse_args()
    t0 = time.time()
    try:
        cache = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        cache = {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("at", "") >= cutoff}

    log("nieuws ophalen ...")
    news = update.news()
    todo, seen = [], set()
    for sec in SECTIONS:
        for it in news.get(sec, [])[:PER_SECTION]:
            k = key_of(it)
            if k in seen or k in cache or len(it.get("s") or "") < MIN_SOURCE or not is_english(it):
                continue
            seen.add(k)
            todo.append(it)
    if args.max:
        todo = todo[:args.max]
    log(f"{len(todo)} nieuwe berichten te herschrijven met {MODEL} ({len(cache)} al klaar)")

    ok = rejected = failed = 0
    for n, it in enumerate(todo, 1):
        try:
            res, why = rewrite(it)
        except Exception as e:
            failed += 1
            log(f"[{n}/{len(todo)}] fout: {e}")
            continue
        if res:
            ok += 1
            cache[key_of(it)] = {**res, "src": it["src"], "orig": it["t"], "model": MODEL, "at": datetime.now(timezone.utc).isoformat()}
            log(f"[{n}/{len(todo)}] ok   {res['t']}")
        else:
            rejected += 1
            log(f"[{n}/{len(todo)}] afgekeurd ({why}): {it['t'][:70]}")
        if n % 10 == 0:  # tussentijds bewaren
            json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    log(f"klaar in {(time.time() - t0) / 60:.0f} min: {ok} herschreven, {rejected} afgekeurd door de controle, {failed} fouten; {len(cache)} in totaal")


if __name__ == "__main__":
    main()
