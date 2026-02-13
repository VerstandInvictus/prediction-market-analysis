"""Targeted fetch of NBA and NCAAM game-winner markets from Kalshi API.

Instead of crawling millions of markets across all categories, this uses
the series_ticker API filter to fetch only basketball game-winner markets.
Results are saved in the same format as the general markets indexer so the
existing trades indexer can pick them up.

Usage:
    uv run scripts/fetch_basketball.py

After running this, fetch trades for the new markets:
    uv run main.py index kalshi_trades
"""

from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

# Ensure project root is on the path so `src.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
from tqdm import tqdm

from src.common.storage import ParquetStorage
from src.indexers.kalshi.client import KalshiClient
from src.indexers.kalshi.models import Market

DATA_DIR = Path("data/kalshi/markets")

# Series tickers for basketball game-winner markets
BASKETBALL_SERIES = [
    "KXNBAGAME",
    "KXNCAAMBGAME",
]


def get_existing_tickers() -> set[str]:
    """Get all tickers already in the markets parquet files."""
    pattern = str(DATA_DIR / "markets_*_*.parquet")
    try:
        rows = duckdb.sql(f"SELECT DISTINCT ticker FROM '{pattern}'").fetchall()
        return {row[0] for row in rows}
    except Exception:
        return set()


def fetch_series_markets(
    client: KalshiClient,
    series_ticker: str,
    existing_tickers: set[str],
) -> list[Market]:
    """Fetch all markets for a given series_ticker, skipping already-known tickers."""
    new_markets: list[Market] = []
    cursor: Optional[str] = None
    page = 0

    pbar = tqdm(desc=f"Fetching {series_ticker}", unit=" markets")

    while True:
        params: dict = {"limit": 200, "series_ticker": series_ticker}
        if cursor:
            params["cursor"] = cursor

        data = client._get("/markets", params=params)

        markets = [Market.from_dict(m) for m in data.get("markets", [])]
        if not markets:
            break

        for m in markets:
            if m.ticker not in existing_tickers:
                new_markets.append(m)
                existing_tickers.add(m.ticker)

        pbar.update(len(markets))
        page += 1

        cursor = data.get("cursor")
        if not cursor:
            break

        time.sleep(0.5)  # ~2 req/s to stay under Kalshi rate limit

    pbar.close()
    return new_markets


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Scanning existing market data...")
    existing = get_existing_tickers()
    print(f"Found {len(existing)} existing tickers in parquet files\n")

    client = KalshiClient()
    storage = ParquetStorage(data_dir=DATA_DIR)

    total_new = 0
    for series in BASKETBALL_SERIES:
        new_markets = fetch_series_markets(client, series, existing)
        if new_markets:
            stored = storage.append_markets(new_markets)
            print(f"  {series}: {len(new_markets)} new markets saved (total in storage: {stored})")
            total_new += len(new_markets)
        else:
            print(f"  {series}: all markets already present")

    client.close()

    print(f"\nDone. {total_new} new basketball markets added.")
    if total_new > 0:
        print("\nNext step: fetch trades for these markets:")
        print("  uv run main.py index kalshi_trades")


if __name__ == "__main__":
    main()
