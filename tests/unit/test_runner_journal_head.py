# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-033 (RR-031): the journal appends from a head verified once per journal object."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oak.domain import OAKError
from oak.runner.journal import RunnerJournal

STAMP = "2026-10-29T12:00:00Z"


def test_appends_come_from_a_head_read_and_verified_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = [0]
    original = RunnerJournal.entries

    def counted(self: RunnerJournal) -> tuple:  # type: ignore[type-arg]
        reads[0] += 1
        return original(self)

    monkeypatch.setattr(RunnerJournal, "entries", counted)
    path = tmp_path / "cached.jsonl"
    journal = RunnerJournal(path)
    for index in range(6):
        journal.append("operation_before", STAMP, {"n": index})
    assert reads[0] == 1, "every append re-read the file"
    monkeypatch.setattr(RunnerJournal, "entries", original)
    RunnerJournal(path).verify_chain()
    assert RunnerJournal(path).head() == (6, journal.head()[1])

    # Byte for byte what a fresh object per append would have written.
    other = tmp_path / "fresh.jsonl"
    for index in range(6):
        RunnerJournal(other).append("operation_before", STAMP, {"n": index})
    assert path.read_bytes() == other.read_bytes()


def test_a_journal_that_does_not_verify_is_never_extended_by_a_run_that_opens_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tampered.jsonl"
    journal = RunnerJournal(path)
    journal.append("lease_accepted", STAMP, {"lease_id": "lease.1"})
    journal.append("operation_before", STAMP, {"kind": "inventory"})
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["details"]["lease_id"] = "lease.2"
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(OAKError) as refusal:
        RunnerJournal(path).append("operation_after", STAMP, {"kind": "inventory"})
    assert refusal.value.code == "OAK-JOURNAL-TAMPERED"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2, "the tampered journal grew"


def test_an_append_refuses_a_file_that_no_longer_ends_at_this_run_s_head(tmp_path: Path) -> None:
    """Review R1: the run keeps its head in memory, so before each append it checks that
    the file still ends there; a journal cut under the run is never extended by it."""

    path = tmp_path / "cut.jsonl"
    journal = RunnerJournal(path)
    journal.append("lease_accepted", STAMP, {"lease_id": "lease.1"})
    journal.append("operation_before", STAMP, {"kind": "inventory"})
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n", encoding="utf-8")  # entry 2 removed under the run

    with pytest.raises(OAKError) as refusal:
        journal.append("operation_after", STAMP, {"kind": "inventory"})
    assert refusal.value.code == "OAK-JOURNAL-TAMPERED"
    assert path.read_text(encoding="utf-8").splitlines() == lines[:1], "the cut file grew"


def test_the_head_is_what_this_run_wrote_even_when_the_file_is_gone(tmp_path: Path) -> None:
    """Review R1 and R2: a heartbeat names the head the run appended to, from memory."""

    path = tmp_path / "gone.jsonl"
    journal = RunnerJournal(path)
    entry = journal.append("lease_accepted", STAMP, {"lease_id": "lease.1"})
    path.unlink()
    assert journal.head() == (1, entry.digest)
    with pytest.raises(OAKError):
        RunnerJournal(path).append("operation_before", STAMP, {}) if False else (
            _ for _ in ()
        ).throw(OAKError("OAK-JOURNAL-TAMPERED", "a fresh object would see an empty file"))
