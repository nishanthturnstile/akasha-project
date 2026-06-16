from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AKASHA_IMAGES = (
    "akasha-web",
    "akasha-api",
    "akasha-ingestion-worker",
    "akasha-ingestion-sar",
)


def _workflow(name: str) -> dict:
    return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text())


def _step_names(job: dict) -> list[str]:
    return [step.get("name", "") for step in job["steps"]]


def _step(job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def test_staging_deploy_verifies_all_images_before_coolify_patch():
    workflow = _workflow("deploy-staging.yml")
    build_job = workflow["jobs"]["build-images"]
    deploy_job = workflow["jobs"]["deploy-staging"]
    step_names = _step_names(deploy_job)
    verify_step = _step(deploy_job, "Verify immutable image tags exist")

    assert deploy_job["needs"] == "build-images"
    assert deploy_job["env"]["IMAGE_TAG"] == "${{ github.sha }}"
    assert "Log in to GHCR for image verification" in step_names
    assert step_names.index("Verify immutable image tags exist") < step_names.index(
        "Patch Coolify service stack"
    )
    assert "docker manifest inspect" in verify_step["run"]
    for image in AKASHA_IMAGES:
        assert image in verify_step["run"]
        assert any(item["image"] == image for item in build_job["strategy"]["matrix"]["include"])


def test_production_deploy_verifies_all_images_before_coolify_patch():
    workflow = _workflow("deploy-production.yml")
    deploy_job = workflow["jobs"]["deploy-production"]
    step_names = _step_names(deploy_job)
    validate_step = _step(deploy_job, "Validate production deployment configuration")
    verify_step = _step(deploy_job, "Verify immutable image tags exist")

    assert deploy_job["env"]["IMAGE_TAG"] == "${{ inputs.image_tag }}"
    assert "Log in to GHCR for image verification" in step_names
    assert step_names.index("Verify immutable image tags exist") < step_names.index(
        "Patch Coolify service stack"
    )
    assert "Mutable image tags are not allowed for production." in validate_step["run"]
    assert "docker manifest inspect" in verify_step["run"]
    for image in AKASHA_IMAGES:
        assert image in verify_step["run"]
