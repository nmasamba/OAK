# SPDX-License-Identifier: Apache-2.0
"""Check that source, CI, container, package, documentation, and version declarations agree,
and that the binaries actually running match the pins."""

import json
import platform
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(root: Path, relative: str, failures: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        failures.append(f"{relative}: missing or unreadable")
        return ""


def _match_version(
    text: str,
    pattern: str,
    source: str,
    failures: list[str],
) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        failures.append(f"{source}: expected pinned version with immutable digest")
        return ""
    return match.group("version")


# One `uses:` step: the action, the ref it is fetched at, and the release named in a comment.
_USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:")
_USES = re.compile(
    r"^\s*(?:-\s+)?uses:\s*(?P<action>[^@\s#]+)@(?P<ref>[^\s#]+)"
    r"(?:\s+#\s*(?P<release>\S+))?\s*$"
)
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_RELEASE = re.compile(r"v\d+(?:\.\d+){0,2}")


def _pinned_actions(text: str, source: str, failures: list[str]) -> dict[str, str]:
    """Return each action a workflow uses, mapped to the release its pin names.

    Every action must be fetched at a full commit SHA. A tag such as `@v4` is whatever the
    action's repository says it is on the day the job runs, and a compromised repository
    can move it to other code; a commit cannot be moved. The trailing comment names the
    release the SHA was taken from, so a reviewer can read what the pin is.
    """

    actions: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if _USES_LINE.match(line) is None:
            continue
        match = _USES.match(line)
        if match is None:
            failures.append(f"{source}: line {number} names an action without a ref")
            continue
        action = match.group("action")
        release = match.group("release")
        if _COMMIT_SHA.fullmatch(match.group("ref")) is None:
            failures.append(f"{source}: {action} is not pinned by commit SHA")
        elif release is None or _RELEASE.fullmatch(release) is None:
            failures.append(f"{source}: {action} must name the release its SHA was taken from")
        actions[action] = release or ""
    return actions


def _check_database_suites(
    text: str, label: str, compose_image: str | None, failures: list[str]
) -> None:
    """A gate runs the PostgreSQL-gated suites on the database image compose.yaml pins."""

    service = re.search(r"^        image: (postgres:\S+)$", text, flags=re.MULTILINE)
    if compose_image is not None and (service is None or service.group(1) != compose_image):
        failures.append(f"{label}: the database service must run compose.yaml's postgres image")
    if "OAK_TEST_DATABASE_URL:" not in text or "oak-db-migrate" not in text:
        failures.append(
            f"{label}: the PostgreSQL-gated suites must run "
            "(OAK_TEST_DATABASE_URL and oak-db-migrate)"
        )


def _check_browser_suite(
    text: str, label: str, failures: list[str], *, gated: tuple[str, ...] = ()
) -> None:
    """A gate runs the browser suite on a stack of its own and uploads nothing from it.

    The suite's skips are checked by the script, so a job that ran Playwright some other way
    could go green on a widening skip. A failed page's trace or screenshot can show a brief
    or a model-key field, so the job uploads nothing and reads no secret (RR-021).
    """

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        failures.append(f"{label}: the workflow is not valid YAML")
        return
    jobs = document.get("jobs") if isinstance(document, dict) else None
    jobs = jobs if isinstance(jobs, dict) else {}
    job = jobs.get("web-e2e")
    if not isinstance(job, dict):
        failures.append(f"{label}: the browser suite must run (a web-e2e job)")
        return
    steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
    runs = _runs(job)
    if "needs" in job:
        failures.append(f"{label}: the web-e2e job must not wait on another job")
    if "pnpm --dir web exec playwright install --with-deps chromium" not in runs:
        failures.append(f"{label}: the web-e2e job must install the Chromium Playwright pins")
    if _SUITE_RUN not in runs:
        failures.append(f"{label}: the web-e2e job must run scripts/run_browser_suite.py")
    # An allowlist of actions, not a list of upload names; the checkout keeps no token on
    # disk; and no expression in the job or the workflow-wide settings it inherits names a
    # secret or the job's token.
    actions = [str(step["uses"]).split("@", 1)[0] for step in steps if "uses" in step]
    checkouts = [step for step in steps if str(step.get("uses", "")).startswith(_CHECKOUT)]
    inherited = {key: document.get(key) for key in ("env", "defaults") if key in document}
    text = yaml.safe_dump([job, inherited])
    if (
        any(action not in _BROWSER_ACTIONS for action in actions)
        or not checkouts
        or any(
            (step.get("with") or {}).get("persist-credentials") is not False for step in checkouts
        )
        or _SECRET.search(text)
    ):
        failures.append(f"{label}: the web-e2e job must upload nothing and read no secret")
    for name in gated:
        gate = jobs.get(name)
        needs = gate.get("needs", []) if isinstance(gate, dict) else []
        # `if: always()` would run the job after a failed suite.
        if (
            not isinstance(gate, dict)
            or not _binding(gate)
            or "web-e2e" not in ([needs] if isinstance(needs, str) else needs)
        ):
            failures.append(f"{label}: the {name} job must wait for the browser suite")


_SHELLS = frozenset({"bash", "sh"})
# The gate commands, exactly: a `|| true`, a `--help` or any other argument would make one
# pass without running it.
_SUITE_RUN = (
    'python3 scripts/run_browser_suite.py --project "oak-e2e-${{ github.run_id }}-'
    '${{ github.run_attempt }}" --commit "${{ github.sha }}"'
)
_LEDGER = "${{ runner.temp }}/skips.jsonl"
_CHECKOUT = "actions/checkout@"
_BROWSER_ACTIONS = frozenset({"actions/checkout", "actions/setup-node"})
# A secret, or the job's token, in any spelling GitHub accepts: contexts are matched
# without regard to case, and indexed or serialised as well as dotted.
_SECRET = re.compile(
    r"\bsecrets\b|github\s*(?:\.\s*token|\[\s*['\"]token['\"]\s*\])|github_token"
    r"|tojson\(\s*github\s*\)",
    re.IGNORECASE,
)
# Steps each gate must run as written, beside the ones checked above.
_REQUIRED_RUNS = {
    ("CI workflow", "check"): ("make build", "make audit"),
    ("release workflow", "artifacts"): (
        "make release",
        "uv run python scripts/verify_release.py --checksums-only dist/release",
    ),
}


def _check_workflow_settings(text: str, label: str, failures: list[str]) -> None:
    """Nothing workflow-wide may turn every step into a no-op: no `defaults.run.shell` but
    a real shell, and no `MAKE*` variable (`MAKEFLAGS=-n` makes `make check` a dry run)."""

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return
    if not isinstance(document, dict):
        return
    defaults = document.get("defaults")
    run_defaults = defaults.get("run") if isinstance(defaults, dict) else None
    shell = run_defaults.get("shell") if isinstance(run_defaults, dict) else None
    if shell is not None and shell not in _SHELLS:
        failures.append(f"{label}: the workflow's default shell must be bash or sh")
    scopes = [document.get("env")]
    for job in (document.get("jobs") or {}).values():
        if isinstance(job, dict):
            scopes.append(job.get("env"))
            scopes += [step.get("env") for step in job.get("steps", []) if isinstance(step, dict)]
    if any(
        str(key).upper().startswith(("MAKE", "GNUMAKE"))
        for scope in scopes
        if isinstance(scope, dict)
        for key in scope
    ):
        failures.append(f"{label}: no step may set a MAKE variable")


def _check_required_runs(text: str, label: str, failures: list[str]) -> None:
    jobs = _jobs(text)
    for (source, name), commands in _REQUIRED_RUNS.items():
        if source != label:
            continue
        runs = _runs(jobs[name]) if isinstance(jobs.get(name), dict) else []
        for command in commands:
            if command not in runs:
                failures.append(f"{label}: the {name} job must run `{command}`")


def _jobs(text: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    jobs = document.get("jobs") if isinstance(document, dict) else None
    return jobs if isinstance(jobs, dict) else {}


def _runs(job: dict[str, Any]) -> list[str]:
    """The commands a job always runs: a step that can be skipped or fail quietly is none."""

    if not _binding(job):
        return []
    return [
        str(step.get("run", "")).strip()
        for step in job.get("steps", [])
        if isinstance(step, dict) and _binding(step)
    ]


def _binding(item: dict[str, Any]) -> bool:
    """Whether a job or step always runs, in a shell that stops on failure, and fails its
    job when it fails."""

    defaults = item.get("defaults")
    run_defaults = defaults.get("run") if isinstance(defaults, dict) else None
    shells = (
        item.get("shell"),
        run_defaults.get("shell") if isinstance(run_defaults, dict) else None,
    )
    return (
        "if" not in item
        and not item.get("continue-on-error")
        and all(shell is None or shell in _SHELLS for shell in shells)
    )


def _check_counted_skips(
    jobs: dict[str, Any], name: str, key: str, label: str, failures: list[str]
) -> None:
    """A job's `make check` names its skips, and the job fails unless they are expected."""

    job = jobs.get(name)
    steps = job.get("steps", []) if isinstance(job, dict) and _binding(job) else []
    ledgered = any(
        isinstance(step, dict)
        and _binding(step)
        and str(step.get("run", "")).strip() == "make check"
        and step.get("env") == {"OAK_SKIP_LEDGER": _LEDGER}
        for step in steps
    )
    checked = f'python3 scripts/check_skips.py "{_LEDGER}" {key}' in (
        _runs(job) if isinstance(job, dict) else []
    )
    if not (ledgered and checked):
        failures.append(f"{label}: the {name} job must count its skips against {key}")


# The platforms (RR-014): each job, its pinned runner label, what proves where it ran and
# the skips it is counted against.
_PLATFORM_JOBS = {
    "check": ("ubuntu-latest", "linux-x86_64", "check-linux-x86_64"),
    "check-macos-arm64": ("macos-15", "macosx-11.0-arm64", "check-macos-arm64"),
    "check-linux-arm64": ("ubuntu-24.04-arm", "linux-aarch64", "check-linux-arm64"),
}
_PLATFORM_ASSERT = (
    'uv run python -c "import sysconfig, sys; platform = sysconfig.get_platform(); '
    "print(platform); sys.exit(platform != '{tag}')\""
)


def _check_platform(
    jobs: dict[str, Any], name: str, runner: str, tag: str, label: str, failures: list[str]
) -> None:
    """A job runs on its pinned runner, waits on no other job and proves its venv's platform."""

    job = jobs.get(name)
    if not isinstance(job, dict):
        failures.append(f"{label}: the {name} job is missing")
        return
    if job.get("runs-on") != runner:
        failures.append(f"{label}: the {name} job must run on {runner}")
    if _PLATFORM_ASSERT.format(tag=tag) not in _runs(job):
        failures.append(f"{label}: the {name} job must assert a {tag} venv")


def _check_platform_jobs(text: str, compose_image: str | None, failures: list[str]) -> None:
    jobs = _jobs(text)
    for name, (runner, platform_tag, key) in _PLATFORM_JOBS.items():
        _check_platform(jobs, name, runner, platform_tag, "CI workflow", failures)
        if isinstance(jobs.get(name), dict) and "needs" in jobs[name]:
            failures.append(f"CI workflow: the {name} job must not wait on another job")
        _check_counted_skips(jobs, name, key, "CI workflow", failures)
    arm = jobs.get("check-linux-arm64")
    if isinstance(arm, dict):
        _check_database_suites(yaml.safe_dump(arm, width=1000), "CI arm64 job", None, failures)
        services = arm.get("services") or {}
        postgres = services.get("postgres") if isinstance(services, dict) else None
        if compose_image is not None and (
            not isinstance(postgres, dict) or postgres.get("image") != compose_image
        ):
            failures.append("CI arm64 job: the database service must run compose.yaml's image")
        build = next((run for run in _runs(arm) if _REPRODUCE in run), "")
        if not all(
            fragment in build
            for fragment in (
                "deploy/images/api.Dockerfile",
                "deploy/images/web.Dockerfile",
                'test "$architecture" = arm64',
            )
        ):
            failures.append("CI arm64 job: both images must be built and checked as arm64")


_BUILDKIT_PIN = re.compile(r"^image=moby/buildkit:v\d+\.\d+\.\d+@sha256:[a-f0-9]{64}$")
_REPRODUCE = "scripts/reproduce_images.py"


def _check_image_reproduction(
    text: str, label: str, job_name: str, platform: str, failures: list[str]
) -> str | None:
    """The job builds both images twice for its platform on a pinned BuildKit (RR-006).

    Returns the BuildKit pin it found, so the caller can require one pin across workflows.
    """

    job = _jobs(text).get(job_name)
    if not isinstance(job, dict):
        failures.append(f"{label}: the {job_name} job is missing")
        return None
    steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
    pins = [
        str((step.get("with") or {}).get("driver-opts", "")).strip()
        for step in steps
        if str(step.get("uses", "")).startswith("docker/setup-buildx-action")
    ]
    if len(pins) != 1 or _BUILDKIT_PIN.match(pins[0]) is None:
        failures.append(
            f"{label}: the {job_name} job must pin BuildKit by version and digest "
            "(setup-buildx driver-opts image=moby/buildkit:vX.Y.Z@sha256:...)"
        )
    reproduce = next((run for run in _runs(job) if _REPRODUCE in run), "")
    if not all(
        fragment in reproduce
        for fragment in (
            f"--platform {platform}",
            "deploy/images/api.Dockerfile",
            "deploy/images/web.Dockerfile",
        )
    ):
        failures.append(
            f"{label}: the {job_name} job must build both images twice for {platform} "
            f"with {_REPRODUCE}"
        )
    return pins[0] if len(pins) == 1 else None


def _load_package(text: str, failures: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        failures.append("package.json: invalid JSON")
        return {}
    if not isinstance(value, dict):
        failures.append("package.json: root must be an object")
        return {}
    return value


def _npm_version(pep440: str) -> str:
    """Return the npm spelling of a PEP 440 repository version.

    The Python and npm version grammars disagree about pre-releases: PEP 440
    writes ``0.8.0.dev8`` where npm requires ``0.8.0-dev.8``. Releases are
    spelled identically in both, so this only matters between releases.
    """

    for marker in (".dev", ".rc", ".a", ".b"):
        head, separator, tail = pep440.partition(marker)
        if separator:
            return f"{head}-{marker.lstrip('.')}.{tail}"
    return pep440


def _check_release_version(root: Path, failures: list[str]) -> None:
    """Check that every file naming the repository version agrees with VERSION."""

    version = _read(root, "VERSION", failures).strip()
    if not version:
        return

    pyproject = _read(root, "pyproject.toml", failures)
    if f'\nversion = "{version}"\n' not in pyproject:
        failures.append("pyproject.toml: project version differs from VERSION")

    status = _read(root, "STATUS.md", failures)
    if f"- **Repository version:** `{version}`" not in status:
        failures.append("STATUS.md: reported repository version differs from VERSION")

    npm_version = _npm_version(version)
    for relative in ("package.json", "web/package.json"):
        text = _read(root, relative, failures)
        if not text:
            continue
        try:
            declared = json.loads(text).get("version")
        except json.JSONDecodeError:
            failures.append(f"{relative}: invalid JSON")
            continue
        if declared != npm_version:
            failures.append(f"{relative}: version {declared!r} differs from VERSION {version!r}")

    openapi = _read(root, "openapi/oak.openapi.json", failures)
    if openapi:
        try:
            info = json.loads(openapi).get("info", {})
        except json.JSONDecodeError:
            failures.append("openapi/oak.openapi.json: invalid JSON")
        else:
            if info.get("version") != version:
                failures.append("openapi/oak.openapi.json: info.version differs from VERSION")


def check(root: Path = ROOT) -> list[str]:
    """Return stable descriptions of every toolchain-contract mismatch."""

    failures: list[str] = []
    python_version = _read(root, ".python-version", failures).strip()
    node_version = _read(root, ".node-version", failures).strip()
    package = _load_package(_read(root, "package.json", failures), failures)
    api_dockerfile = _read(root, "deploy/images/api.Dockerfile", failures)
    web_dockerfile = _read(root, "deploy/images/web.Dockerfile", failures)
    compose = _read(root, "compose.yaml", failures)
    workflow = _read(root, ".github/workflows/ci.yml", failures)
    release_workflow = _read(root, ".github/workflows/release.yml", failures)
    readme = _read(root, "README.md", failures)
    development = _read(root, "docs/development.md", failures)

    uv_version = _match_version(
        api_dockerfile,
        r"^FROM ghcr\.io/astral-sh/uv:(?P<version>\d+\.\d+\.\d+)@sha256:[a-f0-9]{64} AS uv$",
        "deploy/images/api.Dockerfile",
        failures,
    )
    container_python = _match_version(
        api_dockerfile,
        r"^FROM python:(?P<version>\d+\.\d+\.\d+)-slim@sha256:[a-f0-9]{64}$",
        "deploy/images/api.Dockerfile",
        failures,
    )
    container_node = _match_version(
        web_dockerfile,
        r"^FROM node:(?P<version>\d+\.\d+\.\d+)-alpine@sha256:[a-f0-9]{64} AS build$",
        "deploy/images/web.Dockerfile",
        failures,
    )
    # The build stage carries its own FROM line; the anchored runtime pattern above
    # cannot match it, so without this check the two Python pins could silently diverge
    # and the build stage would escape drift detection entirely.
    container_python_build = _match_version(
        api_dockerfile,
        r"^FROM python:(?P<version>\d+\.\d+\.\d+)-slim@sha256:[a-f0-9]{64} AS build$",
        "deploy/images/api.Dockerfile",
        failures,
    )
    # The web runtime base and the compose postgres image are version-pinned to nothing
    # else in the repository, so the only checkable property is that each stays pinned by
    # tag plus immutable digest; an unpinned line here previously escaped drift detection.
    if not re.search(
        r"^FROM nginxinc/nginx-unprivileged:\d+\.\d+\.\d+-trixie@sha256:[a-f0-9]{64}$",
        web_dockerfile,
        flags=re.MULTILINE,
    ):
        failures.append("deploy/images/web.Dockerfile: expected pinned unprivileged nginx runtime")
    if not re.search(
        r"^    image: postgres:\d+\.\d+-alpine@sha256:[a-f0-9]{64}$",
        compose,
        flags=re.MULTILINE,
    ):
        failures.append("compose.yaml: expected pinned postgres image with immutable digest")

    if python_version and container_python != python_version:
        failures.append("Python version differs between .python-version and API container")
    if python_version and container_python_build != python_version:
        failures.append("Python version differs between .python-version and API build stage")
    if node_version and container_node != node_version:
        failures.append("Node version differs between .node-version and web container")

    engines = package.get("engines")
    if not isinstance(engines, dict):
        failures.append("package.json: engines must be an object")
        engines = {}
    if node_version and engines.get("node") != node_version:
        failures.append("Node version differs between .node-version and package.json")

    # devEngines.runtime is what makes pnpm provision the pinned Node itself instead of
    # trusting whatever Node happens to invoke it (RR-034). An engines pin without it is
    # a declaration nothing enforces at run time.
    runtime = package.get("devEngines", {}).get("runtime") if isinstance(package, dict) else None
    if not isinstance(runtime, dict):
        failures.append("package.json: devEngines.runtime must pin the managed Node")
    else:
        if runtime.get("name") != "node" or runtime.get("onFail") != "download":
            failures.append("package.json: devEngines.runtime must download the pinned Node")
        if node_version and runtime.get("version") != node_version:
            failures.append("Node version differs between .node-version and devEngines.runtime")

    package_manager = package.get("packageManager")
    if not isinstance(package_manager, str) or not package_manager.startswith("pnpm@"):
        failures.append("package.json: packageManager must pin pnpm exactly")
        pnpm_version = ""
    else:
        pnpm_version = package_manager.removeprefix("pnpm@")
    if pnpm_version and engines.get("pnpm") != pnpm_version:
        failures.append("pnpm version differs between packageManager and engines")

    ci_actions = _pinned_actions(workflow, ".github/workflows/ci.yml", failures)
    release_actions = _pinned_actions(release_workflow, ".github/workflows/release.yml", failures)
    if "astral-sh/setup-uv" not in ci_actions:
        failures.append("CI workflow: setup-uv action is missing")
    if uv_version and f'version: "{uv_version}"' not in workflow:
        failures.append("uv version differs between CI and API container")
    if "node-version-file: .node-version" not in workflow:
        failures.append("CI workflow: Node must come from .node-version")

    # The PostgreSQL-gated suites skip silently without OAK_TEST_DATABASE_URL, so a gate
    # that stops setting it, or skips the migration, would go green on nothing (RR-019).
    # CI's gate and the release gate both run them, on the very image compose.yaml pins.
    compose_postgres = re.search(r"^    image: (postgres:\S+)$", compose, flags=re.MULTILINE)
    compose_image = compose_postgres.group(1) if compose_postgres is not None else None
    _check_database_suites(workflow, "CI workflow", compose_image, failures)
    _check_database_suites(release_workflow, "release workflow", compose_image, failures)
    # The real-daemon runner journeys skip unless their stand-in image is cached, so the
    # release gate fetches the image CI's does.
    ci_pull = re.search(r"^ +(?:- )?run: (docker pull \S+)$", workflow, flags=re.MULTILINE)
    if ci_pull is not None and ci_pull.group(1) not in release_workflow:
        failures.append("release workflow: the gate must fetch the image CI's runner journeys use")

    _check_platform_jobs(workflow, compose_image, failures)

    # Reproducible images (RR-006): one dated Debian snapshot in both Dockerfiles and the
    # source date in the API one, one pinned BuildKit wherever a workflow builds the
    # images, each build proven twice, and the release scan folding the proof into its
    # provenance.
    snapshots = {}
    for label, text in (("api", api_dockerfile), ("web", web_dockerfile)):
        match = re.search(r"^ARG DEBIAN_SNAPSHOT=(\d{8}T\d{6}Z)$", text, flags=re.MULTILINE)
        if match is None:
            failures.append(
                f"deploy/images/{label}.Dockerfile: expected ARG DEBIAN_SNAPSHOT=<YYYYMMDDTHHMMSSZ>"
            )
        else:
            snapshots[label] = match.group(1)
    if len(set(snapshots.values())) > 1:
        failures.append("deploy/images: both Dockerfiles must name one DEBIAN_SNAPSHOT date")
    if not re.search(r"^ARG SOURCE_DATE_EPOCH$", api_dockerfile, flags=re.MULTILINE):
        failures.append("deploy/images/api.Dockerfile: expected ARG SOURCE_DATE_EPOCH")
    release_pin = _check_image_reproduction(
        release_workflow, "release workflow", "images", "linux/amd64", failures
    )
    ci_pin = _check_image_reproduction(
        workflow, "CI workflow", "check-linux-arm64", "linux/arm64", failures
    )
    if release_pin is not None and ci_pin is not None and release_pin != ci_pin:
        failures.append("the CI and release workflows must pin one BuildKit")
    scan = next(
        (
            run
            for run in _runs(_jobs(release_workflow).get("images") or {})
            if "scan_images.py" in run
        ),
        "",
    )
    if "--reproducibility image-evidence/image-reproducibility.json" not in scan:
        failures.append(
            "release workflow: the images job must hand the scan its reproducibility record"
        )
    _check_platform(
        _jobs(release_workflow),
        "artifacts",
        "ubuntu-latest",
        "linux-x86_64",
        "release workflow",
        failures,
    )
    _check_counted_skips(
        _jobs(release_workflow), "artifacts", "check-linux-x86_64", "release workflow", failures
    )
    _check_browser_suite(workflow, "CI workflow", failures)
    _check_browser_suite(
        release_workflow, "release workflow", failures, gated=("artifacts", "images")
    )
    for text, label in ((workflow, "CI workflow"), (release_workflow, "release workflow")):
        _check_workflow_settings(text, label, failures)
        _check_required_runs(text, label, failures)

    # The release builder must be the pinned builder. A release produced by a different
    # uv than the one CI and the container use is not the artifact anyone reviewed.
    if "astral-sh/setup-uv" not in release_actions:
        failures.append("release workflow: setup-uv action is missing")
    if uv_version and f'version: "{uv_version}"' not in release_workflow:
        failures.append("uv version differs between the release workflow and API container")
    if "node-version-file: .node-version" not in release_workflow:
        failures.append("release workflow: Node must come from .node-version")

    if uv_version:
        uv_parts = uv_version.split(".")
        compatible_series = ".".join(uv_parts[:2]) + ".x"
        documentation_fragments = (
            ("README.md", readme),
            ("docs/development.md", development),
        )
        for name, text in documentation_fragments:
            if f"`uv` {compatible_series}" not in text:
                failures.append(f"{name}: local uv compatibility series is stale")
            if f"{uv_version}" not in text:
                failures.append(f"{name}: exact CI/container uv builder is stale")

    _check_release_version(root, failures)

    for name, text, version, fragment in (
        ("README.md", readme, python_version, f"Python {python_version}"),
        ("README.md", readme, node_version, f"Node.js {node_version}"),
        ("README.md", readme, pnpm_version, f"`pnpm` {pnpm_version}"),
        ("docs/development.md", development, python_version, f"Python {python_version}"),
        ("docs/development.md", development, node_version, f"Node.js {node_version}"),
        ("docs/development.md", development, pnpm_version, f"`pnpm` {pnpm_version}"),
    ):
        if version and fragment not in text:
            failures.append(f"{name}: documented {fragment.split()[0]} version is stale")

    return failures


def runtime_failures(
    root: Path = ROOT,
    *,
    run: Callable[[tuple[str, ...]], str] | None = None,
) -> list[str]:
    """Compare the pinned toolchain against the binaries actually running.

    `check()` compares declarations against each other and never executes anything,
    so a host whose interpreters drift from the pins passes every declaration check:
    the `0.7.0` web artifacts were built on Node 22.17.1 against a 24.18.0 pin with
    every gate green (`RR-034`). This is the runtime half: the Python executing this
    process and the Node that pnpm actually provides must equal the pins exactly, and
    an inability to ask pnpm is itself a failure, never a pass. It is a separate
    function so the declaration checks stay runnable on scratch trees without pnpm.
    """

    failures: list[str] = []
    pinned_python = _read(root, ".python-version", failures).strip()
    pinned_node = _read(root, ".node-version", failures).strip()

    running_python = platform.python_version()
    if pinned_python and running_python != pinned_python:
        failures.append(
            f"runtime: Python {running_python} does not match .python-version {pinned_python}"
        )

    if pinned_node:
        executor = run if run is not None else _pnpm_runner(root)
        try:
            reported = executor(("pnpm", "exec", "node", "--version")).strip()
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(f"runtime: pnpm could not report its Node version: {error}")
        else:
            if reported != f"v{pinned_node}":
                failures.append(
                    f"runtime: pnpm-provisioned Node {reported} does not match "
                    f".node-version {pinned_node}"
                )
    return failures


def _pnpm_runner(root: Path) -> Callable[[tuple[str, ...]], str]:
    def execute(argv: tuple[str, ...]) -> str:
        completed = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        return completed.stdout

    return execute


def main() -> int:
    failures = check() + runtime_failures()
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
