"""data/universe.py: S&P 100 membership from a stored Wikipedia page, and ticker mapping.

No network. Pages are small hand-built HTML documents in the shape the MediaWiki
parse API returns.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from dcfbench.data import universe
from dcfbench.data.snapshot import Snapshot
from dcfbench.data.universe import Constituent

AS_OF = date(2022, 12, 31)


def html_table(headers, rows, css="wikitable sortable") -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table class="{css}"><tbody><tr>{head}</tr>{body}</tbody></table>'


# Tables that surround the constituent list in the real article.
INFOBOX = ('<table class="infobox vcard"><tbody>'
           '<tr><th scope="row">Foundation</th><td>June 15, 1983</td></tr>'
           '<tr><th scope="row">Operator</th><td>S&amp;P Dow Jones Indices</td></tr>'
           '</tbody></table>')
RECORDS = html_table(["Category", "Value", "Date"], [["Closing high", "3,000.00", "2022"]])
# Longer than the constituent list, but without a Symbol column.
ANNUAL_RETURNS = html_table(["Year", "Closing level"], [[y, "1,000.00"] for y in range(1900, 2025)])
# Has a Symbol column, but is far too short to be the index.
RECENT_CHANGES = html_table(["Symbol", "Name"], [["OLD", "Removed Co."], ["NEW", "Added Co."]])

LEADERS = [("AAPL", "Apple Inc.", "Information Technology"),
           ("BRK.B", "Berkshire Hathaway", "Financials"),
           ("GOOG", "Alphabet Inc. (Class C)", "Communication Services"),
           ("GOOGL", "Alphabet Inc. (Class A)", "Communication Services")]
FILLER = [(f"T{i:03d}", f"Company {i}", "Industrials") for i in range(97)]
MEMBERS = LEADERS + FILLER  # 101 rows, like the real index with two Alphabet classes


def page(*tables: str) -> bytes:
    """The answer of action=parse with formatversion=2: the article HTML as one string."""
    body = "<p>The S&amp;P 100 is a stock market index.</p>" + "".join(tables)
    text = f'<div class="mw-parser-output">{body}</div>'
    parse = {"title": "S&P 100", "pageid": 2658424, "revid": 1, "text": text}
    return json.dumps({"parse": parse}).encode()


def revision(revid: int, timestamp: str) -> bytes:
    """The answer of action=query&prop=revisions with rvlimit=1."""
    found = {"revid": revid, "parentid": revid - 1, "timestamp": timestamp}
    article = {"pageid": 2658424, "ns": 0, "title": "S&P 100", "revisions": [found]}
    return json.dumps({"query": {"pages": [article]}}).encode()


@pytest.fixture
def snap(tmp_path):
    return Snapshot("t", root=tmp_path, readonly=False)


def put_page(snap, as_of: date, content: bytes) -> None:
    snap.put(f"universe/sp100/{as_of.isoformat()}/page.json", content, source="t")


# --- load_sp100 --------------------------------------------------------------------


def test_load_sp100_reads_the_three_column_layout(snap):
    put_page(snap, AS_OF, page(html_table(["Symbol", "Name", "Sector"], MEMBERS)))
    members = universe.load_sp100(snap, AS_OF)
    assert len(members) == 101
    assert members[0] == Constituent("AAPL", "Apple Inc.", "Information Technology")
    # The ticker is kept as the article writes it. current_ticker() normalizes it later.
    assert members[1] == Constituent("BRK.B", "Berkshire Hathaway", "Financials")
    assert [m.ticker for m in members] == [row[0] for row in MEMBERS]


def test_load_sp100_reads_the_two_column_layout_of_2019(snap):
    as_of = date(2019, 12, 31)
    put_page(snap, as_of, page(html_table(["Symbol", "Name"], [row[:2] for row in MEMBERS])))
    members = universe.load_sp100(snap, as_of)
    assert len(members) == 101
    assert members[0] == Constituent("AAPL", "Apple Inc.", None)
    assert all(m.sector is None for m in members)


def test_load_sp100_finds_the_constituent_table_among_several(snap):
    constituents = html_table(["Symbol", "Name", "Sector"], MEMBERS)
    put_page(snap, AS_OF, page(INFOBOX, RECORDS, RECENT_CHANGES, ANNUAL_RETURNS, constituents))
    members = universe.load_sp100(snap, AS_OF)
    assert len(members) == 101
    assert {m.ticker for m in members}.isdisjoint({"OLD", "NEW"})


def test_load_sp100_matches_the_symbol_header_loosely(snap):
    put_page(snap, AS_OF, page(INFOBOX, html_table([" symbol ", "NAME", "Sector"], MEMBERS)))
    assert universe.load_sp100(snap, AS_OF)[0] == Constituent(
        "AAPL", "Apple Inc.", "Information Technology")


def test_load_sp100_without_a_constituent_table_is_an_error(snap):
    put_page(snap, AS_OF, page(INFOBOX, RECENT_CHANGES, ANNUAL_RETURNS))
    with pytest.raises(ValueError, match="no constituent table in the S&P 100 article as of 2022"):
        universe.load_sp100(snap, AS_OF)


def test_load_sp100_reads_the_page_stored_for_the_date(snap):
    earlier = date(2019, 12, 31)
    put_page(snap, AS_OF, page(html_table(["Symbol", "Name", "Sector"], MEMBERS)))
    old_members = [("UTX", "United Technologies")] + [row[:2] for row in MEMBERS[1:]]
    put_page(snap, earlier, page(html_table(["Symbol", "Name"], old_members)))
    assert universe.load_sp100(snap, AS_OF)[0].ticker == "AAPL"
    assert universe.load_sp100(snap, earlier)[0].ticker == "UTX"


def test_sp100_revision_reports_the_article_version_used(snap):
    snap.put(f"universe/sp100/{AS_OF.isoformat()}/revision.json",
             revision(1126258944, "2022-12-08T10:53:00Z"), source="t")
    assert universe.sp100_revision(snap, AS_OF) == {
        "revid": 1126258944, "parentid": 1126258943, "timestamp": "2022-12-08T10:53:00Z"}


# --- fetch_sp100 ---------------------------------------------------------------------


class FakeWiki:
    """Answers the two MediaWiki calls fetch_sp100 makes."""

    def __init__(self, revision_json: bytes, page_json: bytes):
        self.answers = {"query": revision_json, "parse": page_json}
        self.calls: list[tuple[str, dict]] = []
        self.requests_made = 0

    def get(self, url, params=None):
        self.calls.append((url, params))
        self.requests_made += 1
        return self.answers[params["action"]]


def test_fetch_sp100_stores_the_revision_live_on_the_date_and_its_page(snap):
    wiki = FakeWiki(revision(1126258944, "2022-12-08T10:53:00Z"),
                    page(INFOBOX, html_table(["Symbol", "Name", "Sector"], MEMBERS)))
    members = universe.fetch_sp100(snap, wiki, AS_OF)
    assert len(members) == 101

    (first_url, first), (second_url, second) = wiki.calls
    assert first_url == second_url == universe.WIKI_API
    # The newest revision at or before the end of the valuation date.
    assert first == dict(action="query", prop="revisions", titles="S&P 100", rvlimit=1,
                         rvdir="older", rvstart="2022-12-31T23:59:59Z", rvprop="ids|timestamp",
                         format="json", formatversion=2)
    assert second == dict(action="parse", oldid=1126258944, prop="text", format="json",
                          formatversion=2)
    assert snap.keys() == ["universe/sp100/2022-12-31/page.json",
                           "universe/sp100/2022-12-31/revision.json"]
    assert "oldid=1126258944" in snap.entry("universe/sp100/2022-12-31/page.json")["source"]

    # A second run is served from the snapshot.
    assert universe.fetch_sp100(snap, wiki, AS_OF) == members
    assert wiki.requests_made == 2


# --- tickers ---------------------------------------------------------------------------


@pytest.mark.parametrize("old, current", [
    ("FB", "META"), ("UTX", "RTX"), ("BK", "BNY"),  # renamed, same company
    ("BRK.B", "BRK-B"), (" brk.b ", "BRK-B"),  # share class written the SEC way
    ("AAPL", "AAPL"), ("GOOGL", "GOOGL"),
])
def test_current_ticker_maps_old_symbols_and_normalizes(old, current):
    assert universe.current_ticker(old) == current


def test_cik_for_prefers_the_override_then_the_ticker_map():
    ticker_map = {"XOM": "0009999999", "AAPL": "0000320193"}
    # Exxon's history sits under the older registrant, not the one its ticker maps to.
    assert universe.cik_for("XOM", ticker_map) == universe.CIK_OVERRIDES["XOM"] == "0000034088"
    assert universe.cik_for("AAPL", ticker_map) == "0000320193"
    assert universe.cik_for("AGN", ticker_map) is None
