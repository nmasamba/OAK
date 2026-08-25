# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-001..011 signed dispatch journey and adversarial verification."""

import copy
from pathlib import Path

import pytest

from oak.contracts import load_yaml_document
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.runner.execution import execute_dispatch
from oak.runner.journal import RunnerJournal
from oak.runner.verification import RunnerDenialError, TrustAnchors, verify_dispatch
from tests.runner_support import ROOT, build_compiled_case, read_dispatch, tamper, with_time

pytestmark = pytest.mark.integration

MUTATION_TARGET = "local-mutation-fixture.yaml"


def _target(name: str) -> dict:
    return load_yaml_document((ROOT / "examples/targets" / name).read_text(encoding="utf-8"))


def _dispatch_readonly(tmp_path: Path):
    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(
        ("inventory", "validate", "render", "plan", "verify"),
        harness.context("dispatch-readonly-1", "0.1.9"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    return harness, envelope, attachments


@pytest.fixture(scope="module")
def readonly_dispatch(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("readonly")
    harness, envelope, attachments = _dispatch_readonly(tmp_path)
    return {
        "trust_directory": harness.trust_directory,
        "registry": harness.registry,
        "now": harness.now,
        "envelope": envelope,
        "attachments": attachments,
    }


def _verify(
    state, *, target_name="local-fixture.yaml", envelope=None, attachments=None, **overrides
):
    kwargs: dict = {
        "envelope": copy.deepcopy(envelope if envelope is not None else state["envelope"]),
        "attachments": copy.deepcopy(
            attachments if attachments is not None else state["attachments"]
        ),
        "registry": state["registry"],
        "anchors": TrustAnchors.from_directory(state["trust_directory"]),
        "target_document": _target(target_name),
        "revoked_approval_ids": frozenset(),
        "seen_lease_nonces": frozenset(),
        "now": with_time(state["now"], 60),
    }
    kwargs.update(overrides)
    return verify_dispatch(**kwargs)


def test_read_only_dispatch_verifies_and_executes(readonly_dispatch, tmp_path: Path) -> None:
    verified = _verify(readonly_dispatch)
    assert verified.requested_kinds == ("inventory", "validate", "render", "plan", "verify")
    journal = RunnerJournal(tmp_path / "journal.jsonl")
    outcome = execute_dispatch(
        verified,
        journal=journal,
        target_document=_target("local-fixture.yaml"),
        registry=readonly_dispatch["registry"],
        now=with_time(readonly_dispatch["now"], 61),
    )
    assert outcome.outcome == "succeeded"
    assert set(outcome.applied_kinds) == {"inventory", "validate", "render", "plan", "verify"}
    journal.verify_chain()


def test_tampered_plan_is_denied_before_execution(readonly_dispatch) -> None:
    attachments = copy.deepcopy(readonly_dispatch["attachments"])
    attachments["plan"] = tamper(attachments["plan"], "/status", "approved")
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, attachments=attachments)
    assert caught.value.code == "OAK-RUNNER-DIGEST"


def test_wrong_target_fingerprint_is_denied(readonly_dispatch) -> None:
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, target_name=MUTATION_TARGET)
    assert caught.value.code == "OAK-RUNNER-TARGET"


def test_expired_lease_is_denied(readonly_dispatch) -> None:
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, now=with_time(readonly_dispatch["now"], 10_000))
    assert caught.value.code == "OAK-RUNNER-LEASE"


def test_replayed_lease_nonce_is_denied(readonly_dispatch) -> None:
    seen = frozenset({readonly_dispatch["envelope"]["lease"]["nonce"]})
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, seen_lease_nonces=seen)
    assert caught.value.code == "OAK-RUNNER-REPLAY"


def test_untrusted_signer_is_denied(readonly_dispatch) -> None:
    empty = TrustAnchors(keys_by_role={"plan-signer": {}, "approver": {}})
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, anchors=empty)
    assert caught.value.code == "OAK-RUNNER-TRUST"


def test_revoked_approval_is_denied(readonly_dispatch) -> None:
    approval_id = readonly_dispatch["envelope"]["approval_refs"][0]["id"]
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, revoked_approval_ids=frozenset({approval_id}))
    assert caught.value.code == "OAK-RUNNER-APPROVAL"


