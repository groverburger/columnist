# Tools

This folder contains support utilities that are useful around the Columnist
project but are not part of the viewer runtime or packaged desktop app.

## `pnf_columns.py`

`pnf_columns.py` is an importable library and CLI for extracting Point-and-Figure
columns from ticker data. It is intended for AI-agent workflows, quick terminal
checks, and standalone analysis.

Run it from the repository root:

```bash
python tools/pnf_columns.py AAPL 0.02
python tools/pnf_columns.py AAPL 0.02 --period 5y --json
```

The box size is a decimal fraction, so `0.02` means `2%`.
