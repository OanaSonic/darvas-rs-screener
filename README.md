# DARVAS RS Screener v10 — Strategy-named downloads + TradingView CSV/TXT

Streamlit app for real historical daily/weekly OHLCV screening of Darvas, VCP and First Pullback EMA20W. No synthetic trading signals; public Yahoo Finance feeds can be delayed, rate limited or unavailable. StockCharts SCTR is a manually pasted snapshot, not a live API.

## Fast update from v9: only ONE file

In the existing GitHub repository `OanaSonic/darvas-rs-screener`, replace only **`app.py`** from the v10 one-file hotfix archive. Keep `hover_chart.py`, `screener_core.py`, `pullback_core.py`, `sctr_paste.py`, and `requirements.txt` from your working v9 setup. Deploys on Streamlit Cloud after commit; reboot the app if necessary.

The export functions are *embedded in app.py*. No new imported Python module is needed, so this version does not create another `ModuleNotFoundError`. The optional full developer archive contains `watchlist_export.py` for independent tests only. `watchlist_export.py` in the full developer archive is optional and provided only for independent testing/reuse.

## 05 · Export Center v10

**Automatic file names** include the actual exported strategy (or all strategies if the selected subset mixes setups), completed scan timeframe, filter stage, chosen statuses and optional numeric thresholds, scan date and destination platform. Example: `First_Pullback_EMA20W_Weekly_RezultateFinale_20261109_TradingView.txt`. A cached scan keeps the name of the **strategy actually used at scan time**, even if you switch quick presets without rerunning. The imported-universe export is marked `Univers_SCTR` and never mislabeled as a breakout.

**TradingView watchlist import uses TXT, not CSV.** Official source: https://www.tradingview.com/support/solutions/43000487233-how-to-import-or-export-a-watchlist/ . Use **TradingView TXT · import direct** for Watchlist → Upload list…; values are comma-separated with venue prefixes like `NASDAQ:NVDA,NYSE:MA`. The additional **TradingView CSV · tabel** is provided as requested for Excel/spreadsheets, with a single `Symbol` column containing the same prefixed symbols. The CSV is **not** the native direct watchlist-upload format. No unverified exchange is guessed.

## Export subsets

After **RUN SCREENER**, choose exactly one dataset:

1. Results after all active scan filters.
2. After RS, before SCTR and exchange.
3. After RS + SCTR, before exchange.
4. All technical setup candidates before RS/SCTR — not just the 120 shown in the chart explorer.
5. Entire chosen input universe (SCTR snapshot/custom list), even if no technical setups match.

Then filter without rescanning by **Status**, **Pattern**, **Ticker**, and optionally additional **SCTR, RS 3M, Stop risk, Signal age** conditions. The preview and downloads reflect that server-side export subset. The tiny search field within the separate hover-chart table is client-side only and does not change exports.

Exports:

| Target | Button | Format | Import workflow |
| --- | --- | --- | --- |
| TradingView watchlist | TradingView TXT · import direct | `.txt`, `NASDAQ:NVDA,NYSE:MA,...` | Watchlist name menu → **Upload list…** |
| TradingView spreadsheet | TradingView CSV · tabel | `.csv` with single `Symbol` column | Excel or other workflows; **not** the direct watchlist-upload format |
| Deepvue | Deepvue TXT | `.txt` with ticker on each line | Open **Watchlists → New Watchlist → Add Symbol**, then paste contents; or use the built-in copy-ready list |
| thinkorswim | thinkorswim CSV | `.csv` with a single `Symbol` column | **MarketWatch → Quotes → Create watchlist / Import** from CSV |
| Research backup | Detalii CSV | `.csv` with stage/status/SCTR/RS/risk/date etc. | Spreadsheet, archive, further filtering |

**TradingView exchange accuracy:** No invented stock-exchange prefixes. Known mappings from the scan or manually uploaded `Symbol,Exchange` CSV are used. Click **Verifică bursele** to retrieve missing exchanges in batches of up to 80 through Yahoo metadata (which may not always respond). Any remaining unknown venue is omitted by default from TradingView TXT, with the count shown. A manual NASDAQ/NYSE/AMEX override is available but explicitly not verified; review it before import. Yahoo dash class symbols such as `BRK-B` become `NYSE:BRK.B` for TradingView. Deepvue and thinkorswim exports do not need exchange prefixes.

**Important:** these files export watchlists of tickers, not strategy filters, indicators, chart annotations or automatic alerts. Imported lists do not sync automatically after a new scan.

