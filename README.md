# exploratory-data-auditing

Code for cleaning and reproducing the analyses in the *Harvard Data Science
Review* article on **Exploratory Data Auditing**, applied to ~15 years of the
U.S. House of Representatives
[Statement of Disbursements](https://www.house.gov/the-house-explained/open-government/statement-of-disbursements)
(SoD) — the quarterly public record of every payment made from House
appropriations.

The repository is a **reproducibility trust contract**: a reader who clones it
can retrieve the same source data, re-run the notebooks from a fresh kernel,
and obtain the same numbers the article reports.

---

## Project layout

```
exploratory-data-auditing/
├── cleaning.ipynb              schema normalization + validation
│                               → writes data/all_disbursements.csv
├── analysis_v3.ipynb           anomaly analysis (consumes the cleaned data)
├── data/                       data root (mostly gitignored — see .gitignore)
│   ├── SOURCE_MANIFEST.csv     tracked index: filename, size, sha256
│   ├── disbursements/          raw quarterly source files (gitignored, ~1 GB)
│   ├── all_disbursements.csv   cleaned product (gitignored, ~1.2 GB)
│   ├── propublica_members.csv  member id → gender / party / name
│   ├── legislators-historical.csv  congress-legislators historical roster
│   ├── census_state.txt        Census ANSI state codes
│   ├── census_cenpop2020.csv   Census 2020 centers of population
│   ├── member_data_2015_2023.csv  House Clerk office building/room
│   ├── personnel_bp.gexf       bipartite member↔payee personnel network
│   └── personnel_proj.gexf     member-projection of the personnel network
├── images/                     figures produced by analysis_v3.ipynb
├── scripts/
│   ├── fetch_data.py           retrieve / discover raw disbursement files
│   └── fetch_biographical.py   enrichment + reference inputs
├── .github/workflows/
│   └── fetch-disbursements.yml annual (Jan 6) data-refresh automation
├── requirements.txt            pinned Python environment
├── .gitattributes              Git LFS rule for all_disbursements.csv
├── .gitignore                  raw data / cleaned product / caches excluded
├── LICENSE                     MIT
└── README.md                   this file
```

The data pipeline is strictly one-directional:

```
data/disbursements/*.{csv,xlsx}  ──cleaning.ipynb──▶  data/all_disbursements.csv  ──analysis_v3.ipynb──▶  images/ + GEXF
        (62 raw files)              normalize+validate       (19-col contract)            anomaly tests
```

`analysis_v3.ipynb` performs **no** schema normalization or datetime parsing —
that is exclusively `cleaning.ipynb`'s contract.

---

## Notebooks

### `cleaning.ipynb` — schema normalization & validation

Reads every quarterly file under `data/disbursements/`, normalizes four
historical schema eras plus two single-quarter transitional schemas into one
common 19-column schema, validates it, and writes
`data/all_disbursements.csv`. Section by section:

| Section | What it does |
|---|---|
| **Title** | Provenance, scope, pinned-numbers contract (one `#` H1, byline, MIT). |
| **Imports** | Single imports cell; no plotting, no network I/O. |
| **Configuration & provenance** | `DATA_DIR`, `EXPECTED_QUARTERS` (58), `EXCLUDED_QUARTERS` (2010), `schema_era()` dispatch, the schema-era reference table. |
| **File discovery** | Globs `data/disbursements/`, parses the `YYYYQ#` key, asserts all 62 source files present. |
| **Common-schema contract** | `ADAPTER_COLUMNS` (15) / `COMMON_COLUMNS` (19); `validate_schema()` asserted by every adapter and the final frame. |
| **Raw read helper & parsers** | `read_raw` (latin1/xlsx, header-whitespace strip, unnamed-column drop), `_to_amount`, `_to_dt` (explicit formats only — no dateutil OOB), `_to_txn_date` (reconstructs the year-less `MM-DD`/`DD-Mon` dates of 2011–2016), `_drop_total_rows`. |
| **Per-schema adapters A–E** | One adapter per era; every domain-knowledge fix from the original notebook preserved as an explicit, commented, **asserted** step (Schema-1 no-totals proof; the 2017Q2 three-column positional shift; the 2018Q2 mini-schema; the 2022Q4 overhaul; the 2023–2025 office-level Schema 3 with `BIOGUIDE_ID` null). |
| **Adapter dispatch & run** | Loops the 58 quarters, records raw row counts, concatenates. |
| **Derived columns** | `CATEGORY` normalization; Congress-derived `TERM_QUARTER` (1–8); `PERIOD_DATE` / `DATE_IS_RECONSTRUCTED`. |
| **Integrity checks** | Asserted: quarter coverage, power-of-two truncation watch, AMOUNT numeric, date ranges/types, `BIOGUIDE_ID` null audit, category consistency, totals removal, the 2017Q2 shift correctness, full contract conformance. |
| **Pinned headline numbers** | Hard-asserts the 58/6,233,106/6,040,756/192,350/$20.17 B figures — a loud, intentional failure if the source shifts. |
| **Write cleaned output** | Writes `data/all_disbursements.csv` and round-trips it (shape, columns, datetime dtypes). |

**Common schema (`data/all_disbursements.csv`, 19 columns):**
`YEAR-QUARTER, YEAR, QUARTER, TERM_QUARTER, BIOGUIDE_ID, OFFICE, PROGRAM,
CATEGORY, PAYEE, PURPOSE, AMOUNT, DATE, PERIOD_DATE, DATE_IS_RECONSTRUCTED,
START DATE, END DATE, TRANSCODE, RECORDID, VOUCHER_ID`.

### `analysis_v3.ipynb` — anomaly analysis

Consumes `data/all_disbursements.csv` (plus locally-cached enrichment inputs
in `data/`) and runs the *Exploratory Data Auditing* test battery. Front
matter: title + `## External inputs` provenance, single imports cell, the
cleaned-data load with an **integration-contract assertion** (column set,
datetime dtypes, 2011 start), and the `members_df` filter scoped to 2011–2022
(Decision 3). The analytic body (preserved as authored — Decision 4) covers:

- **Continuous anomalies** — personnel-compensation outliers, last-digit /
  pre- vs post-decimal distributions, **Benford's law** by category, by
  member, and by member×category, relative-size-factor ratios.
- **Categorical anomalies** — expense-count distributions, spending by
  **gender** and by **party** (χ² and t-tests).
- **Temporal anomalies** — travel pre-billing (`DATE − START DATE`), the
  COVID-19 spending shock, pandemic impact by member, quarterly /
  term-quarterly cyclicality, inter-event timing.
- **Spatial anomalies** — travel vs. distance-to-DC (Census centers of
  population).
- **Network analysis** — the member↔payee bipartite personnel network and its
  projection, exported as `data/personnel_bp.gexf` and
  `data/personnel_proj.gexf`, with payee-name normalization.

All figures are written to `images/` (Benford panels, personnel-compensation
outliers, decimal/digit distributions, two-largest ratios, categorical
profiles, gender / party / term-quarter spending, COVID temporal,
inter-event timing, travel-distance).

Analysis-specific transforms (personnel payee-name normalization,
gender/party/office enrichment, per-test statistical subsetting) deliberately
remain in this notebook.

---

## Scripts

### `scripts/fetch_data.py`

Retrieves the raw quarterly SoD files (the ~1 GB that is *not* committed) and
maintains the tracked archive index.

- *(default)* download the known pinned source set into `data/disbursements/`.
- `--discover` — scrape the canonical House
  [SoD](https://www.house.gov/the-house-explained/open-government/statement-of-disbursements)
  and [archive](https://www.house.gov/the-house-explained/open-government/statement-of-disbursements/archive)
  pages, normalize any new period (incl. the newer
  `MON-MON-YYYY-SOD-DETAIL-GRID-FINAL.csv` convention) to the repo filename
  convention, and download what is missing.
- `--manifest` — (re)write `data/SOURCE_MANIFEST.csv` (filename, size,
  sha256 of every source file).
- `--verify` — report which expected files are present and flag newly
  available quarters not yet pinned in `cleaning.ipynb`.

### `scripts/fetch_biographical.py`

Produces the enrichment / reference inputs that `analysis_v3.ipynb` reads
from `data/`, so the notebook is reproducible offline (network retrieval
stays out of the notebook per the project's notebook discipline):

- `data/propublica_members.csv` — member `id → gender / party / name`, built
  from the canonical, still-maintained
  [congress-legislators](https://unitedstates.github.io/congress-legislators/)
  roster (the legacy ProPublica Congress API this file is named after returns
  HTTP 410 / has been retired).
- `data/legislators-historical.csv` — raw congress-legislators historical
  roster.
- `data/census_state.txt`, `data/census_cenpop2020.csv` — Census ANSI state
  codes and 2020
  [centers of population](https://www.census.gov/geographies/reference-files/time-series/geo/centers-population.html).
- `data/member_data_2015_2023.csv` — House Clerk `MemberData.xml` office
  building/room via the Wayback Machine, with a **live clerk.house.gov
  fallback** so a valid file always exists.

Flags: `--force` (re-fetch), `--skip-wayback` (skip the slow archive.org pull).

### Automation — `.github/workflows/fetch-disbursements.yml`

Runs every **January 6** (`cron: "0 6 6 1 *"`) and on manual dispatch. By
January the prior calendar year's quarterly SoD files are published. The job
checks out with LFS, installs `requirements.txt`, runs
`fetch_data.py --discover`, uploads the freshly fetched raw files as a 90-day
build artifact, refreshes `data/SOURCE_MANIFEST.csv`, and **opens a pull
request** with a maintainer checklist (bump `EXPECTED_QUARTERS`, update the
pinned headline numbers with a documented reason, regenerate the LFS
artifact). It deliberately does *not* silently rewrite the pinned cleaned data
on the default branch — the reproducibility pins stay human-reviewed.

---

## Data provenance & sources

Primary source — the U.S. House **Statement of Disbursements archive**:

> <https://www.house.gov/the-house-explained/open-government/statement-of-disbursements/archive>

(landing page:
<https://www.house.gov/the-house-explained/open-government/statement-of-disbursements>;
secondary mirror: ProPublica
[House Office Expenditures](https://projects.propublica.org/represent/expenditures)).

Each quarter is one file at the archive, named
`YYYYQ#-house-disburse-detail.csv` (2011–2022),
`YYYYQ#-house-disburse-detail only.csv` (2023–2024), or
`YYYYQ#-house-disburse-details only.xlsx` (2025) — see the per-file table
below and `data/SOURCE_MANIFEST.csv` for exact sizes and SHA-256 checksums.
The raw files (~1 GB) are gitignored and live under `data/disbursements/`;
retrieve them with `python scripts/fetch_data.py`.

### Per-file describe table

Rows and unique legislators are measured **after cleaning** (subtotal/total
rows removed). 2010 is excluded (see *Scope* below). From 2023Q1 the source
dropped `BIOGUIDE_ID`, so those quarters are office-level only and report no
unique legislators by construction. Totals are the cleaned `AMOUNT` sum.

| Quarter | Source file (House SoD archive) | Cleaned rows | Unique legislators | Cleaned total |
|---|---|--:|--:|--:|
| 2011Q1 | `2011Q1-house-disburse-detail.csv` | 119,231 | 540 | $326.3M |
| 2011Q2 | `2011Q2-house-disburse-detail.csv` | 112,855 | 536 | $310.6M |
| 2011Q3 | `2011Q3-house-disburse-detail.csv` | 105,990 | 495 | $313.8M |
| 2011Q4 | `2011Q4-house-disburse-detail.csv` | 103,582 | 479 | $349.1M |
| 2012Q1 | `2012Q1-house-disburse-detail.csv` | 118,910 | 486 | $329.0M |
| 2012Q2 | `2012Q2-house-disburse-detail.csv` | 102,790 | 464 | $303.5M |
| 2012Q3 | `2012Q3-house-disburse-detail.csv` | 93,360 | 451 | $299.8M |
| 2012Q4 | `2012Q4-house-disburse-detail.csv` | 90,337 | 449 | $321.2M |
| 2013Q1 | `2013Q1-house-disburse-detail.csv` | 107,854 | 529 | $298.6M |
| 2013Q2 | `2013Q2-house-disburse-detail.csv` | 95,638 | 521 | $282.6M |
| 2013Q3 | `2013Q3-house-disburse-detail.csv` | 96,677 | 486 | $283.0M |
| 2013Q4 | `2013Q4-house-disburse-detail.csv` | 88,785 | 463 | $297.6M |
| 2014Q1 | `2014Q1-house-disburse-detail.csv` | 102,354 | 458 | $292.6M |
| 2014Q2 | `2014Q2-house-disburse-detail.csv` | 94,473 | 449 | $276.4M |
| 2014Q3 | `2014Q3-house-disburse-detail.csv` | 90,252 | 449 | $281.3M |
| 2014Q4 | `2014Q4-house-disburse-detail.csv` | 91,131 | 447 | $308.6M |
| 2015Q1 | `2015Q1-house-disburse-detail.csv` | 102,726 | 506 | $295.4M |
| 2015Q2 | `2015Q2-house-disburse-detail.csv` | 95,493 | 495 | $277.4M |
| 2015Q3 | `2015Q3-house-disburse-detail.csv` | 91,563 | 477 | $276.8M |
| 2015Q4 | `2015Q4-house-disburse-detail.csv` | 96,048 | 463 | $313.8M |
| 2016Q1 | `2016Q1-house-disburse-detail.csv` | 103,132 | 457 | $300.7M |
| 2016Q2 | `2016Q2-house-disburse-detail.csv` | 99,251 | 540 | $285.5M |
| 2016Q3 | `2016Q3-house-disburse-detail.csv` | 92,555 | 442 | $295.8M |
| 2016Q4 | `2016Q4-house-disburse-detail.csv` | 90,675 | 444 | $309.8M |
| 2017Q1 | `2017Q1-house-disburse-detail.csv` | 103,087 | 497 | $297.1M |
| 2017Q2 | `2017Q2-house-disburse-detail.csv` | 98,669 | 487 | $290.1M |
| 2017Q3 | `2017Q3-house-disburse-detail.csv` | 97,734 | 462 | $294.8M |
| 2017Q4 | `2017Q4-house-disburse-detail.csv` | 94,086 | 460 | $325.5M |
| 2018Q1 | `2018Q1-house-disburse-detail.csv` | 85,279 | 354 | $255.4M |
| 2018Q2 | `2018Q2-house-disburse-detail.csv` | 97,856 | 456 | $300.8M |
| 2018Q3 | `2018Q3-house-disburse-detail.csv` | 94,055 | 448 | $312.9M |
| 2018Q4 | `2018Q4-house-disburse-detail.csv` | 93,044 | 443 | $340.6M |
| 2019Q1 | `2019Q1-house-disburse-detail.csv` | 108,131 | 535 | $315.6M |
| 2019Q2 | `2019Q2-house-disburse-detail.csv` | 111,977 | 514 | $313.5M |
| 2019Q3 | `2019Q3-house-disburse-detail.csv` | 111,086 | 495 | $324.9M |
| 2019Q4 | `2019Q4-house-disburse-detail.csv` | 114,059 | 470 | $363.8M |
| 2020Q1 | `2020Q1-house-disburse-detail.csv` | 121,052 | 455 | $363.3M |
| 2020Q2 | `2020Q2-house-disburse-detail.csv` | 78,499 | 453 | $335.7M |
| 2020Q3 | `2020Q3-house-disburse-detail.csv` | 81,147 | 455 | $354.0M |
| 2020Q4 | `2020Q4-house-disburse-detail.csv` | 80,906 | 452 | $379.2M |
| 2021Q1 | `2021Q1-house-disburse-detail.csv` | 96,244 | 506 | $348.0M |
| 2021Q2 | `2021Q2-house-disburse-detail.csv` | 92,076 | 485 | $339.7M |
| 2021Q3 | `2021Q3-house-disburse-detail.csv` | 97,327 | 465 | $360.0M |
| 2021Q4 | `2021Q4-house-disburse-detail.csv` | 102,260 | 460 | $401.8M |
| 2022Q1 | `2022Q1-house-disburse-detail.csv` | 110,844 | 453 | $391.7M |
| 2022Q2 | `2022Q2-house-disburse-detail.csv` | 110,745 | 447 | $395.6M |
| 2022Q3 | `2022Q3-house-disburse-detail.csv` | 120,047 | 450 | $422.5M |
| 2022Q4 | `2022Q4-house-disburse-detail.csv` | 106,238 | 450 | $476.1M |
| 2023Q1 | `2023Q1-house-disburse-detail only.csv` | 126,102 | — *(office-level)* | $440.7M |
| 2023Q2 | `2023Q2-house-disburse-detail only.csv` | 122,488 | — *(office-level)* | $418.7M |
| 2023Q3 | `2023Q3-house-disburse-detail only.csv` | 126,131 | — *(office-level)* | $450.1M |
| 2023Q4 | `2023Q4-house-disburse-detail only.csv` | 117,508 | — *(office-level)* | $485.0M |
| 2024Q1 | `2024Q1-house-disburse-detail only.csv` | 137,622 | — *(office-level)* | $488.2M |
| 2024Q2 | `2024Q2-house-disburse-detail only.csv` | 124,153 | — *(office-level)* | $442.0M |
| 2024Q3 | `2024Q3-house-disburse-detail only.csv` | 120,045 | — *(office-level)* | $474.6M |
| 2024Q4 | `2024Q4-house-disburse-detail only.csv` | 121,192 | — *(office-level)* | $514.9M |
| 2025Q1 | `2025Q1-house-disburse-details only.xlsx` | 126,650 | — *(office-level)* | $480.6M |
| 2025Q2 | `2025Q2-house-disburse-details only.xlsx` | 126,755 | — *(office-level)* | $447.5M |
| **Total** | **58 quarters** | **6,040,756** | **938 distinct** | **$20,174.4M** |

---

## Pinned headline numbers

| Metric | Value |
|---|--:|
| Source files read | 62 (2010Q1–2025Q2) |
| Cleaned quarters | 58 (2011Q1–2025Q2) |
| Raw rows read | 6,233,106 |
| Cleaned rows | 6,040,756 |
| Subtotal/total rows removed | 192,350 |
| Distinct legislators (2011–2022) | 938 |
| Grand-total `AMOUNT` | $20,174,379,954.18 |

`cleaning.ipynb` asserts every one of these; a change is a deliberate,
documented signal that the upstream source shifted.

## Scope & limitations

- **2010 is excluded.** The 2010Q1–Q2 raw files cram date, posting code,
  record id, and payee into one fixed-width `PAYEE` field (a pre-Schema-1
  layout the source never normalized); the original analysis also excluded all
  of 2010. The cleaned universe is a consistent **2011Q1–2025Q2** boundary.
- **2023–2025 are office-level only.** `BIOGUIDE_ID` was dropped from the
  source at 2023Q1, so member-level analyses cover **2011–2022**.
- **`DATE` vs `PERIOD_DATE`.** `DATE` is the true transaction date, null where
  the source has none (notably personnel rows); `PERIOD_DATE` (= `DATE` else
  `START DATE`) is for time-series binning. The pre-billing audit uses the
  true (possibly null) `DATE` on purpose.

## Reproduce

```bash
git lfs install                       # one-time
pip install -r requirements.txt

python scripts/fetch_data.py          # raw files -> data/  (~1 GB)
python scripts/fetch_biographical.py  # enrichment inputs (cached locally)

jupyter nbconvert --to notebook --execute --inplace cleaning.ipynb
jupyter nbconvert --to notebook --execute --inplace analysis_v3.ipynb
```

Released under an [MIT License](LICENSE).
