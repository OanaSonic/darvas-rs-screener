# DARVAS RS — Daily / Weekly Breakout Screener

O aplicație Streamlit în stil dark, realizată separat de RS Matrix Dashboard. Folosește **date OHLCV reale, când sunt disponibile**, nu tickere sau semnale fictive. Scanează Daily și Weekly, desenează în mod nativ chart-uri la **hover pe ticker** și calculează **Relative Strength vs SPY sau SPX**.

## Publicare: GitHub + Streamlit Cloud

1. Creează **un repository GitHub nou**, de exemplu `darvas-rs-screener`. Recomand separat de `OanaSonic/rs-matrix-dashboard`, ca să nu suprascrii aplicația RS Matrix.
2. Dezarhivează pachetul și încarcă în rădăcina repository-ului fișierele `app.py`, `screener_core.py`, `hover_chart.py`, `requirements.txt`, `sample_scores.csv`, plus directorul `.streamlit/` (inclusiv `config.toml`).
3. În Streamlit Community Cloud, **Create app → repository-ul nou → branch main → main file `app.py` → Deploy**. Nu ai nevoie de cheie API Yahoo pentru screening-ul OHLCV.
4. Din sidebar alegi universul (`Starter`, `S&P 500`, `Nasdaq-100` sau `Custom`), adaugi tickere dacă dorești, apoi setezi filtrele și apeși **RUN DARVAS SCAN**.
5. La rezultate, ține mouse-ul pe ticker pentru **chart popup**: lumânări OHLC, 20 EMA, zona Darvas, suport/rezistență, volum, RS vs benchmark. Click pe ticker fixează chartul, click din nou îl închide; poți filtra și sorta rezultatele fără a reporni scanarea.

> Îți trebuie Python 3.11+ și Streamlit 1.56+. Local: `pip install -r requirements.txt` și `streamlit run app.py`. Testele logice: `python -m pytest -q tests/` (necesită `pytest`).

## Configurația implicită din videoclip

| Filtru | Default | Interpretare în această aplicație |
|---|---|---|
| Timeframe | Weekly | Poți trece pe Daily |
| Direction | Long | Long și Short calculate simetric, cu stop corespunzător |
| Minimum box bars | 6 | Consolidare pe minimum 6 lumânări închise |
| Maximum box bars | 16 | Maximum implicit de căutare, ajustabil |
| Maximum consolidation range | 20% | `(box_high - box_low) / box_low × 100 ≤ 20%` |
| Stop position | 33% | Din partea inferioară a box-ului la Long |
| Max stop risk | 16% | `(entry - stop) / entry × 100 ≤ 16%` la Long |
| Breakout clearance MIN | 4% | Close al lumânării de breakout peste box_high cu cel puțin 4% |
| Close strength MIN | 75% | `(close-low)/(high-low) × 100 ≥ 75%` |
| Volume increase MIN | 1% | Volum vs lumânarea **imediat precedentă** |
| Entry beyond close | 0,01% | Prețul de intrare teoretic peste close-ul breakout-ului |
| EMA confirmation | 20 EMA | Prețul peste EMA pentru long |
| MACD | ON | **MACD line > signal line**, nu neapărat `MACD > 0` |
| Market cap | $1B | Verificat automat pe **candidații finali**, dacă Yahoo oferă market cap |
| Quality / Growth | 60 / 60 | Filtrează numai dacă importul extern conține scorurile și activezi bifa respectivă |
| RS vs SPY / SPX | 3M outperform | Raportul `(stock/benchmark)` trebuie să crească pe 13 săptămâni / 63 zile |
| RS rank percentile | 0 = OFF | Percentila **calculată local** în universul descărcat; diferă de SCTR |
| SCTR | 70 / OFF | Numai din CSV StockCharts încărcat |
| Barchart Opinion | OFF | CSV sau API licențiat `getSignal` |

**Moduri suplimentare**: Breakout, Near breakout sau Both. Near breakout caută consolidări încheiate la cel mult X% sub rezistență, însă nu le prezintă drept semnale deja confirmate. **Fresh breakout** poate căuta un semnal apărut în ultimele 1–6 lumânări închise. Acest mod este unul de **scanare**, nu un backtest.

### RS — Relative Strength vs SPY/SPX