## Legibility fixes

Dark backgrounds and high-contrast text are enforced together on normal/hover/focus/disabled states of download buttons, select/multiselect dropdowns, option lists, and table rows. The embedded table iframe now has an explicit dark background so its hint text remains readable even when Streamlit or the browser uses light mode.

## Tests

Run `python -m pytest -q` from the project directory. 68 pure-unit/integration-source tests validate the full screening modules, format conversions, subset selection, exchange mapping, and consistency of the self-contained export functions. Browser-level hover rendering was checked in local headless Chromium. Live Streamlit Cloud deployment and Yahoo metadata access must still be verified after update.

## Sources

* [TradingView official watchlist TXT import](https://www.tradingview.com/support/solutions/43000487233-how-to-import-or-export-a-watchlist/)
* [Deepvue official instructions: paste ticker list](https://docs.deepvue.com/articles/creating-a-watchlist)
* [thinkorswim official watchlist CSV import](https://toslc.thinkorswim.com/center/faq/Customization)


## v10.1 — Corecție selectare univers SCTR (9 Nov 2026)

- Un raport SCTR lipit sau un CSV SCTR nou, cu scoruri valide, activează automat `Stock universe = Imported SCTR list` și `Scanează TOATE acțiunile...`, înainte ca Streamlit să creeze selectorul de univers.
- Dacă alegi manual ulterior alt univers, alegerea ta rămâne activă până la un **nou import SCTR**. Astfel sunt posibile în continuare comparații cu lista Starter, S&P 500 sau NASDAQ-100.
- În rezumatul scanării se afișează numele universului activ, nu doar numărul simbolurilor. Dacă există SCTR importat și alt univers activ, apare un avertisment cu buton de corectare rapidă.
- Nu se schimbă algoritmii Darvas, VCP, Pullback și nici exporturile TradingView/Deepvue/thinkorswim din v10.
- Correctitudinea 494/95 este testată, dar instalarea live pe Streamlit Cloud trebuie validată după upload.

### Instalare rapidă
Încarcă doar `app.py` din hotfix în rădăcina repository-ului GitHub, suprascriind fișierul precedent, apoi Commit changes. Pe Streamlit, dacă datele SCTR s-au resetat, lipește din nou tabelul.

## v10.2 – Corecție persistentă SCTR 494 vs Starter 95 (9 noiembrie 2026)

**Problemă:** aplicația putea afișa 494 tickere recunoscute în raportul SCTR, dar continua să scaneze doar lista Starter cu 95 de simboluri. În v10.1 activarea automată se întâmpla numai la detectarea unui snapshot nou, astfel încât o sesiune Streamlit păstrată putea reveni la Starter.

**Soluție:** `app.py` revalidează **la fiecare rerun** existența datelor SCTR și alege implicit `Imported SCTR list`, cu scanarea tuturor simbolurilor, dacă utilizatorul nu a selectat explicit alt univers. O schimbare manuală reală în selectorul `Stock universe` rămâne posibilă; un import SCTR nou reface prioritatea implicită. La pornirea scanării există un mecanism separat care verifică din nou universul și împiedică trimiterea silențioasă a listei Starter.

Vei vedea în aplicație versiunea **v10.2** și mesajul vizibil `SCTR IMPORTAT: N tickere · SCANARE PROGRAMATĂ: N tickere`. Dacă lista copiată conține 494 de simboluri, **trebuie** să apară 494 de scanat înainte de orice erori de acces la date OHLCV. `SCTR >=70`, RS și criteriile Darvas/VCP/Pullback sunt aplicate ulterior și pot reduce separat numărul de rezultate.

**Instalare rapidă:** în GitHub înlocuiește **doar `app.py`** cu fișierul din pachetul hotfix. Commit changes, apoi în Streamlit `Manage app → Reboot app` și o reîncărcare completă. Celelalte module pot rămâne din v8.1/v9/v10 compatibile (logica Darvas și Pullback este neschimbată). Dacă sesiunea pierde textul importat, lipește din nou tabelul SCTR.

**Verificare:** `python -m pytest -q`: 79 teste trecute, incluzând cazul 494 recunoscute, 95 Starter inițial, persistența listei la rerun și schimbarea manuală permisă. Nu a fost verificată lansarea live în Streamlit Community Cloud și nu este garantat un număr minim de *matches*: acesta depinde de setările presetului, date și momentul scanării.
