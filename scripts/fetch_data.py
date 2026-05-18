#!/usr/bin/env python3
"""
Retrieve the quarterly U.S. House Statement of Disbursements source files.

The raw files (~1 GB) are intentionally NOT committed to the repository (see
.gitignore); only the cleaned product `all_disbursements.csv` is tracked, via
Git LFS, and a small tracked index `data/SOURCE_MANIFEST.csv` records exactly
which source files the archive contains. This script is the reproducibility
bridge: it documents the canonical source, discovers/pulls every available
quarterly file into ./data/, and (re)writes the manifest.

Canonical primary source
    U.S. House of Representatives — Statement of Disbursements
    https://www.house.gov/the-house-explained/open-government/statement-of-disbursements
    https://www.house.gov/the-house-explained/open-government/statement-of-disbursements/archive
Secondary mirror
    ProPublica — House Office Expenditures
    https://projects.propublica.org/represent/expenditures

The House has used several filename conventions over time
(`YYYYQ#-house-disburse-detail[ only].csv/.xlsx`, and more recently
`MON-MON-YYYY-SOD-DETAIL-GRID-FINAL.csv`). `--discover` scrapes the public
pages, normalizes each detail file to the repo convention
`YYYYQ#-house-disburse-detail[ only].csv`, and downloads anything missing.

Usage
    python scripts/fetch_data.py                 # download the known set
    python scripts/fetch_data.py --discover      # scrape pages for new data
    python scripts/fetch_data.py --verify        # only report presence
    python scripts/fetch_data.py --manifest      # (re)write SOURCE_MANIFEST
    HOUSE_DISBURSE_BASE_URL=... python scripts/fetch_data.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANIFEST = DATA_DIR / "SOURCE_MANIFEST.csv"

SOD_PAGES = [
    "https://www.house.gov/the-house-explained/open-government/statement-of-disbursements",
    "https://www.house.gov/the-house-explained/open-government/statement-of-disbursements/archive",
]
HOST = "https://www.house.gov"
BASE_URL = os.environ.get("HOUSE_DISBURSE_BASE_URL",
                          "https://disbursements.house.gov/data/")
UA = {"User-Agent": "Mozilla/5.0 (compatible; sod-archive-bot/1.0)"}

_MONTHS_Q = {("JAN", "MAR"): 1, ("APR", "JUN"): 2,
             ("JUL", "SEP"): 3, ("OCT", "DEC"): 4}


def expected_files() -> list[str]:
    """The known/pinned source set (2010Q1..2024Q4 csv + 2025Q1/Q2 xlsx)."""
    names = []
    for year in range(2010, 2025):
        for q in range(1, 5):
            suffix = " only" if year >= 2023 else ""
            names.append(f"{year}Q{q}-house-disburse-detail{suffix}.csv")
    names.append("2025Q1-house-disburse-details only.xlsx")
    names.append("2025Q2-house-disburse-details only.xlsx")
    return names


def _repo_name(year: int, q: int) -> str:
    suffix = " only" if year >= 2023 else ""
    return f"{year}Q{q}-house-disburse-detail{suffix}.csv"


def _period_from_href(href: str) -> tuple[int, int] | None:
    """Map a House detail-file URL to (year, quarter), or None."""
    m = re.search(r"(20\d\d)Q([1-4])", href)
    if m:
        return int(m.group(1)), int(m.group(2))
    # MON-MON-YYYY-SOD-DETAIL-GRID...
    m = re.search(r"([A-Z]{3})-([A-Z]{3})-(20\d\d)", href.upper())
    if m and (m.group(1), m.group(2)) in _MONTHS_Q:
        return int(m.group(3)), _MONTHS_Q[(m.group(1), m.group(2))]
    return None


def discover() -> dict[str, str]:
    """Scrape the SoD pages -> {repo_filename: absolute_url} for detail files."""
    found: dict[str, str] = {}
    for page in SOD_PAGES:
        try:
            req = urllib.request.Request(page, headers=UA)
            html = urllib.request.urlopen(req, timeout=60).read().decode(
                "utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            print(f"  !! could not read {page}: {exc}")
            continue
        for href in re.findall(r'href=["\']([^"\']+)["\']', html):
            low = href.lower()
            is_detail = ("sod-detail" in low or "disburse-detail" in low
                         or re.search(r"20\d\dq[1-4]", low))
            if not (is_detail and low.split("?")[0].endswith(
                    (".csv", ".xlsx"))):
                continue
            url = href if href.startswith("http") else HOST + href
            period = _period_from_href(href)
            name = (_repo_name(*period) if period
                    else os.path.basename(href.split("?")[0]))
            found.setdefault(name, url)
    return found


def _download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r, \
                open(dest, "wb") as fh:
            fh.write(r.read())
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  !! failed {url} ({exc})")
        if dest.exists():
            dest.unlink()
        return False


def download(use_discovery: bool) -> list[str]:
    DATA_DIR.mkdir(exist_ok=True)
    added: list[str] = []
    targets: dict[str, str] = {}
    if use_discovery:
        targets = discover()
        print(f"discovered {len(targets)} detail files on house.gov")
    else:
        for name in expected_files():
            targets[name] = (BASE_URL.rstrip("/") + "/"
                             + urllib.request.quote(name))
    for name, url in sorted(targets.items()):
        dest = DATA_DIR / name
        if dest.exists():
            continue
        print(f"downloading {name}")
        if _download(url, dest):
            added.append(name)
        else:
            print(f"  -> retrieve manually from {SOD_PAGES[0]}")
    return added


def write_manifest() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    rows = []
    for p in sorted(DATA_DIR.glob("*.csv")) + sorted(DATA_DIR.glob("*.xlsx")):
        if p.name == MANIFEST.name:
            continue
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        rows.append((p.name, p.stat().st_size, h.hexdigest()))
    with open(MANIFEST, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "size_bytes", "sha256"])
        w.writerows(rows)
    print(f"wrote {MANIFEST} ({len(rows)} source files indexed)")


def verify() -> bool:
    DATA_DIR.mkdir(exist_ok=True)
    present = [n for n in expected_files() if (DATA_DIR / n).exists()]
    missing = [n for n in expected_files() if not (DATA_DIR / n).exists()]
    extra = sorted(
        p.name for p in DATA_DIR.glob("*")
        if p.suffix in (".csv", ".xlsx") and p.name != MANIFEST.name
        and p.name not in expected_files())
    print(f"data dir : {DATA_DIR}")
    print(f"pinned   : {len(present)}/{len(expected_files())} present")
    if missing:
        print(f"missing  : {missing}")
    if extra:
        print(f"newly available (not yet pinned in cleaning.ipynb): {extra}")
    return not missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--discover", action="store_true",
                    help="scrape house.gov for new/updated detail files")
    ap.add_argument("--verify", action="store_true",
                    help="only report which expected files are present")
    ap.add_argument("--manifest", action="store_true",
                    help="(re)write data/SOURCE_MANIFEST.csv and exit")
    args = ap.parse_args()

    if args.manifest:
        write_manifest()
        return 0
    if not args.verify:
        added = download(use_discovery=args.discover)
        print(f"added {len(added)} file(s): {added}" if added
              else "no new files")
        write_manifest()
    ok = verify()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
