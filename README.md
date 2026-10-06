# txt.info

Teletekst zoals vroeger, als app voor je gsm: https://thibauddec.github.io/elenet-teletekst/

| Pagina | Inhoud |
|---|---|
| 100 | Index |
| 101-199 | Nieuws België |
| 200-299 | Wereldnieuws |
| 300-399 | Financieel nieuws |
| 400-499 | Beurs en aandelen |
| 500-579 | Sportnieuws |
| 580-599 | Sportuitslagen: voetbal (clubs en interlands), tennis, F1, golf, NBA, NFL, NHL |
| 600-605 | Weer en KMI-waarschuwingen |
| 610 | Wetenschap & tech |
| 650 | Cultuur & media |
| 700-799 | Oorlog & brandhaarden |
| 800-899 | Klimaat |
| 900-999 | Weetjes, vandaag in de geschiedenis, horoscoop, kalender |

`update.py` haalt elke dag om 5u en 13u nieuws (VRT NWS, NOS, De Tijd, Sporza), koersen (Yahoo Finance) en weer (Open-Meteo) op
via de GitHub Action in `.github/workflows/update.yml` en publiceert `site/` op GitHub Pages.
