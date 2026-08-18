# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-003 hash-chained runner journal integrity and resume state."""

from pathlib import Path

import pytest

from oak.domain import OAKError
from oak.runner.journal import RunnerJournal


def test_chain_verifies_and_detects_tampering(tmp_path: Path) -> None:
    journal = RunnerJournal(tmp_path / "j.jsonl")
    journal.append("lease_accepted", "2026-08-18T12:00:00Z", {"lease_id": "lease.1"})
    journal.append("operation_before", "2026-08-18T12:00:01Z", {"operation_id": "op.1"})
    journal.append("operation_after", "2026-08-18T12:00:02Z", {"operation_id": "op.1"})
    journal.verify_chain()

    lines = (tmp_path / "j.jsonl").read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("op.1", "op.evil")
    (tmp_path / "j.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(OAKError, match="hash chain does not verify"):
        RunnerJournal(tmp_path / "j.jsonl").verify_chain()


def test_incomplete_operation_is_detected_on_resume(tmp_path: Path) -> None:
    journal = RunnerJournal(tmp_path / "j.jsonl")
    journal.append("lease_accepted", "2026-08-18T12:00:00Z", {"lease_id": "lease.1"})
    journal.append("operation_before", "2026-08-18T12:00:01Z", {"operation_id": "op.apply"})
    # crash before the after-entry
    assert journal.incomplete_operation() == {"operation_id": "op.apply"}

    journal.append("operation_after", "2026-08-18T12:00:02Z", {"operation_id": "op.apply"})
    assert journal.incomplete_operation() is None


def test_manual_recovery_state_sticks(tmp_path: Path) -> None:
    journal = RunnerJournal(tmp_path / "j.jsonl")
    assert not journal.requires_manual_recovery()
    journal.append(
        "manual_recovery_required", "2026-08-18T12:00:00Z", {"reason": "rollback failed"}
    )
    assert journal.requires_manual_recovery()


def test_unknown_entry_type_is_rejected(tmp_path: Path) -> None:
    journal = RunnerJournal(tmp_path / "j.jsonl")
    with pytest.raises(OAKError, match="journal entry type is not recognized"):
        journal.append("arbitrary", "2026-08-18T12:00:00Z", {})
