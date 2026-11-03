# Darvas RS Screener v8.1 — ImportError fix (single-file hotfix)

## Problem
If a v8 app.py is paired with an earlier preset_profiles.py, Streamlit can fail at the initial `from preset_profiles import ...` with ImportError.

## Correction
`app.py` now includes the preset definitions and helpers internally. It does **not** import preset_profiles.py, so the previous file can be left in GitHub. All previously implemented filters, import SCTR, full imported-universe option, and dark contrast changes are preserved.

## Easy installation — only one file
1. Open the GitHub repository root.
2. Open `app.py`, choose **Edit this file** (pencil icon), replace its content with the new app.py, and **Commit changes**. Or use Add file -> Upload files and upload the new app.py, replacing the existing file.
3. Wait for Streamlit to redeploy or use Manage app -> Reboot app.
4. Do not change any other file. In particular, an old preset_profiles.py can remain and does not affect app.py anymore.

## Notes
- Imported SCTR is a manual snapshot and may need to be pasted again after a session restart.
- StockPrices (Yahoo Finance) are delayed/EOD; outputs are not validated trading recommendations.
- This patch prevents the preset_profiles import mismatch; it does not claim to fix unrelated failures if underlying APIs or files change.
