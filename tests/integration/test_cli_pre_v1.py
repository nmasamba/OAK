# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-012 and OAK-V1-013: the CLI before 1.0.

`oak keys show` created the trust directory and three private keys as a side effect of a
read (RR-018). The rest are the rough edges the 1.0 review noted without numbering them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oak.interfaces.cli.main import app as cli_app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()

pytestmark = pytest.mark.integration


def _output(result) -> str:  # type: ignore[no-untyped-def]
    return str(result.output) + str(result.stderr or "")


def _files(directory: Path) -> dict[str, int]:
    return {path.name: path.stat().st_mtime_ns for path in sorted(directory.iterdir())}


@pytest.fixture
def trust(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    directory = tmp_path / "trust"
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(directory))
    return directory


def test_keys_show_reads_and_never_creates_what_init_creates(trust: Path) -> None:
    refused = runner.invoke(cli_app, ["keys", "show"])
    assert refused.exit_code == 2
    assert "OAK-KEYS-UNINITIALIZED" in _output(refused)
    assert not trust.exists(), "a read created the trust directory"

    created = runner.invoke(cli_app, ["keys", "init", "--output", "json"])
    assert created.exit_code == 0, _output(created)
    before = _files(trust)
    shown = runner.invoke(cli_app, ["keys", "show", "--output", "json"])
    assert shown.exit_code == 0, _output(shown)
    assert json.loads(shown.stdout)["identities"] == json.loads(created.stdout)["identities"]
    assert _files(trust) == before

    # An uninstall deletes the directory; reading afterwards must not bring the keys back.
    shutil.rmtree(trust)
    again = runner.invoke(cli_app, ["keys", "show"])
    assert again.exit_code == 2
    assert "OAK-KEYS-UNINITIALIZED" in _output(again)
    assert not trust.exists()


def test_keys_show_names_one_missing_key_and_leaves_it_missing(trust: Path) -> None:
    assert runner.invoke(cli_app, ["keys", "init"]).exit_code == 0
    (trust / "approver.key").unlink()

    shown = runner.invoke(cli_app, ["keys", "show"])

    assert shown.exit_code == 2
    assert "OAK-SIGNING-KEY-MISSING" in _output(shown)
    assert not (trust / "approver.key").exists()


# ----- OAK-V1-013: the CLI polish ----------------------------------------------------------


def test_set_key_refuses_an_unknown_store_before_it_asks_for_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))
    asked: list[bool] = []

    def read_key(from_stdin: bool) -> str:
        asked.append(from_stdin)
        return "oak-test-key-huggingface-0123456789abcdef"

    monkeypatch.setattr("oak.interfaces.cli.main._read_key", read_key)

    refused = runner.invoke(cli_app, ["models", "set-key", "huggingface", "--store", "vault"])

    assert refused.exit_code == 2
    assert "OAK-MODEL-CREDENTIAL-SOURCE" in _output(refused)
    assert asked == [], "the key was asked for before the store was checked"


def test_policy_packs_lists_without_a_workspace_and_evaluate_still_needs_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.setenv("OAK_EXTENSIONS_DIRECTORY", str(tmp_path / "extensions"))
    monkeypatch.chdir(tmp_path)

    listed = runner.invoke(cli_app, ["policy", "packs", "--output", "json"])
    assert listed.exit_code == 0, _output(listed)
    assert [pack["id"] for pack in json.loads(listed.stdout)["packs"]]

    evaluate = runner.invoke(cli_app, ["policy", "evaluate", "--pack", "anything"])
    assert evaluate.exit_code == 2
    assert "OAK-WORKSPACE-NOT-FOUND" in _output(evaluate)


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, _limit: int) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.mark.parametrize(
    "server",
    [
        "http://127.0.0.1:9",
        "http://127.0.0.1:9/",
        "http://127.0.0.1:9/v1",
        " http://127.0.0.1:9/v1/ ",
    ],
)
def test_a_server_url_ending_in_v1_reaches_the_same_routes(
    monkeypatch: pytest.MonkeyPatch, server: str
) -> None:
    from oak.interfaces.cli.remote import RemoteClient

    requested: list[str] = []

    def urlopen(request, timeout):  # type: ignore[no-untyped-def]
        requested.append(request.full_url)
        return _Response(b'{"case": {"id": "design-case.x", "version": "0.1.0"}}')

    monkeypatch.setattr("oak.interfaces.cli.remote.urllib.request.urlopen", urlopen)
    RemoteClient(server).get_case("design-case.x")

    assert requested == ["http://127.0.0.1:9/v1/design-cases/design-case.x"]


def _refusing(code: str):  # type: ignore[no-untyped-def]
    import io
    import urllib.error

    def urlopen(request, timeout):  # type: ignore[no-untyped-def]
        body = json.dumps({"code": code, "detail": "The requested resource was not found."})
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", {}, io.BytesIO(body.encode("utf-8"))
        )

    return urlopen


def test_an_unknown_remote_case_is_the_case_not_found_code_and_names_the_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from oak.domain import OAKError
    from oak.interfaces.cli.remote import RemoteClient

    monkeypatch.setattr(
        "oak.interfaces.cli.remote.urllib.request.urlopen", _refusing("OAK-WORKSPACE-NOT-FOUND")
    )
    client = RemoteClient("http://127.0.0.1:9")
    for call in (
        lambda: client.get_case("design-case.absent"),
        lambda: client.research_plan("design-case.absent"),
    ):
        with pytest.raises(OAKError) as missing:
            call()
        assert missing.value.code == "OAK-CASE-NOT-FOUND"
        assert "design-case.absent" in missing.value.message
        assert missing.value.retriable is False

    # Any other not-found code is the server's own and passes through unchanged.
    monkeypatch.setattr(
        "oak.interfaces.cli.remote.urllib.request.urlopen", _refusing("OAK-ARTIFACT-NOT-FOUND")
    )
    with pytest.raises(OAKError) as artifact:
        client.get_case("design-case.absent")
    assert artifact.value.code == "OAK-ARTIFACT-NOT-FOUND"


def test_validate_says_when_it_was_given_the_other_kind_of_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(cli_app, ["init", "ws"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "ws")
    brief = str(ROOT / "examples/briefs/public-manual-qa.yaml")
    assert runner.invoke(cli_app, ["design", brief]).exit_code == 0
    exported = tmp_path / "case-export"
    assert runner.invoke(cli_app, ["export", "--output", str(exported)]).exit_code == 0

    as_bundle = runner.invoke(cli_app, ["validate", "bundle", str(exported)])
    assert as_bundle.exit_code == 2
    assert "OAK-VALIDATE-KIND" in _output(as_bundle)
    assert "validate export" in _output(as_bundle)

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "deployment-bundle.json").write_text("{}", encoding="utf-8")
    as_export = runner.invoke(cli_app, ["validate", "export", str(bundle)])
    assert as_export.exit_code == 2
    assert "OAK-VALIDATE-KIND" in _output(as_export)
    assert "validate bundle" in _output(as_export)


def test_a_narrative_without_record_says_it_applies_only_when_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.chdir(tmp_path)

    reading = runner.invoke(cli_app, ["report", "--narrative", "online"])
    assert "--narrative online applies only with --record" in _output(reading)

    for argv in (["report"], ["report", "--narrative", "online", "--record"]):
        quiet = runner.invoke(cli_app, argv)
        assert "applies only with --record" not in _output(quiet)
