# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-002 execution may run only what verification approved."""

import inspect

from oak.runner import execution, verification


def test_execution_iterates_the_verified_operation_tuple() -> None:
    """Execution must not re-derive its work list from the raw plan.

    Re-filtering `plan["operations"]` would let an operation that verification
    never inspected run beside one it did.
    """

    source = inspect.getsource(execution.execute_dispatch)
    assert "verified.operations" in source
    assert 'verified.plan["operations"]' not in source


def test_verified_dispatch_exposes_the_approved_operations() -> None:
    fields = verification.VerifiedDispatch.__dataclass_fields__
    assert "operations" in fields


def test_duplicate_operation_kinds_are_rejected() -> None:
    source = inspect.getsource(verification.verify_dispatch)
    assert "more than one operation of the same kind" in source
