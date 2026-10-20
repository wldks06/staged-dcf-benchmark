# Answer-key engine (`dcfbench`)

The engine turns point-in-time company data and a stated valuation policy into a case with one correct value at every DCF step (paper, Sections IV-A and IV-B). Its output for this paper is [`data/cases_v1_us/`](../data/cases_v1_us/); the questions in [`data/questions/`](../data/questions/) read every number from there.

This folder is the U.S. part of the authors' `dcfbench` package: the data adapters for the four U.S. sources, the policies, the deterministic DCF and the case generator, with their tests.

## Layout

| File | Role |
|---|---|
| [`src/dcfbench/policies.py`](src/dcfbench/policies.py) | The policy blocks: `TEXTBOOK`, `PRACTITIONER` and the trap policies, with the constants they refer to (ERP 7.0% or 5.0%, Blume adjustment, terminal growth, operating cash) |
| [`src/dcfbench/schema.py`](src/dcfbench/schema.py) | Pydantic models of a case: company, policy, inputs with provenance, checkpoints |
| [`src/dcfbench/forecast.py`](src/dcfbench/forecast.py) | Step 2: revenue growth from the three-year history fading to *g*, items held at their average share of revenue, the steady-state year 5 |
| [`src/dcfbench/engine.py`](src/dcfbench/engine.py) | Steps 3 to 5: FCFF, CAPM cost of equity with a relevered beta, cost of debt from the synthetic rating, WACC, Gordon terminal value, enterprise value, the equity bridge and value per share; every intermediate value is stored as a checkpoint; also the trap answers |
| [`src/dcfbench/generate.py`](src/dcfbench/generate.py) | Universe filters, input assembly from the snapshot and case generation (`generate_us`); every exclusion and fallback is logged |
| [`src/dcfbench/data/`](src/dcfbench/data/) | One adapter per source: [`edgar.py`](src/dcfbench/data/edgar.py) (XBRL company facts, ordered tag recipes, the as-of rule), [`fred.py`](src/dcfbench/data/fred.py), [`prices.py`](src/dcfbench/data/prices.py) (Yahoo Finance, un-adjusted for later splits), [`damodaran.py`](src/dcfbench/data/damodaran.py) (industry betas, rating spreads), [`universe.py`](src/dcfbench/data/universe.py) (S&P 100 membership, sector pool), and [`snapshot.py`](src/dcfbench/data/snapshot.py), the frozen, hashed store every adapter writes to and reads from |
| [`src/dcfbench/cli.py`](src/dcfbench/cli.py) | `snapshot-us`, `snapshot-info`, `generate-us` |
| [`tests/`](tests/) | 350 tests, among them the textbook example reproduced to the cent ([`test_engine_rwj.py`](tests/test_engine_rwj.py), Ross, Westerfield and Jaffe) and a worked guide example with its sensitivity grid ([`test_engine_guide.py`](tests/test_engine_guide.py)) |

## Install and test

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -e "engine[dev]"
cd engine && DCFBENCH_ROOT=$PWD python -m pytest -q          # 350 passed, 6 skipped (live network tests)
```

`make engine-test` from the repository root does the same in a temporary environment.

## Rebuild the cases from the original sources

Not needed to use the benchmark: the cases are in [`data/cases_v1_us/`](../data/cases_v1_us/). To rebuild them:

1. Copy [`.env.example`](.env.example) to `.env` and set `SEC_USER_AGENT` (SEC EDGAR asks every client for a name and a contact email; no key). A FRED key is optional.
2. Provide the sector candidate pool as `data/universe/us_sector_seed.csv` (columns `ticker,name,gics_sector,gics_sub_industry,market_cap_usd_<date>,rank_in_sector`; the paper used the 30 largest U.S.-exchange listings per GICS sector outside Financials by market capitalization on October 4, 2026). Optionally add GICS labels as `data/universe/gics_labels.csv` (columns `market,ticker,name,gics_sector,gics_industry_group,gics_industry,gics_sub_industry,gics_sub_code`); without it the cases carry no sector names. Both files came from a licensed screener export and are not redistributed.
3. Pull a snapshot and generate, from this folder:

```bash
export DCFBENCH_ROOT=$PWD
python -m dcfbench.cli snapshot-us --snapshot snap-my-rebuild --universe both     # network; SEC allows 10 requests per second
python -m dcfbench.cli snapshot-info --snapshot snap-my-rebuild --verify
python -m dcfbench.cli generate-us --snapshot snap-my-rebuild --universe sector --version v1   # no network
```

Generation reads the snapshot only, so the same snapshot always gives the same cases. A filing counts only if it was filed on or before the valuation date. SEC company facts and price histories change as companies file and restate, so a snapshot pulled today differs from the paper's; [`data/snapshot_manifest/`](../data/snapshot_manifest/) lists the SHA-256 of every payload of the paper's snapshot `snap-2026-10-05-a` for comparison.

## Scope

The package also holds the definitions of draft Korean and Japanese policies and of source codes for those markets (in `policies.py` and `schema.py`); they are not used in this paper, and their data adapters are not part of this repository.
