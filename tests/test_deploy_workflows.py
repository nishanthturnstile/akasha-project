from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AKASHA_IMAGES = (
    "akasha-web",
    "akasha-api",
    "akasha-ingestion-worker",
    "akasha-ingestion-sar",
)
DEPLOY_WORKFLOWS = ("deploy-staging.yml", "deploy-production.yml")


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def _workflow(name: str) -> dict:
    return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text())


def _step_names(job: dict) -> list[str]:
    return [step.get("name", "") for step in job["steps"]]


def _step(job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def _python_heredocs(run: str) -> list[str]:
    snippets: list[str] = []
    lines = run.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != "python3 - <<'PY'":
            index += 1
            continue
        index += 1
        snippet: list[str] = []
        while index < len(lines) and lines[index].strip() != "PY":
            snippet.append(lines[index])
            index += 1
        snippets.append("\n".join(snippet))
        index += 1
    return snippets


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


def test_staging_deploy_uses_service_patch_instant_deploy_without_generic_deploy_webhook():
    workflow = _workflow("deploy-staging.yml")
    deploy_job = workflow["jobs"]["deploy-staging"]
    step_names = _step_names(deploy_job)
    patch_step = _step(deploy_job, "Patch Coolify service stack")

    assert "Trigger Coolify deployment" not in step_names
    assert '"instant_deploy": True' in patch_step["run"]
    assert "/deploy?" not in patch_step["run"]


def test_deploy_workflow_inline_python_snippets_compile():
    for workflow_name in DEPLOY_WORKFLOWS:
        workflow = _workflow(workflow_name)
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                run = step.get("run", "")
                for snippet in _python_heredocs(run):
                    compile(snippet, f"{workflow_name}:{job_name}:{step.get('name', '')}", "exec")


def test_production_deploy_uses_service_patch_instant_deploy_without_generic_deploy_webhook():
    workflow = _workflow("deploy-production.yml")
    deploy_job = workflow["jobs"]["deploy-production"]
    step_names = _step_names(deploy_job)
    patch_step = _step(deploy_job, "Patch Coolify service stack")

    assert "Trigger Coolify deployment" not in step_names
    assert '"instant_deploy": True' in patch_step["run"]
    assert "/deploy?" not in patch_step["run"]


def test_selfhosted_env_documents_admin_ingestion_live_trigger_gate():
    """The deploy env template must include the manual live-sync gate used by the API."""
    env = _text("infra/selfhosted/env.example")
    compose = _text("infra/selfhosted/coolify-compose.yml")

    assert "INGESTION_JOB_INBOX_DIR=/srv/akasha/ingestion-inbox" in env
    assert "ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false" in env
    assert "ADMIN_INGESTION_LIVE_TRIGGER_ENABLED" in compose
    assert "${ADMIN_INGESTION_LIVE_TRIGGER_ENABLED:-false}" in compose


def test_ingestion_image_packages_eos04_prepare_script():
    """EOS-04 live validation requires the prepare script inside ingestion-worker."""
    dockerfile = _text("services/ingestion/Dockerfile")

    assert "prepare_eos04_sar_mrs_l2b_cogs.py" in dockerfile


def test_staging_validator_checks_internal_stac_and_titiler_services():
    """Post-deploy staging validation must include catalog and tile internals."""
    validator = _text("scripts/validate_selfhosted_staging_bhoonidhi.py")

    assert "for service in web api stac-api titiler" in validator
    assert "for service in web api stac-api titiler postgis minio" in validator
    assert "http://stac-api:8080/collections" in validator
    assert "http://titiler:8000/healthz" in validator
