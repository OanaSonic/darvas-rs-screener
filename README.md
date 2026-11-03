# Darvas RS Screener v6.1 — Quick Presets & TypeError fix

Streamlit dashboard for StockCharts SCTR imports (CSV or copied SCTR Reports table), weekly/daily Darvas and VCP screening, and first pullback to a 20-week moving average. Yahoo Finance supplies adjusted historical OHLCV. This is **not real-time data** and is **not a backtesting engine**.

## What's fixed in v6.1

- **`TypeError` on `Rules(...)`:** `app.py` and `screener_core.py` now have matching interfaces. An explicit API version handshake checks `screener_core.py` and `pullback_core.py` **before downloading any market data** and shows helpful instructions instead of an opaque Python traceback if one module is stale.
- Three **Quick Presets** immediately visible:
  1. **Darvas Breakout** — classical high-of-box breakout with 4% minimum breakout clearance, close-strength/volume/EMA/MACD confirmation; default Weekly but Daily available.
  2. **VCP Pre-Breakout** — final contraction smaller than the preceding range, approaching final local pivot; default Weekly but Daily available. An experimental mechanical contraction proxy, not a guaranteed VCP pattern.
  3. **First Pullback EMA 20W** — Weekly only; first approach, touch or confirmed rebound after a prior breakout and upward impulse.
- A single **Advanced Filters — optional** panel, closed by default, contains the rest of the inputs: pattern type, exchange, Darvas, VCP, pullback and additional RS settings.
- Selecting a new preset clears results from the previous preset; no misleading old results shown.
- The default scan limit is **500 tickers**, enough for a typical pasted SCTR list. Scans can take time and Yahoo may rate-limit.
- Keeps user-requested removals: **no Market Cap filter**, no **Barchart**, **Quality**, or **Growth** fields/columns.
- Preserves the dark theme, hover charts and diagnostic candidate explorer.

## Install / update an existing GitHub repository

1. Download and **unzip the release**.
2. In `OanaSonic/darvas-rs-screener`, use **Add file → Upload files** and upload the **files inside the extracted ZIP** (do not upload the ZIP itself). Commit the changes to branch `main`.
3. **Replace ALL five Python files together**: `app.py`, `screener_core.py`, `pullback_core.py`, `hover_chart.py`, and `sctr_paste.py`; also upload `requirements.txt` and `.streamlit/config.toml` as supplied. The two `*_core.py` files are mandatory; do not mix v6.1 `app.py` with older modules.
4. Streamlit Cloud should redeploy the `app.py` entrypoint after GitHub commits. If the older version remains, use **Manage app → Reboot** and inspect logs. Paste SCTR table again if the app session resets.
5. For the previous `TypeError`, if the new version shows a version-mismatch warning, confirm `screener_core.py` and `pullback_core.py` were uploaded **to the repository root**, not a subfolder and not as `filename (1).py`.

## Quick use

- Paste the copied table in the **Paste SCTR Reports — fără CSV** sidebar expander, and select **Imported SCTR list**. The data are a timestamp-less snapshot from StockCharts; replace periodically.
- Choose one of the three presets. Set the benchmark and (optionally) the signal freshness, SCTR minimum and RS filter.
- Click **RUN SCREENER**. The green/red signals, charts and result exports come from current available historical OHLCV; missing tickers are not invented.
- To customize close strength, VCP range, other indicators, etc., open **Advanced Filters — optional**. It stays closed unless needed.

## Data and strategy caveats

A `BOUNCE CONFIRMED` signal is a research flag and not an executable buy order. Weekly scans exclude the current incomplete week. RS percentile is computed within the downloaded universe; SCTR is taken from imported StockCharts text or CSV. Yahoo data can be delayed, rate-limited or incomplete. Any backtested returns in the cited video are third-party claims, not reproduced by this screener. None of the displayed signals constitutes investment advice.

## Tests

Run `python -m pytest -q` (requires `pytest`, `numpy`, `pandas`). All source files can be compiled with `python -m compileall -q .`. Streamlit Cloud / Yahoo network deployment must still be checked in the user's environment.
