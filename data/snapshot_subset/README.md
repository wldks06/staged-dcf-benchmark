# Raw data subset of snapshot `snap-2026-10-05-a`

The public part of the raw data the cases in [`../cases_v1_us/`](../cases_v1_us/) were built from, as it was fetched on
October 5, 2026. [`pipeline/audit_questions.py`](../../pipeline/audit_questions.py) (check C) matches every historical input
of every question to these files.

| Folder | Contents | Source |
|---|---|---|
| `edgar/companyfacts/CIK<10 digits>.json.gz` | XBRL company facts of the 68 companies in the case set | SEC EDGAR (public) |
| `fred/<series>.json.gz` | DTB3 (3-month Treasury bill), DGS10 and DGS20 (10- and 20-year Treasury yields), T10YIE | FRED, Federal Reserve Bank of St. Louis |

Not included: the Yahoo Finance price histories (an unofficial interface whose terms do not clearly allow
redistribution) and Damodaran's spreadsheets. Their URLs, fetch times and SHA-256 hashes are in
[`../snapshot_manifest/snap-2026-10-05-a.manifest.json`](../snapshot_manifest/), so a snapshot rebuilt with the engine
([`engine/README.md`](../../engine/README.md)) can be checked payload by payload.
