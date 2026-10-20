"""Frozen data snapshots.

A snapshot is a directory of raw API responses plus a manifest:

    data/snapshots/{snapshot_id}/manifest.json
    data/snapshots/{snapshot_id}/raw/{key}.gz

This module is the only code that writes there. Fetchers call Snapshot.fetch, which
returns the stored payload when the key exists and touches the network only when it
does not. Generation and grading open the snapshot read-only, so a missing key is an
error instead of a live request. Once frozen, a snapshot never changes: make a new
one and bump the id.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from datetime import datetime, timezone
from pathlib import Path

from requests import Request

from ..config import SNAPSHOT_DIR, redact
from .http import Http


AUTOSAVE_EVERY = 20


class SnapshotError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Snapshot:
    def __init__(self, snapshot_id: str, *, root: Path | None = None, readonly: bool = True):
        self.snapshot_id = snapshot_id
        self.dir = (root or SNAPSHOT_DIR) / snapshot_id
        self.readonly = readonly
        self._manifest_path = self.dir / "manifest.json"
        if self._manifest_path.exists():
            self._manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        elif readonly:
            raise SnapshotError(f"snapshot {snapshot_id} does not exist at {self.dir}")
        else:
            self._manifest = {
                "snapshot_id": snapshot_id, "created": _now(), "frozen": False, "entries": {},
            }
        self._dirty = False
        self._unsaved = 0

    # --- reading -------------------------------------------------------------

    @property
    def frozen(self) -> bool:
        return bool(self._manifest["frozen"])

    def has(self, key: str) -> bool:
        return key in self._manifest["entries"]

    def keys(self, prefix: str = "") -> list[str]:
        return sorted(k for k in self._manifest["entries"] if k.startswith(prefix))

    def entry(self, key: str) -> dict:
        if not self.has(key):
            raise SnapshotError(f"{key} is not in snapshot {self.snapshot_id}")
        return self._manifest["entries"][key]

    def read(self, key: str, *, verify: bool = False) -> bytes:
        entry = self.entry(key)
        with gzip.open(self.dir / "raw" / (key + ".gz"), "rb") as handle:
            content = handle.read()
        if verify and hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise SnapshotError(f"{key} does not match its manifest hash")
        return content

    def read_json(self, key: str):
        return json.loads(self.read(key))

    def verify(self) -> list[str]:
        """Keys whose stored payload is missing or does not match the manifest."""
        bad = []
        for key in self.keys():
            try:
                self.read(key, verify=True)
            except (SnapshotError, OSError, EOFError, zlib.error):
                bad.append(key)  # hash mismatch, missing file, truncated or damaged gzip
        return bad

    # --- writing -------------------------------------------------------------

    def _check_writable(self) -> None:
        if self.readonly:
            raise SnapshotError(f"snapshot {self.snapshot_id} is open read-only")
        if self.frozen:
            raise SnapshotError(f"snapshot {self.snapshot_id} is frozen, create a new one")

    def put(self, key: str, content: bytes, *, source: str, note: str | None = None) -> None:
        """Store a payload. A key is written once: the same content again is a no-op."""
        self._check_writable()
        digest = hashlib.sha256(content).hexdigest()
        if self.has(key):
            if self.entry(key)["sha256"] == digest:
                return
            raise SnapshotError(f"{key} already holds different content in {self.snapshot_id}")
        path = self.dir / "raw" / (key + ".gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the compressed bytes identical across runs.
        with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as handle:
            handle.write(content)
        entry = {"source": redact(source), "fetched_at": _now(), "sha256": digest,
                 "bytes": len(content)}
        if note:
            entry["note"] = note
        self._manifest["entries"][key] = entry
        self._dirty = True
        # A long pull that dies midway should not lose track of what it stored.
        self._unsaved += 1
        if self._unsaved >= AUTOSAVE_EVERY:
            self.save()

    def fetch(self, key: str, url: str, http: Http, *, params: dict | None = None,
              source: str | None = None) -> bytes:
        """The stored payload for key, downloading it first if the snapshot lacks it."""
        if self.has(key):
            return self.read(key)
        self._check_writable()
        content = http.get(url, params=params)
        # put() redacts key values, so the full request URL is safe to record.
        self.put(key, content, source=source or Request("GET", url, params=params).prepare().url)
        return content

    def save(self) -> None:
        if self.readonly or not self._dirty:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self._manifest, indent=1, sort_keys=True, ensure_ascii=False)
        tmp = self._manifest_path.with_suffix(".json.tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(self._manifest_path)
        self._dirty = False
        self._unsaved = 0

    def freeze(self) -> None:
        self._check_writable()
        self._manifest["frozen"] = True
        self._manifest["frozen_at"] = _now()
        self._dirty = True
        self.save()

    def __enter__(self) -> "Snapshot":
        return self

    def __exit__(self, *exc) -> None:
        self.save()
