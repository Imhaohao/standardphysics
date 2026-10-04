"""The image that reaches GHCR is the image CI built once, tested and scanned.

The image job builds, smoke-tests and runs the Blender regressions against one
image, then hands on its identity: the candidate digest it pushed on master, or
an archive of the same image elsewhere. The vulnerability scan reads that
identity instead of building its own copy, and publish retags the candidate
digest instead of building again, so the bytes released are the bytes checked.

Everything the build pulls in is pinned too: base images by digest, pip at a
named version, and each downloaded tool against a sha256 sum, which the
pinned-download action checks on every run, cached or not.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_DOWNLOAD = "./.github/actions/pinned-download"
BUILD_STEP = re.compile(r"docker/build-push-action|docker (buildx )?build\b")
UNBOUNDED_PIP_UPGRADE = re.compile(r"pip install[^\n]*--upgrade pip(?!=)")
ENV_REFERENCE = re.compile(r"\$\{\{ env\.(\w+) \}\}")


def _workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _jobs() -> dict[str, Any]:
    return _workflow("ci.yml")["jobs"]


def _step_text(step: dict[str, Any]) -> str:
    return f"{step.get('uses', '')}\n{step.get('run', '')}\n{step.get('if', '')}"


def _job_text(job: dict[str, Any]) -> str:
    return "\n".join(_step_text(step) for step in job["steps"])


def test_only_the_image_job_builds_the_image():
    builders = [name for name, job in _jobs().items() if BUILD_STEP.search(_job_text(job))]
    assert builders == ["image"]


def test_the_image_job_hands_on_the_digest_and_id_it_tested():
    outputs = _jobs()["image"]["outputs"]
    assert "steps." in outputs["candidate"]
    assert "steps." in outputs["image-id"]


UNRELEASED_JOBS = {"publish", "reels"}


def test_publish_waits_for_every_job_behind_the_image():
    jobs = _jobs()
    assert set(jobs["publish"]["needs"]) == set(jobs) - UNRELEASED_JOBS


def test_the_reels_app_is_linted_and_typechecked():
    reels = _jobs()["reels"]
    runs = [step.get("run", "") for step in reels["steps"]]
    assert reels["defaults"]["run"]["working-directory"] == "apps/reels"
    assert runs[-3:] == ["npm ci", "npm run lint", "npm run typecheck"]


def test_publish_retags_the_candidate_digest_the_image_job_pushed():
    publish = _jobs()["publish"]
    step_env = {key: value for step in publish["steps"] for key, value in step.get("env", {}).items()}
    assert "needs.image.outputs.candidate" in step_env["CANDIDATE"]
    assert '"$CANDIDATE"' in _job_text(publish)
    assert "candidate-$GITHUB_SHA" not in _job_text(publish)


def test_the_vulnerability_scan_reads_the_tested_image():
    scan = _jobs()["image-vulnerabilities"]
    text = f"{_job_text(scan)}\n{scan['env']}"
    assert scan["name"] == "Critical vulnerabilities with a fix in the image"
    assert scan["needs"] == "image" or scan["needs"] == ["image"]
    assert "needs.image.outputs.candidate" in text
    assert "needs.image.outputs.image-id" in text
    assert 'registry:$CANDIDATE' in text
    assert text.count("--only-fixed --fail-on critical") == 2


def _global_build_args(dockerfile: str) -> dict[str, str]:
    before_first_stage = dockerfile.split("\nFROM ", 1)[0]
    return dict(re.findall(r"^ARG (\w+)=(\S+)", before_first_stage, re.MULTILINE))


def test_every_dockerfile_base_is_pinned_by_digest():
    dockerfile = (ROOT / "Dockerfile").read_text()
    build_args = _global_build_args(dockerfile)
    stages = re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE)
    bases = [re.sub(r"\$\{(\w+)\}", lambda arg: build_args.get(arg[1], ""), image) for image in stages]
    unpinned = [image for image in bases if "@sha256:" not in image]
    assert not unpinned


def test_pip_upgrades_name_a_version():
    sources = [ROOT / "Dockerfile", *WORKFLOWS.glob("*.yml")]
    unbounded = [path.name for path in sources if UNBOUNDED_PIP_UPGRADE.search(path.read_text())]
    assert not unbounded


def _workflow_jobs() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every job in every workflow, with the env its steps' inputs can read."""
    jobs = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        jobs += [({**workflow.get("env", {}), **job.get("env", {})}, job) for job in workflow["jobs"].values()]
    return jobs


