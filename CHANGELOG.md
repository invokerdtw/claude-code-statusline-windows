# Changelog

## 1.0.0 — 2026-10-08

First public release.

- Three colour-coded bars (context, 5-hour, 7-day), each cell coloured by the percentage it represents (65% yellow, 85% red, adjustable)
- Reset countdowns (`4h23m`, `5d12h`), prompt-cache expiry time, session duration, lines changed
- Model name follows `/model` even when the status-line input lags behind; names are derived from the model id, so new models need no update
- Git branch read from `.git/HEAD`; dirty flag cached for 5 seconds; no git process at all on Google Drive / OneDrive folders
- Cached limits are dropped when the account changes (plan + hashed account ID) or when the window has already reset
- Optional burn rate (tokens/min via ccusage) and optional cost display
- `install.py` with backup, `--dry-run` and `--uninstall`; unit + end-to-end tests; mock scenarios and SVG previews
