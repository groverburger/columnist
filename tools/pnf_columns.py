#!/usr/bin/env python3
"""
pnf_columns - Point-and-Figure column extractor

Importable library and command-line tool. Given a ticker and a box size,
returns the list of PnF columns with direction, price range, and date range.

Library usage:
    from pnf_columns import get_columns, compute_columns

    # Fetch and compute in one call (requires yfinance):
    cols = get_columns("AAPL", 0.02, reversal=3, period="2y")

    # Or compute from your own OHLC data (no network / no deps):
    cols = compute_columns(ohlc_bars, box_size=0.02, reversal=3)

CLI usage:
    python pnf_columns.py AAPL 0.02
    python pnf_columns.py AAPL 0.02 --reversal 3 --period 5y
    python pnf_columns.py AAPL 0.02 --start 2022-01-01 --end 2024-01-01 --json

Box size is expressed as a decimal fraction: 0.02 means 2%.
"""

import argparse
import json
import sys


def _round4(x):
    return round(x * 10000) / 10000


def compute_columns(ohlc, box_size, reversal=3):
    """Compute Point-and-Figure columns from a list of OHLC bars.

    Args:
        ohlc: sequence of dicts with keys 'date' (YYYY-MM-DD str),
            'high', 'low', 'close'.
        box_size: box size as a decimal fraction (e.g. 0.02 for 2%).
        reversal: number of boxes required to reverse direction.

    Returns:
        List of column dicts, each with:
            direction: 'X' (ascending) or 'O' (descending)
            high: highest price in the column
            low: lowest price in the column
            start_date: date the column began (YYYY-MM-DD)
            end_date: date the last box was added (YYYY-MM-DD)
    """
    if not ohlc:
        return []
    if box_size <= 0:
        raise ValueError("box_size must be positive")
    if reversal < 1:
        raise ValueError("reversal must be >= 1")

    bs = float(box_size)
    rs = int(reversal)

    def inc(p, n=1):
        for _ in range(n):
            p = _round4(p * (1 + bs))
        return p

    def dec(p, n=1):
        for _ in range(n):
            p = _round4(p / (1 + bs))
        return p

    first_close = float(ohlc[0]['close'])
    first_date = ohlc[0]['date']

    cols = [[first_close]]
    start_dates = [first_date]
    end_dates = [first_date]
    dirs = ['up']

    bp = 100.0
    while first_close > bp:
        bp = inc(bp)
    while first_close < bp:
        bp = dec(bp)

    state = {'direction': 'up', 'bp': bp}

    def fill_up(price, cur_date):
        filled = False
        while price >= inc(state['bp']):
            state['bp'] = inc(state['bp'])
            cols[-1].append(state['bp'])
            end_dates[-1] = cur_date
            filled = True
        return filled

    def fill_down(price, cur_date):
        filled = False
        while price <= dec(state['bp']):
            state['bp'] = dec(state['bp'])
            cols[-1].append(state['bp'])
            end_dates[-1] = cur_date
            filled = True
        return filled

    for bar in ohlc:
        cur_date = bar['date']
        h = float(bar['high'])
        l = float(bar['low'])

        if state['direction'] == 'up':
            if fill_up(h, cur_date):
                continue
            if l <= dec(state['bp'], rs):
                state['direction'] = 'down'
                dirs.append('down')
                cols.append([])
                start_dates.append(cur_date)
                end_dates.append(cur_date)
                fill_down(l, cur_date)
                continue

        if state['direction'] == 'down':
            if fill_down(l, cur_date):
                continue
            if h >= inc(state['bp'], rs):
                state['direction'] = 'up'
                dirs.append('up')
                cols.append([])
                start_dates.append(cur_date)
                end_dates.append(cur_date)
                fill_up(h, cur_date)
                continue

    result = []
    for i, col in enumerate(cols):
        if not col:
            continue
        result.append({
            'direction': 'X' if dirs[i] == 'up' else 'O',
            'high': round(max(col), 6),
            'low': round(min(col), 6),
            'start_date': start_dates[i],
            'end_date': end_dates[i],
        })
    return result


def fetch_ohlc(ticker, start=None, end=None, period=None):
    """Fetch daily OHLC bars from Yahoo Finance via yfinance.

    Returns a list of dicts with keys 'date', 'high', 'low', 'close'.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError as e:
        raise ImportError("yfinance is required: pip install yfinance") from e

    kwargs = {'progress': False, 'auto_adjust': True}
    if period:
        kwargs['period'] = period
    else:
        if start:
            kwargs['start'] = start
        if end:
            kwargs['end'] = end
        if not start and not end:
            kwargs['period'] = '2y'

    df = yf.download(ticker, **kwargs)
    if df.empty:
        raise ValueError(f"No data found for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    needed = ['High', 'Low', 'Close']
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns from yfinance response: {missing}")

    df = df[needed].dropna()
    return [
        {
            'date': idx.strftime('%Y-%m-%d'),
            'high': round(float(row['High']), 6),
            'low': round(float(row['Low']), 6),
            'close': round(float(row['Close']), 6),
        }
        for idx, row in df.iterrows()
    ]


def get_columns(ticker, box_size, reversal=3, start=None, end=None, period=None):
    """Fetch a ticker and return its PnF columns in one call.

    Convenience wrapper around fetch_ohlc + compute_columns.
    """
    ohlc = fetch_ohlc(ticker, start=start, end=end, period=period)
    return compute_columns(ohlc, box_size, reversal=reversal)


def _print_table(ticker, box_size, reversal, cols):
    print(f"{ticker.upper()}  box={box_size:g}  reversal={reversal}  columns={len(cols)}")
    header = f"{'#':>4}  {'Dir':>3}  {'High':>12}  {'Low':>12}  {'Start':>10}  {'End':>10}"
    print(header)
    print('-' * len(header))
    for i, c in enumerate(cols, 1):
        print(f"{i:>4}  {c['direction']:>3}  {c['high']:>12.4f}  {c['low']:>12.4f}  "
              f"{c['start_date']:>10}  {c['end_date']:>10}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compute Point-and-Figure columns for a ticker.",
    )
    parser.add_argument('ticker', help="Ticker symbol (e.g. AAPL)")
    parser.add_argument('box_size', type=float,
                        help="Box size as a decimal fraction (e.g. 0.02 for 2%%)")
    parser.add_argument('-r', '--reversal', type=int, default=3,
                        help="Reversal count in boxes (default: 3)")
    parser.add_argument('-p', '--period', default=None,
                        help="yfinance period string (e.g. 1y, 2y, 5y, max). "
                             "Defaults to 2y if no start/end given.")
    parser.add_argument('--start', default=None, help="Start date YYYY-MM-DD")
    parser.add_argument('--end', default=None, help="End date YYYY-MM-DD")
    parser.add_argument('--json', action='store_true',
                        help="Emit JSON instead of a formatted table")
    args = parser.parse_args(argv)

    try:
        cols = get_columns(
            args.ticker,
            args.box_size,
            reversal=args.reversal,
            start=args.start,
            end=args.end,
            period=args.period,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(cols, indent=2))
    elif not cols:
        print("No columns")
    else:
        _print_table(args.ticker, args.box_size, args.reversal, cols)
    return 0


if __name__ == '__main__':
    sys.exit(main())
