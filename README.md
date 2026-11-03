# Darvas RS Screener v7 — Recommended One-Click Presets

A dark-mode Streamlit technical screener for **Darvas breakout**, **tight-base/VCP pre-breakout**, and **first pullback to the weekly 20 EMA**. It uses historical Yahoo Finance OHLCV and manually imported StockCharts SCTR snapshots. Not a real-time feed, portfolio backtester, or trade execution system.

## What's new in v7

The three **recommended presets now actually configure every filter**, rather than just selecting the strategy's name. Switching a preset or clicking **↺ Reaplică presetul** sets the inputs to their recommended values and clears out results from the previous configuration. Open **⚙ Advanced Filters — optional** to change anything; a `ⓘ` help icon explains each filter with an example.

| Preset | Starting rule settings |
| --- | --- |
| **Darvas Breakout** | **Weekly**; SCTR ≥70; RS 3M outperform SPY; freshness **2 completed weeks**; long breakout; consolidation 6–16 bars, width ≤20%; close ≥**1% and ≤10%** above resistance; close strength ≥75%; volume ≥previous bar +1%; EMA20 and MACD confirmation on; max technical entry-to-stop 16% |
| **VCP Pre-Breakout** | **Weekly**; SCTR ≥70; RS 3M outperform SPY; latest **3 completed weeks** considered; **pre-breakout only**; base ≥4 bars; final contraction ≤12%; latest/previous range ≤0.80; latest/previous True Range ≤0.95; **volume dry-up ON** with ratio ≤0.90; close to local pivot (within 5%); EMA confirmation on, MACD off |
| **First Pullback EMA 20W** | **Weekly only**; SCTR ≥70; RS 3M outperform SPY; freshness 3; breakout over previous 8-week high by at least 0.5%; ≥3 weeks of uptrend; ≥8% impulse; first EMA20W approach/touch/bounce; ±touch tolerance +2%/−2.5%, WATCH up to +5%; stop offset 0.5%; max technical entry-to-stop 16% |

All preset thresholds are **initial research settings**, not verified optimal trade-entry parameters. The SCTR filter is switched on automatically when the selected stock universe is **Imported SCTR list**. If the user scans a different universe and has not imported SCTR values, the SCTR requirement defaults off.

## Personal presets (no authentication)

1. Choose a recommended preset.
2. Optionally adjust **⚙ Advanced Filters** and/or the quick filters.
3. At the bottom of the form, expand **💾 Salvează propriul profil**, type a name, then click **💾 Salvează profil**.
4. The new profile appears with a `★` prefix under **Alege strategia** (after the next rerun). Select it to restore **all** values.
5. To keep profiles after app restart, use **StockCharts sidebar → 💾 Profiluri personale → Exportă profilurile mele (JSON)**. Import the exported `.json` file later.

Saving to the browser session is **not permanent storage**; the JSON export is needed to persist a personal profile across Streamlit session resets. No login or database is involved.

## Update your existing Streamlit Cloud app

1. Download and extract the ZIP, don't upload the ZIP itself.
2. Go to your existing GitHub repository `OanaSonic/darvas-rs-screener` and use **Add file → Upload files**.
3. **Replace all files as a matched set**: `app.py`, `screener_core.py`, `pullback_core.py`, `hover_chart.py`, `sctr_paste.py`, `requirements.txt`. **Add the new `preset_profiles.py`** at the same root level as `app.py`. Keep `.streamlit/config.toml` or upload it from this ZIP.
4. Commit and reload Streamlit; use **Manage app → Reboot** if it shows an old build.
5. Paste your StockCharts SCTR table, choose `Imported SCTR list`, pick a preset and click **RUN SCREENER**.

`app.py`, `screener_core.py` and `pullback_core.py` still share the **v6.1 engine API version**. Do not mix the new UI with older engine modules.

## Testing

Run `python -m pytest -q` from the extracted repository for unit tests (requires pandas/numpy/pytest). Tests verify recommended values, validation, custom profile export/import, Streamlit widget wiring, and legacy Darvas/VCP/pullback logic. Live Yahoo download and Streamlit Cloud deployment cannot be tested in this offline environment.

## Data and risk caveats

Yahoo Finance OHLCV is delayed/EOD, may be incomplete or rate-limited and adjusts historical prices. StockCharts SCTR copied from a table is a manual snapshot, not a live score. The screener offers signals for further manual verification; it does not place orders or determine a suitable position size. Historical video returns are not reproduced by the app.
