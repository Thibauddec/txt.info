# Elenet Teletekst

Teletekst zoals vroeger, als app voor je gsm: https://thibauddec.github.io/elenet-teletekst/

| Pagina | Inhoud |
|---|---|
| 100 | Index |
| 101-199 | Nieuws België |
| 200-299 | Wereldnieuws |
| 300-399 | Financieel nieuws |
| 400-499 | Beurs en aandelen |
| 500-599 | Sport |
| 600-699 | Weer |
| 700 | Wetenschap & tech |
| 800 | Cultuur & media |
| 900 | Ontspanning & info |

`update.py` haalt elk half uur nieuws (VRT NWS, NOS, De Tijd, Sporza), koersen (Yahoo Finance) en weer (Open-Meteo) op
via de GitHub Action in `.github/workflows/update.yml` en publiceert `site/` op GitHub Pages.