def _pinned_downloads() -> list[tuple[dict[str, Any], list[dict[str, Any]], int]]:
    """Each use of the pinned-download action: its job's env, the job's steps and its place in them."""
    return [
        (env, job["steps"], index)
        for env, job in _workflow_jobs()
        for index, step in enumerate(job.get("steps", []))
        if step.get("uses") == PINNED_DOWNLOAD
    ]


def _resolved(value: str, env: dict[str, Any]) -> str:
    return ENV_REFERENCE.sub(lambda reference: str(env[reference[1]]), value)


def _asset_name(download: dict[str, Any]) -> str:
    return download["with"]["path"].rsplit("/", 1)[-1]


def _action_steps(name: str) -> list[dict[str, Any]]:
    action = yaml.safe_load((ROOT / ".github" / "actions" / name / "action.yml").read_text())
    return action["runs"]["steps"]


def _position(steps: list[dict[str, Any]], marker: str) -> int:
    return next(index for index, step in enumerate(steps) if marker in _step_text(step))


def test_release_assets_are_downloaded_only_through_the_pinned_download_action():
    direct = [
        step.get("name", step.get("run", ""))
        for _, job in _workflow_jobs()
        for step in job.get("steps", [])
        if "releases/download" in step.get("run", "")
    ]
    assert not direct


def test_the_scanners_and_xcodegen_are_pinned_by_sha256():
    digests = {
        _asset_name(steps[index]): _resolved(steps[index]["with"]["sha256"], env)
        for env, steps, index in _pinned_downloads()
    }
    assert set(digests) == {"gitleaks.tar.gz", "grype.tar.gz", "xcodegen.zip"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in digests.values())


def test_each_download_is_used_only_after_the_action_has_checked_it():
    for _, steps, index in _pinned_downloads():
        asset = _asset_name(steps[index])
        users = [position for position, step in enumerate(steps) if asset in step.get("run", "")]
        assert users and min(users) > index


def test_the_pinned_download_checks_the_digest_on_every_run_and_caches_only_a_match():
    steps = _action_steps("pinned-download")
    restore, fetch, check, save = (
        _position(steps, marker)
        for marker in ("actions/cache/restore@", "curl ", "shasum -a 256 --check --strict", "actions/cache/save@")
    )
    assert restore < fetch < check < save
    assert "if" not in steps[check]
    assert steps[fetch]["if"] == steps[save]["if"] == "steps.cache.outputs.cache-hit != 'true'"
    assert steps[restore]["with"]["key"] == steps[save]["with"]["key"] == "pinned-download-${{ inputs.sha256 }}"


def test_a_failed_download_retries_for_minutes_before_it_gives_up():
    steps = _action_steps("pinned-download")
    curl = steps[_position(steps, "curl ")]["run"]
    retries = int(re.search(r"--retry (\d+)", curl)[1])
    retry_window = int(re.search(r"--retry-max-time (\d+)", curl)[1])
    assert "--retry-all-errors" in curl
    # Without --retry-delay curl waits one second and doubles each wait, so n
    # retries wait 2**n - 1 seconds in all. Five fixed five-second waits gave
    # up after 25 seconds of 500s from GitHub's release download.
    assert "--retry-delay" not in curl
    assert min(2**retries - 1, retry_window) >= 120
