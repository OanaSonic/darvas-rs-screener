# DARVAS RS Screener v10.3 — Export simplificat, doar 3 butoane

Versiune pentru repository-ul GitHub existent `OanaSonic/darvas-rs-screener`. Se păstrează algoritmii de scanare, presetările, importul SCTR, corecția universului 494 vs 95 din v10.2 și graficul la hover.

## Actualizare rapidă

1. Descarcă arhiva hotfix și extrage fișierul `app.py`.
2. În GitHub intră în repository → **Add file → Upload files** → încarcă noul `app.py`, înlocuindu-l pe cel vechi → **Commit changes**.
3. Deschide aplicația Streamlit; dacă nu se actualizează, **Manage app → Reboot app**.
4. După **RUN SCREENER**, la secțiunea **05 · Descarcă rezultatele scanării curente** există doar **trei butoane**:

| Buton | Fișier | Conținut |
|---|---|---|
| TradingView | `.txt` | `NASDAQ:NVDA,NYSE:MA` (format nativ pentru Upload list) |
| Deepvue | `.txt` | Câte un ticker pe linie (pentru Paste) |
| thinkorswim | `.csv` | O coloană `Symbol` (pentru Import watchlist) |

Fiecare fișier primește automat numele strategiei **folosite la scanarea efectivă**, timeframe-ul, data scanării și platforma. Listele conțin **doar rezultatele finale ale scanării**; nu se aplică alte filtre și tickerele duplicate sunt eliminate. Dacă nu există rezultate, butoanele de descărcare sunt inactive.

### TradingView: prefix bursier verificat automat

TradingView necesită fișier **TXT** cu prefix `EXCHANGE:` și simboluri despărțite prin virgulă, nu CSV. Aplicația încearcă să determine automat bursele din directorul public NasdaqTrader și, unde nu reușește, din metadatele Yahoo Finance. Dacă anumite burse nu pot fi confirmate, **nu le inventează**: avertizează în mod explicit, iar acele tickere sunt omise numai din fișierul TradingView. Fișierele Deepvue și thinkorswim păstrează toate rezultatele. Verifică avertismentul înainte de import.

Surse: [TradingView](https://www.tradingview.com/support/solutions/43000487233-how-to-import-or-export-a-watchlist/) · [thinkorswim](https://toslc.thinkorswim.com/center/faq/Customization) · [Deepvue](https://docs.deepvue.com/articles/creating-a-watchlist).

## Verificare

`python -m pytest -q` testează strategiile, exporturile, deduplicarea, sursele de date, compatibilitatea și controlul stărilor de contrast. Rularea finală pe Streamlit Cloud și disponibilitatea live a directoarelor externe trebuie confirmate după instalare.