def test_forbidden_execution_field_is_denied(readonly_dispatch) -> None:
    attachments = copy.deepcopy(readonly_dispatch["attachments"])
    plan = attachments["plan"]
    plan["operations"][0]["parameters"]["command"] = "rm -rf /"
    envelope = tamper(
        readonly_dispatch["envelope"],
        "/plan_ref/digest",
        content_digest(canonical_json_bytes(plan)),
    )
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, envelope=envelope, attachments=attachments)
    assert caught.value.code in {
        "OAK-RUNNER-SIGNATURE",
        "OAK-RUNNER-PARAMETERS",
        "OAK-RUNNER-SCHEMA",
    }


def test_dispatch_without_signing_is_refused(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(("inventory",), harness.context("dispatch-nosign-01", "0.1.7"))
    assert caught.value.code == "OAK-DEPENDENCY-MISSING"


def test_dispatch_without_approval_is_refused(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(("inventory",), harness.context("dispatch-noappr-01", "0.1.8"))
    assert caught.value.code == "OAK-DISPATCH-APPROVAL"


def test_mutating_dispatch_applies_and_rolls_back(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.approve("apply", harness.context("approve-apply-00001", "0.1.9"))
    harness.release.approve("rollback", harness.context("approve-rollbk-0001", "0.1.10"))
    harness.release.dispatch(
        ("apply", "verify", "rollback"),
        harness.context("dispatch-mutating-1", "0.1.11"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    verified = verify_dispatch(
        envelope=envelope,
        attachments=attachments,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        target_document=_target(MUTATION_TARGET),
        revoked_approval_ids=frozenset(),
        seen_lease_nonces=frozenset(),
        now=with_time(harness.now, 60),
    )
    assert "apply" in verified.requested_kinds


def test_mutating_dispatch_without_apply_approval_is_denied(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(
            ("apply", "verify"), harness.context("dispatch-noapply-1", "0.1.9")
        )
    assert caught.value.code == "OAK-DISPATCH-APPROVAL"


def test_a_disallowed_registry_is_denied_before_any_adapter_exists(tmp_path: Path) -> None:
    """A target allowlist that excludes the image's registry denies the dispatch.

    The whole chain is authentic — compiled, signed, and approved against this exact
    profile — so the denial is the new admission control, not a broken signature. The
    denial comes from `verify_dispatch`, which cannot construct an adapter: the module
    imports none, so no docker invocation can precede it structurally.
    """

    import yaml

    source = load_yaml_document(
        (ROOT / "examples/targets" / MUTATION_TARGET).read_text(encoding="utf-8")
    )
    source["execution"]["allowed_registries"] = ["registry.example.internal"]
    variant = tmp_path / "disallowed-registry-target.yaml"
    variant.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    harness = build_compiled_case(tmp_path, target_name=str(variant))
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.approve("apply", harness.context("approve-apply-00001", "0.1.9"))
    harness.release.approve("rollback", harness.context("approve-rollbk-0001", "0.1.10"))
    harness.release.dispatch(
        ("apply", "verify", "rollback"),
        harness.context("dispatch-mutating-1", "0.1.11"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    with pytest.raises(RunnerDenialError) as caught:
        verify_dispatch(
            envelope=envelope,
            attachments=attachments,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            target_document=source,
            revoked_approval_ids=frozenset(),
            seen_lease_nonces=frozenset(),
            now=with_time(harness.now, 60),
        )
    assert caught.value.code == "OAK-RUNNER-REGISTRY"


def test_an_allowlisted_registry_still_verifies(tmp_path: Path) -> None:
    """The shipped mutation fixture allowlists docker.io and must keep working."""

    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.approve("apply", harness.context("approve-apply-00001", "0.1.9"))
    harness.release.approve("rollback", harness.context("approve-rollbk-0001", "0.1.10"))
    harness.release.dispatch(
        ("apply", "verify", "rollback"),
        harness.context("dispatch-mutating-1", "0.1.11"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    verified = verify_dispatch(
        envelope=envelope,
        attachments=attachments,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        target_document=_target(MUTATION_TARGET),
        revoked_approval_ids=frozenset(),
        seen_lease_nonces=frozenset(),
        now=with_time(harness.now, 60),
    )
    assert "apply" in verified.requested_kinds


def test_the_verification_policy_clauses_are_where_the_runner_reads_them(
    readonly_dispatch,
) -> None:
    """The policy guard must be reachable for the document the compiler actually emits.

    `verify_dispatch` used to read `policy.get("body", policy)`. No compiled verification
    policy has ever carried a `body` key — the clauses live under `content` — so the
    lookup always returned the wrapper, the comparison was always against `None`, and the
    guard could not fire for any plan the compiler produces.

    Substituting the policy outright is already caught earlier by the digest check
    (`test_tampered_plan_is_denied_before_execution` shows that path), so this asserts the
    narrower thing that was actually broken: the compiler's write key and the runner's
    read key agree, and the clauses the guard inspects are present and true.
    """

    policy = readonly_dispatch["attachments"]["verification-policy"]

    assert "body" not in policy, "the key the old lookup used must not silently appear"
    content = policy["content"]
    assert isinstance(content, dict)
    assert content["requires_signature_before_dispatch"] is True
    assert content["requires_approval_before_dispatch"] is True

    source = (ROOT / "src" / "oak" / "runner" / "verification.py").read_text(encoding="utf-8")
    assert 'policy.get("content")' in source, "the runner must read the clauses from `content`"


def test_a_read_only_dispatch_still_verifies_with_the_policy_guard_live(
    readonly_dispatch,
) -> None:
    """Making a dead guard live must not deny what the release already ships."""

    verified = _verify(readonly_dispatch)

    assert set(verified.requested_kinds) == {"inventory", "validate", "render", "plan", "verify"}


def test_the_compiled_policy_reflects_its_target(readonly_dispatch, tmp_path: Path) -> None:
    """RR-032: the policy is a function of the target, not a constant.

    The read-only compile carries the five read-only kinds and `mutation_allowed:
    false`; the mutation compile carries every target-allowed kind and `true`. The
    policy id names the target, because one constant id for two different policies
    would collide in the workspace index.
    """

    readonly_policy = readonly_dispatch["attachments"]["verification-policy"]
    assert readonly_policy["id"] == "verification-policy.target.local-fixture"
    assert readonly_policy["content"]["allowed_operation_kinds"] == [
        "inventory",
        "validate",
        "render",
        "plan",
        "verify",
    ]
    assert readonly_policy["content"]["mutation_allowed"] is False

    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(("inventory",), harness.context("dispatch-readonly-1", "0.1.9"))
    _, attachments = read_dispatch(harness.mailbox_root)
    mutation_policy = attachments["verification-policy"]
    assert mutation_policy["id"] == "verification-policy.target.local-mutation-fixture"
    assert mutation_policy["content"]["allowed_operation_kinds"] == [
        "inventory",
        "validate",
        "render",
        "plan",
        "verify",
        "apply",
        "rollback",
        "destroy",
    ]
    assert mutation_policy["content"]["mutation_allowed"] is True


def _resigned_envelope(envelope: dict, trust_directory: Path) -> dict:
    """Sign an edited envelope with the harness's own plan-signer key.

    The policy reference sits under the envelope signature, so a policy-substitution
    case cannot be produced by tampering — and an authentically signed restrictive
    policy is the stronger case anyway: a signer issued it, and the runner must honour
    it rather than the plan's wider contents.
    """

    from oak.adapters.signing import LocalEd25519Signer
    from oak.contracts.signatures import signed_payload_bytes

    signer = LocalEd25519Signer.load(trust_directory, "plan-signer")
    identity = signer.identity()
    document = {key: value for key, value in envelope.items() if key != "signature"}
    document["signature"] = {
        "role": identity.role,
        "key_id": identity.key_id,
        "algorithm": identity.algorithm,
        "public_key_base64": identity.public_key_base64,
        "trust_level": identity.trust_level,
        "signature_base64": signer.sign(signed_payload_bytes(document)),
    }
    return document


def _restrictive_policy() -> dict:
    return {
        "schema_version": "0.4.0",
        "id": "verification-policy.target.local-mutation-fixture",
        "version": "0.1.0",
        "artifact_type": "verification_policy",
        "status": "draft",
        "content": {
            "allowed_status": "draft",
            "allowed_operation_kinds": ["inventory", "validate", "render", "plan", "verify"],
            "mutation_allowed": False,
            "requires_signature_before_dispatch": True,
            "requires_approval_before_dispatch": True,
        },
        "extensions": {},
    }


def _mutation_dispatch_with_policy(tmp_path: Path, policy: dict, *, now: str | None = None):
    """A signed, fully approved mutation dispatch carrying the given authentic policy."""

    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET, now=now)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.approve("apply", harness.context("approve-apply-00001", "0.1.9"))
    harness.release.approve("rollback", harness.context("approve-rollbk-0001", "0.1.10"))
    harness.release.dispatch(
        ("apply", "verify", "rollback"),
        harness.context("dispatch-mutating-1", "0.1.11"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    reference = dict(envelope["verification_policy_ref"])
    reference["id"] = policy["id"]
    reference["digest"] = content_digest(canonical_json_bytes(policy))
    envelope["verification_policy_ref"] = reference
    envelope = _resigned_envelope(envelope, harness.trust_directory)
    attachments["verification-policy"] = policy
    return harness, envelope, attachments


def test_a_policy_forbidding_the_requested_kind_denies_the_mutation(tmp_path: Path) -> None:
    """An authentic restrictive policy denies a signed, fully approved mutation.

    Every other credential in the dispatch is valid — signature, approvals, target,
    lease — so the denial can only be the newly enforced clauses. `verify_dispatch`
    raises before returning, and adapters are constructed only from its return value,
    so no side effect can precede the denial.
    """

    harness, envelope, attachments = _mutation_dispatch_with_policy(tmp_path, _restrictive_policy())
    with pytest.raises(RunnerDenialError) as caught:
        verify_dispatch(
            envelope=envelope,
            attachments=attachments,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            target_document=_target(MUTATION_TARGET),
            revoked_approval_ids=frozenset(),
            seen_lease_nonces=frozenset(),
            now=with_time(harness.now, 60),
        )
    assert caught.value.code == "OAK-RUNNER-POLICY"


@pytest.mark.parametrize(
    "clauses",
    [
        {"allowed_operation_kinds": "everything"},
        {"allowed_operation_kinds": ["inventory", 7]},
        {"mutation_allowed": "yes"},
    ],
)
def test_a_policy_with_malformed_clauses_is_refused(tmp_path: Path, clauses: dict) -> None:
    """Malformed policy clauses fail closed, never open."""

    policy = _restrictive_policy()
    policy["content"] = {**policy["content"], **clauses}
    harness, envelope, attachments = _mutation_dispatch_with_policy(tmp_path, policy)
    with pytest.raises(RunnerDenialError) as caught:
        verify_dispatch(
            envelope=envelope,
            attachments=attachments,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            target_document=_target(MUTATION_TARGET),
            revoked_approval_ids=frozenset(),
            seen_lease_nonces=frozenset(),
            now=with_time(harness.now, 60),
        )
    assert caught.value.code == "OAK-RUNNER-POLICY"


def test_a_denied_policy_leaves_no_journal_and_publishes_a_denial(
    tmp_path: Path, monkeypatch
) -> None:
    """The full runner path: a restrictive policy denies with no side effect at all.

    Uses real timestamps so the lease and approvals are current when `run_once` reads
    its own clock; the fixed harness clock would read as an expired lease and mask the
    policy denial behind `OAK-RUNNER-LEASE`.
    """

    import json as json_module
    from datetime import UTC, datetime

    from oak.runner.main import run_once

    real_now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    harness, envelope, attachments = _mutation_dispatch_with_policy(
        tmp_path, _restrictive_policy(), now=real_now
    )
    dispatch_dir = next((harness.mailbox_root / "dispatches").iterdir())
    (dispatch_dir / "envelope.json").write_bytes(canonical_json_bytes(envelope))
    (dispatch_dir / "verification-policy.json").write_bytes(
        canonical_json_bytes(attachments["verification-policy"])
    )

    home = tmp_path / "runner-home"
    monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(harness.mailbox_root))
    monkeypatch.setenv("OAK_RUNNER_HOME", str(home))
    monkeypatch.setenv("OAK_RUNNER_TRUST_ANCHORS", str(harness.trust_directory))
    monkeypatch.setenv(
        "OAK_RUNNER_TARGET_PROFILE",
        str(ROOT / "examples/targets" / MUTATION_TARGET),
    )
    assert run_once() == 0

    assert not (home / "journals").exists(), "a denied dispatch must never open a journal"
    messages = sorted((harness.mailbox_root / "messages").glob("*.json"))
    assert messages, "the denial must be published as a signed completion"
    payloads = [json_module.loads(path.read_text(encoding="utf-8"))["payload"] for path in messages]
    assert any(
        entry["outcome"] == "denied" and entry["denial_code"] == "OAK-RUNNER-POLICY"
        for entry in payloads
    )