- **RS 3M%:** `100 × [(StockClose/BenchmarkClose)_today / (StockClose/BenchmarkClose)_13weeks_ago − 1]` sau 63 zile pentru Daily.
- **52w RS high:** raportul stock / benchmark atinge cel mai înalt nivel din ultimele 52 de săptămâni sau 252 de zile.
- **RS rank:** percentila performanței relative pe 3 luni între tickerele din universul accesibil, calculată de aplicație. **Nu este SCTR.**
- Graficul de hover desenează linia RS în panoul inferior, pe o scară normalizată la 100; comparația de preț nu trebuie confundată cu un indicator fundamental.

### StockCharts SCTR: import CSV

StockCharts permite *Download CSV* din rezultatele scanării. Încarcă fișierul în sidebar. Parserul caută `Symbol`/`Ticker` și `SCTR`/`SCTR Rank`; apoi activează **Enforce imported SCTR** dacă dorești filtrarea la minimum 70. Nu există în acest pachet un feed automat SCTR neautorizat.

Sursă oficială: https://help.stockcharts.com/scanning-and-alerts/technical-scans/working-with-scan-results

### Barchart Technical Opinion: CSV sau API

- CSV: încarcă un CSV care conține `Ticker` și `Barchart Opinion` / `Technical Opinion` / `overallAverageSignal`.
- API: dacă ai **Barchart OnDemand API key licențiată**, introdu cheia în sidebar și bifează opțiunea. Programul apelează `getSignal.json` pentru candidații tehnici și citește `overallAverageSignal` plus `overallAverageStrength`. Nu este parola site-ului Barchart.
- Filtre posibile: Off, Buy / Strong Buy, Strong Buy only.

Specificație oficială API: https://www.barchart.com/ondemand/api/getSignal

### Quality și Growth

Scorurile exact ca în Financial Wisdom nu sunt publicate în mod verificabil drept un API compatibil și **nu sunt identice cu SCTR sau Barchart Opinion**. Poți importa un CSV cu `Ticker,Quality Score,Growth Score` dintr-o sursă licențiată. Când lipsesc, coloanele afișează `—`, iar bifa **Enforce Quality & Growth CSV** este OFF. La activarea bifei, tickerele fără valori sunt excluse explicit.

## Calitatea datelor / limitări

- OHLCV vine din Yahoo Finance prin `yfinance`: EOD sau întârziat, cache 15 minute; **nu garantăm prețuri consolidat real-time**. Datele gratuite pot fi rate-limited sau indisponibile. Lumânările nefinalizate sunt omise implicit (regulă orară NYSE; sesiunile scurtate pot necesita verificare).
- Mod implicit: **candles închise**; Weekly agregat din OHLCV Daily, încheiat vineri. Prețurile sunt ajustate pentru corporate actions de Yahoo.
- Filtrul de market cap se verifică prin metadatele Yahoo pentru candidații rămași, ceea ce poate dura. Dacă un market cap nu poate fi verificat, aplicația îl exclude cât timp pragul este activ și afișează numărul exclus. Un minim de `0` dezactivează acest filtru.
- Pentru scanări mari (S&P 500), intervalele de date pot dura și pot apărea simboluri fără date. Interfața raportează exact câte simboluri au fost analizate și câte au fost indisponibile. `Max tickers to scan` limitează explicit universul. Listele indexurilor sunt preluate periodic din Wikipedia; nu reprezintă o sursă profesională point-in-time de compoziție a indicilor.
- Exchange este verificat doar dacă activezi un filtru NYSE/NASDAQ/AMEX/Arca; simbolurile cu exchange necunoscut sunt excluse în acest mod.
- Nu oferă backtest, statistici de randament, execuție de ordine sau alerte automate. Rezultatele **412% return / 41% CAGR / 16% DD** sunt afirmații din materialul video, nu rezultate certificate de această aplicație. A reproduce în mod riguros acele cifre ar necesita date point-in-time fără survivorship bias, corporate actions, scoruri istorice, reguli exacte de tranzacționare și costuri.

## Structura proiectului

- `app.py` — Streamlit UI, Yahoo batch download, input CSV, Barchart API, filtrare, export CSV.
- `screener_core.py` — toate calculele pure de box, EMA, MACD, RS, semnal.
- `hover_chart.py` — tabel interactiv și preview candlestick SVG la mouseover, fără JS extern.
- `.streamlit/config.toml` — temă dark cu dropdown-uri lizibile.
- `sample_scores.csv` — **doar model de antete**, fără scoruri inventate.
- `tests/test_screener_core.py` — teste sintetice ale logicii, nu date de piață fabricate.

Aceasta este o **aplicație nouă**; nu suprascrie RS Matrix v5.
