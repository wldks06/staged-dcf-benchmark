"""data/snapshot.py: the write-once store behind every fetcher. No network, tmp_path only."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import zlib

import pytest

from dcfbench.data import snapshot as snapshot_module
from dcfbench.data.snapshot import AUTOSAVE_EVERY, Snapshot, SnapshotError


class FakeHttp:
    """Stands in for data.http.Http: canned bytes, a call log, a request counter."""

    def __init__(self, content: bytes = b"payload"):
        self.content = content
        self.calls: list[tuple[str, dict | None]] = []
        self.requests_made = 0

    def get(self, url, params=None):
        self.calls.append((url, params))
        self.requests_made += 1
        return self.content


@pytest.fixture
def snap(tmp_path):
    return Snapshot("t", root=tmp_path, readonly=False)


def reopen(snap: Snapshot, **kwargs) -> Snapshot:
    return Snapshot(snap.snapshot_id, root=snap.dir.parent, **kwargs)


def manifest_on_disk(snap: Snapshot) -> dict:
    return json.loads((snap.dir / "manifest.json").read_text(encoding="utf-8"))


# --- put and read ------------------------------------------------------------


def test_put_then_read_round_trips(snap):
    binary = bytes(range(256)) * 4
    snap.put("damodaran/betas/2023.xls", binary, source="unit test")
    snap.put("fred/DGS10.json", b'{"observations": []}', source="unit test")
    assert snap.has("damodaran/betas/2023.xls")
    assert snap.read("damodaran/betas/2023.xls") == binary
    assert snap.read("damodaran/betas/2023.xls", verify=True) == binary
    assert snap.read_json("fred/DGS10.json") == {"observations": []}


def test_put_records_source_hash_size_time_and_note(snap):
    content = b'{"n": 1}'
    snap.put("a.json", content, source="unit test", note="hand-made")
    snap.put("b.json", content, source="unit test")
    entry = snap.entry("a.json")
    assert entry["source"] == "unit test"
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert entry["bytes"] == len(content)
    assert entry["note"] == "hand-made"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", entry["fetched_at"])
    assert "note" not in snap.entry("b.json")


def test_put_same_content_twice_is_a_noop(snap, monkeypatch):
    snap.put("a.json", b"one", source="first")
    before = dict(snap.entry("a.json"))
    # A repeated put must leave the entry alone, timestamp and source included.
    monkeypatch.setattr(snapshot_module, "_now", lambda: "2099-01-01T00:00:00Z")
    snap.put("a.json", b"one", source="second")
    assert snap.entry("a.json") == before
    assert snap.keys() == ["a.json"]


def test_put_different_content_under_an_existing_key_raises(snap):
    snap.put("a.json", b"one", source="t")
    with pytest.raises(SnapshotError, match="already holds different content"):
        snap.put("a.json", b"two", source="t")
    assert snap.read("a.json", verify=True) == b"one"


def test_missing_key_is_an_error_not_an_empty_answer(snap):
    assert not snap.has("absent.json")
    for call in (snap.entry, snap.read, snap.read_json):
        with pytest.raises(SnapshotError, match="absent.json is not in snapshot t"):
            call("absent.json")


def test_keys_filters_by_prefix_and_sorts(snap):
    stored = ["fred/DTB3.csv", "prices/MSFT.json", "fred/DGS10.csv", "prices/AAPL.json", "fredx"]
    for key in stored:
        snap.put(key, key.encode(), source="t")
    assert snap.keys() == sorted(stored)
    assert snap.keys("fred/") == ["fred/DGS10.csv", "fred/DTB3.csv"]
    assert snap.keys("prices/") == ["prices/AAPL.json", "prices/MSFT.json"]
    assert snap.keys("edgar/") == []


def test_payload_is_stored_gzipped_and_reproducible(tmp_path):
    content = b"observation_date,DGS10\n2022-12-30,3.88\n" * 50
    paths = []
    for name in ("one", "two"):
        store = Snapshot(name, root=tmp_path, readonly=False)
        store.put("fred/DGS10.csv", content, source="t")
        paths.append(store.dir / "raw" / "fred" / "DGS10.csv.gz")
    assert gzip.decompress(paths[0].read_bytes()) == content
    # No timestamp in the gzip header, so the same payload gives the same file.
    assert paths[0].read_bytes()[4:8] == b"\x00\x00\x00\x00"
    assert paths[0].read_bytes() == paths[1].read_bytes()


def test_default_root_is_the_configured_snapshot_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_module, "SNAPSHOT_DIR", tmp_path)
    assert Snapshot("t", readonly=False).dir == tmp_path / "t"


# --- persistence -------------------------------------------------------------


def test_manifest_survives_a_new_instance(tmp_path):
    with Snapshot("t", root=tmp_path, readonly=False) as first:
        first.put("a/b.json", b'{"n": 1}', source="unit test", note="hand-made")
        entry = dict(first.entry("a/b.json"))
    # Leaving the with-block saved the manifest.
    again = Snapshot("t", root=tmp_path)
    assert again.snapshot_id == "t"
    assert again.keys() == ["a/b.json"]
    assert again.entry("a/b.json") == entry
    assert again.read_json("a/b.json") == {"n": 1}
    assert not again.frozen
    assert manifest_on_disk(again)["snapshot_id"] == "t"


def test_a_writable_reopen_keeps_earlier_entries(snap):
    snap.put("a", b"1", source="t")
    snap.save()
    second = reopen(snap, readonly=False)
    second.put("b", b"2", source="t")
    second.save()
    assert reopen(snap).keys() == ["a", "b"]
    assert manifest_on_disk(snap)["created"] == snap._manifest["created"]


def test_autosave_writes_the_manifest_during_a_long_run(snap):
    manifest = snap.dir / "manifest.json"
    for i in range(AUTOSAVE_EVERY - 1):
        snap.put(f"k/{i:03d}", str(i).encode(), source="t")
    assert not manifest.exists()
    snap.put("k/last", b"x", source="t")
    # No save() call so far: a pull that dies here still knows what it stored.
    assert len(reopen(snap).keys()) == AUTOSAVE_EVERY
    # The counter starts over after an autosave.
    snap.put("k/after", b"y", source="t")
    assert not reopen(snap).has("k/after")
    snap.save()
    assert reopen(snap).has("k/after")


def test_opening_a_missing_snapshot_readonly_raises(tmp_path):
    with pytest.raises(SnapshotError, match="does not exist"):
        Snapshot("absent", root=tmp_path)
    assert not (tmp_path / "absent").exists()


# --- read-only and frozen ----------------------------------------------------


def test_readonly_snapshot_refuses_writes_but_serves_existing_keys(snap):
    snap.put("a.json", b"one", source="t")
    snap.save()
    readonly = reopen(snap)
    http = FakeHttp()
    assert readonly.read("a.json") == b"one"
    assert readonly.fetch("a.json", "https://example.test/a", http) == b"one"
    with pytest.raises(SnapshotError, match="read-only"):
        readonly.put("b.json", b"two", source="t")
    with pytest.raises(SnapshotError, match="read-only"):
        readonly.put("a.json", b"one", source="t")
    with pytest.raises(SnapshotError, match="read-only"):
        readonly.fetch("b.json", "https://example.test/b", http)
    with pytest.raises(SnapshotError, match="read-only"):
        readonly.freeze()
    assert http.requests_made == 0
    assert not readonly.has("b.json")
    readonly.save()
    assert manifest_on_disk(snap)["frozen"] is False


def test_frozen_snapshot_refuses_writes_but_serves_existing_keys(snap):
    snap.put("a.json", b"one", source="t")
    snap.freeze()
    # Frozen holds for the instance that froze it and for any later writable open.
    for store in (snap, reopen(snap, readonly=False)):
        http = FakeHttp()
        assert store.frozen
        assert store.read("a.json") == b"one"
        assert store.fetch("a.json", "https://example.test/a", http) == b"one"
        with pytest.raises(SnapshotError, match="frozen"):
            store.put("b.json", b"two", source="t")
        with pytest.raises(SnapshotError, match="frozen"):
            store.fetch("b.json", "https://example.test/b", http)
        assert http.requests_made == 0
        assert not store.has("b.json")


def test_freeze_saves_the_manifest_with_a_timestamp(snap):
    snap.put("a.json", b"one", source="t")
    snap.freeze()
    manifest = manifest_on_disk(snap)
    assert manifest["frozen"] is True
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", manifest["frozen_at"])
    assert list(manifest["entries"]) == ["a.json"]
    assert reopen(snap).frozen


# --- fetch -------------------------------------------------------------------


def test_fetch_returns_the_stored_payload_without_calling_http(snap):
    snap.put("fred/DGS10.csv", b"stored", source="t")
    http = FakeHttp(b"from the network")
    url = "https://example.test/x"
    assert snap.fetch("fred/DGS10.csv", url, http, params={"id": "DGS10"}) == b"stored"
    assert http.requests_made == 0


def test_fetch_downloads_once_and_stores_the_request_url(snap):
    http = FakeHttp(b"from the network")
    url, params = "https://example.test/graph.csv", {"id": "DGS10"}
    assert snap.fetch("fred/DGS10.csv", url, http, params=params) == b"from the network"
    assert http.calls == [(url, params)]
    assert snap.entry("fred/DGS10.csv")["source"] == "https://example.test/graph.csv?id=DGS10"
    # The upstream file changing later does not matter: the key is already stored.
    http.content = b"changed upstream"
    assert snap.fetch("fred/DGS10.csv", url, http, params=params) == b"from the network"
    assert http.requests_made == 1


def test_fetch_accepts_an_explicit_source_label(snap):
    snap.fetch("prices/X.json", "https://example.test/x", FakeHttp(), source="vendor:X")
    assert snap.entry("prices/X.json")["source"] == "vendor:X"


def test_manifest_source_never_contains_a_key_value(snap):
    http = FakeHttp()
    snap.fetch("a", "https://api.example.test/obs?api_key=SECRET123", http,
               params={"crtfc_key": "SECRET456", "token": "SECRET789", "series_id": "DGS10"})
    snap.fetch("b", "https://api.example.test/obs", http, params={"api_key": "SECRET123"},
               source="https://api.example.test/obs?api_key=SECRET123")
    snap.put("c", b"x", source="https://api.example.test/obs?token=SECRET789")
    snap.save()
    assert snap.entry("a")["source"] == (
        "https://api.example.test/obs?api_key=REDACTED&crtfc_key=REDACTED&token=REDACTED"
        "&series_id=DGS10")
    text = (snap.dir / "manifest.json").read_text(encoding="utf-8")
    for value in ("SECRET123", "SECRET456", "SECRET789"):
        assert value not in text
    # Only the record is redacted. The request itself went out with the real key.
    assert http.calls[0][1]["crtfc_key"] == "SECRET456"


# --- verify ------------------------------------------------------------------


def stored_three(snap: Snapshot):
    for name in ("a", "b", "c"):
        snap.put(f"x/{name}.json", (name * 2000).encode(), source="t")
    snap.save()
    return snap.dir / "raw" / "x"


def test_verify_is_clean_for_an_untouched_snapshot(snap):
    stored_three(snap)
    assert snap.verify() == []
    assert reopen(snap).verify() == []


def test_verify_reports_tampered_and_missing_payloads(snap):
    raw = stored_three(snap)
    with gzip.open(raw / "a.json.gz", "wb") as handle:
        handle.write(b"tampered")
    (raw / "b.json.gz").unlink()
    readonly = reopen(snap)
    assert readonly.verify() == ["x/a.json", "x/b.json"]
    # A plain read trusts the file. Only read(verify=True) checks the hash.
    assert readonly.read("x/a.json") == b"tampered"
    with pytest.raises(SnapshotError, match="does not match its manifest hash"):
        readonly.read("x/a.json", verify=True)


def test_verify_reports_a_payload_that_is_not_gzip(snap):
    raw = stored_three(snap)
    (raw / "c.json.gz").write_bytes(b"this is not gzip")
    assert reopen(snap).verify() == ["x/c.json"]


def _truncate(path):
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])


def _break_stream(path):
    # A valid gzip header followed by a deflate block of the reserved type 3.
    path.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff" + b"\x07" + b"\x00" * 16)


@pytest.mark.parametrize("damage", [_truncate, _break_stream], ids=["truncated", "bad-stream"])
def test_verify_reports_a_damaged_gzip_payload(snap, damage):
    raw = stored_three(snap)
    damage(raw / "a.json.gz")
    assert reopen(snap).verify() == ["x/a.json"]
