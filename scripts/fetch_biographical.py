#!/usr/bin/env python3
"""
Retrieve the biographical / reference inputs that `analysis.ipynb` enriches the
cleaned disbursements with. Per the project's notebook discipline these network
pulls live in a script, not in the notebook, so `analysis.ipynb` runs from
local cached files and stays reproducible offline.

Outputs (written to the repository root, all .gitignored):

  propublica_members.csv      member roster: id, gender, party, first_name,
                              last_name. Built from the canonical
                              congress-legislators project (the legacy
                              ProPublica Congress API this file is named after
                              has been retired / returns HTTP 410).
  legislators-historical.csv  raw congress-legislators historical roster.
  census_state.txt            Census ANSI state codes.
  census_cenpop2020.csv       Census 2020 centers of population (per state).
  member_data_2015_2023.csv   House Clerk MemberData.xml (office building/room)
                              for 2015..2023, via the Wayback Machine
                              (best-effort; archive.org can be slow/flaky).

Canonical sources
  congress-legislators : https://unitedstates.github.io/congress-legislators/
  Census centers of pop: https://www.census.gov/geographies/reference-files/
                          time-series/geo/centers-population.html
  House Clerk MemberData (snapshotted): https://clerk.house.gov/xml/lists/

Usage
    python scripts/fetch_biographical.py            # fetch all (skip existing)
    python scripts/fetch_biographical.py --force    # re-fetch everything
    python scripts/fetch_biographical.py --skip-wayback
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

LEG_HIST = "https://unitedstates.github.io/congress-legislators/legislators-historical.csv"
LEG_CURR = "https://unitedstates.github.io/congress-legislators/legislators-current.csv"
CENSUS_STATE = "https://www2.census.gov/geo/docs/reference/state.txt"
CENSUS_CENPOP = ("https://www2.census.gov/geo/docs/reference/cenpop2020/"
                 "CenPop2020_Mean_ST.txt")


def _write(df: pd.DataFrame, name: str) -> None:
    out = ROOT / name
    df.to_csv(out, index=False, encoding="utf8")
    print(f"wrote {out}  ({len(df):,} rows)")


def fetch_legislators(force: bool) -> None:
    hist_path = ROOT / "legislators-historical.csv"
    pp_path = ROOT / "propublica_members.csv"
    if pp_path.exists() and hist_path.exists() and not force:
        print("legislators: cached, skipping")
        return
    hist = pd.read_csv(LEG_HIST, dtype=str)
    curr = pd.read_csv(LEG_CURR, dtype=str)
    hist.to_csv(hist_path, index=False, encoding="utf8")
    print(f"wrote {hist_path}  ({len(hist):,} rows)")

    # Build the propublica_members.csv schema analysis.ipynb expects
    # (columns: id, gender, party, first_name, last_name) from the canonical,
    # still-maintained congress-legislators roster instead of the retired API.
    both = pd.concat([curr, hist], ignore_index=True)
    members = both[
        ["bioguide_id", "gender", "party", "first_name", "last_name", "type", "district", "state"]
    ].dropna(subset=["bioguide_id"]).drop_duplicates(subset=["bioguide_id"])
    _write(members, "propublica_members.csv")


def fetch_census(force: bool) -> None:
    s_path = ROOT / "census_state.txt"
    c_path = ROOT / "census_cenpop2020.csv"
    if s_path.exists() and c_path.exists() and not force:
        print("census: cached, skipping")
        return
    pd.read_csv(CENSUS_STATE, sep="|", dtype=str).to_csv(
        s_path, sep="|", index=False)
    print(f"wrote {s_path}")
    pd.read_csv(CENSUS_CENPOP, dtype=str).to_csv(c_path, index=False)
    print(f"wrote {c_path}")


def fetch_member_data(force: bool) -> None:
    out = ROOT / "member_data_2015_2023.csv"
    if out.exists() and not force:
        print("member_data: cached, skipping")
        return
    import requests
    from bs4 import BeautifulSoup

    frames = {}
    avail = "http://archive.org/wayback/available?url=https://clerk.house.gov/xml/lists/MemberData.xml&timestamp={0}0201"
    content = "https://web.archive.org/web/{0}if_/https://clerk.house.gov/xml/lists/MemberData.xml"
    for year in range(2015, 2024):
        try:
            snap = requests.get(avail.format(year), timeout=60).json()
            ts = snap["archived_snapshots"]["closest"]["timestamp"]
            text = requests.get(content.format(ts), timeout=120).text
            df = pd.read_xml(text, xpath="./members/*/member-info",
                             parser="lxml")
            df["congress-num"] = BeautifulSoup(text, "lxml").find_all(
                "congress-num")[0].text
            frames[year] = df
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {year}: {exc}")
    if not frames:
        # archive.org unreachable: fall back to the LIVE House Clerk snapshot
        # so a valid (current-Congress) member_data file still exists. Office
        # building/room are stable enough that this keeps analysis.ipynb
        # runnable; re-run with archive.org reachable for full 2015-2023 history.
        import io
        import re
        try:
            text = requests.get(
                "https://clerk.house.gov/xml/lists/MemberData.xml",
                timeout=120).text
            df = pd.read_xml(io.StringIO(text),
                             xpath="./members/*/member-info", parser="lxml")
            cnum = re.search(r"<congress-num>(\d+)", text)
            df["congress-num"] = cnum.group(1) if cnum else ""
            frames[2000 + int(df["congress-num"].iloc[0]) - 107] = df
            print("member_data: archive.org unreachable; used live "
                  "clerk.house.gov snapshot (current Congress only)")
        except Exception as exc:  # noqa: BLE001
            print(f"member_data: no source reachable ({exc})")
            return
    md = pd.concat(frames, names=["year"]).reset_index(0)
    md.to_csv(out, index=False, encoding="utf8")
    print(f"wrote {out}  ({len(md):,} rows)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-wayback", action="store_true",
                    help="skip the slow/flaky archive.org member-data pull")
    args = ap.parse_args()
    fetch_legislators(args.force)
    fetch_census(args.force)
    if not args.skip_wayback:
        fetch_member_data(args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
