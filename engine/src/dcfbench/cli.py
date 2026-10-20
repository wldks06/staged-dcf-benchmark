"""Command line entry point: python -m dcfbench.cli <command>.

Commands that fetch write into a snapshot. Everything else reads snapshots only.

    python -m dcfbench.cli snapshot-us --snapshot snap-2026-10-05-a --universe both
    python -m dcfbench.cli snapshot-info --snapshot snap-2026-10-05-a --verify
    python -m dcfbench.cli generate-us --snapshot snap-2026-10-05-a --universe sector --version v1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

DEFAULT_DATES = ["2019-12-31", "2022-12-31", "2025-12-31"]


def _dates(values: list[str]) -> list[date]:
    return [date.fromisoformat(v) for v in values]


def cmd_snapshot_us(args: argparse.Namespace) -> int:
    from .data import edgar, universe
    from .data.snapshot import Snapshot

    dates = _dates(args.dates)
    with Snapshot(args.snapshot, readonly=False) as snap:
        tickers: set[str] = set()
        if args.universe in ("sp100", "both"):
            wiki = universe.wiki_http()
            for day in dates:
                members = universe.fetch_sp100(snap, wiki, day)
                print(f"S&P 100 as of {day}: {len(members)} tickers")
                tickers.update(universe.current_ticker(member.ticker) for member in members)
        if args.universe in ("sector", "both"):
            seeds = universe.load_us_sector_seed()
            print(f"sector pool: {len(seeds)} tickers, {len({s.gics_sector for s in seeds})} GICS sectors")
            tickers.update(seed.ticker for seed in seeds)
        http = edgar.sec_http()
        ticker_map = edgar.fetch_ticker_map(snap, http)
        todo = sorted(tickers)[: args.limit] if args.limit else sorted(tickers)
        ciks = {t: universe.cik_for(t, ticker_map) for t in todo}
        missing = [t for t, cik in ciks.items() if cik is None]
        if missing:
            print(f"no SEC listing for {len(missing)} tickers (delisted): {', '.join(missing)}")
        for i, cik in enumerate(sorted({c for c in ciks.values() if c})):
            edgar.fetch_company(snap, http, cik)
            if (i + 1) % 20 == 0:
                print(f"  EDGAR {i + 1} companies, {http.requests_made} requests so far")
        print(f"EDGAR done: {http.requests_made} requests, snapshot {snap.snapshot_id} has "
              f"{len(snap.keys('edgar/companyfacts/'))} company fact files")

        from .data import damodaran, fred, prices

        fred_http = fred.fred_http()
        for series_id in (*fred.US_SERIES, *fred.OAS_SERIES.values()):
            fred.fetch_series(snap, fred_http, series_id)
        print(f"FRED done: {len(snap.keys('fred/'))} series")

        dam_http = damodaran.damodaran_http()
        damodaran.fetch_common(snap, dam_http)
        for day in dates:
            damodaran.fetch_betas(snap, dam_http, damodaran.january_year(day))
        print(f"Damodaran done: {len(snap.keys('damodaran/'))} files")

        no_price = []
        for symbol in (t for t in todo if ciks[t]):
            if not prices.fetch_prices(snap, symbol):
                no_price.append(symbol)
        print(f"prices done: {len(snap.keys('prices/'))} symbols"
              + (f", none for {', '.join(no_price)}" if no_price else ""))
    return 0


def cmd_generate_us(args: argparse.Namespace) -> int:
    from . import generate
    from .config import CASES_DIR
    from .data.snapshot import Snapshot

    snap = Snapshot(args.snapshot)  # read-only: generation never touches the network
    result = generate.generate_us(snap, _dates(args.dates), universe_rule=args.universe,
                                  per_sector=args.per_sector)
    out_dir = CASES_DIR / args.version / "us"
    summary = generate.write_run(result, out_dir)
    print(json.dumps(summary, indent=1))
    print(f"written to {out_dir}")
    return 0


def cmd_snapshot_info(args: argparse.Namespace) -> int:
    from .data.snapshot import Snapshot

    snap = Snapshot(args.snapshot, readonly=not args.freeze)
    groups: dict[str, list[int]] = {}
    for key in snap.keys():
        groups.setdefault(key.split("/")[0], []).append(snap.entry(key)["bytes"])
    print(f"snapshot {snap.snapshot_id}: {len(snap.keys())} payloads, "
          f"{'frozen' if snap.frozen else 'not frozen'}")
    for group, sizes in sorted(groups.items()):
        print(f"  {group:12s} {len(sizes):5d} payloads {sum(sizes) / 1e6:9.1f} MB uncompressed")
    if args.verify:
        bad = snap.verify()
        print("  hashes: all match" if not bad else f"  hashes: {len(bad)} MISMATCH: {bad[:5]}")
    if args.freeze:
        snap.freeze()
        print("  frozen: no further writes are accepted, make a new snapshot id for new data")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dcfbench", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot-us", help="pull the US universe (S&P 100 membership, the sector pool) and SEC data into a snapshot")
    p.add_argument("--snapshot", required=True, help="snapshot id, for example snap-2026-09-30-a")
    p.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    p.add_argument("--universe", choices=["sp100", "sector", "both"], default="both",
                   help="which companies to pull: S&P 100 members, the GICS sector pool, or both (default)")
    p.add_argument("--limit", type=int, default=0, help="only the first N tickers (for a dry run)")
    p.set_defaults(func=cmd_snapshot_us)

    p = sub.add_parser("snapshot-info", help="what a snapshot holds, optionally verify or freeze")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--verify", action="store_true", help="check every payload against its hash")
    p.add_argument("--freeze", action="store_true", help="make the snapshot read-only for good")
    p.set_defaults(func=cmd_snapshot_info)

    p = sub.add_parser("generate-us", help="build US cases from a snapshot (no network)")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    p.add_argument("--version", default="v0")
    p.add_argument("--universe", choices=["sp100", "sector"], default="sp100",
                   help="sp100: index members on each date (version zero); sector: the largest per GICS sector")
    p.add_argument("--per-sector", type=int, default=5, help="companies kept per sector and date under the sector rule")
    p.set_defaults(func=cmd_generate_us)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
