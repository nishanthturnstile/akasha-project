import os
import shlex
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AKASHA_IMAGES = (
    "akasha-web",
    "akasha-api",
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


def _run_bash_step(script: str, values: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    exported = "\n".join(
        f"export {name}={shlex.quote(value)}" for name, value in values.items()
    )
    payload = f"set -euo pipefail\n{exported}\n{script}"
    return subprocess.run(
        ["bash"],
        check=False,
        capture_output=True,
        input=payload.encode(),
        env={**os.environ, **values},
    )


def test_staging_deploy_verifies_all_images_before_coolify_patch():
    workflow = _workflow("deploy-staging.yml")
    validate_job = workflow["jobs"]["validate-web-basemap-config"]
    build_job = workflow["jobs"]["build-images"]
    deploy_job = workflow["jobs"]["deploy-staging"]
    step_names = _step_names(deploy_job)
    verify_step = _step(deploy_job, "Verify immutable image tags exist")

    assert build_job["needs"] == "validate-web-basemap-config"
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

    validate_step = _step(validate_job, "Validate hosted basemap build settings")
    validate_names = _step_names(validate_job)
    build_names = _step_names(build_job)
    assert validate_job["env"]["VITE_ESRI_API_KEY"] == "${{ vars.VITE_ESRI_API_KEY || '' }}"
    assert validate_job["env"]["ESRI_BASEMAP_USAGE_MODEL"] == (
        "${{ vars.ESRI_BASEMAP_USAGE_MODEL || 'session' }}"
    )
    assert build_job["env"]["VITE_ESRI_API_KEY"] == "${{ vars.VITE_ESRI_API_KEY || '' }}"
    assert validate_names.index("Mask Esri public key") < validate_names.index(
        "Validate hosted basemap build settings"
    )
    assert build_names.index("Mask Esri public key") < build_names.index("Build and push image")
    assert "::add-mask::$VITE_ESRI_API_KEY" in _step(
        validate_job, "Mask Esri public key"
    )["run"]
    assert "::add-mask::$VITE_ESRI_API_KEY" in _step(build_job, "Mask Esri public key")["run"]
    web_matrix_args = next(
        item["build_args"]
        for item in build_job["strategy"]["matrix"]["include"]
        if item["image"] == "akasha-web"
    )
    assert "${{ env." not in web_matrix_args
    build_step = _step(build_job, "Build and push image")
    assert "VITE_ESRI_PUBLIC_ACCESS=${{ matrix.image == 'akasha-web' && env.VITE_ESRI_API_KEY || '' }}" in build_step["with"]["build-args"]
    assert "CHANGE_ME" in validate_step["run"]
    assert "VITE_ESRI_API_KEY must be configured" in validate_step["run"]
    assert "echo \"$VITE_ESRI_API_KEY\"" not in validate_step["run"]


def test_staging_basemap_preflight_rejects_missing_and_placeholder_keys():
    workflow = _workflow("deploy-staging.yml")
    validate_step = _step(
        workflow["jobs"]["validate-web-basemap-config"],
        "Validate hosted basemap build settings",
    )
    base = {
        "VITE_BASEMAP_PROVIDER": "esri",
        "VITE_ESRI_API_KEY": "test-public-key",
        "VITE_ESRI_BASEMAP_STYLE": "arcgis/imagery",
        "VITE_ESRI_BASEMAP_STYLE_FAMILY": "arcgis",
        "ESRI_BASEMAP_USAGE_MODEL": "session",
    }

    for invalid_key in ("", "   ", "CHANGE_ME_KEY", "<public-key>"):
        rejected = _run_bash_step(
            validate_step["run"],
            {**base, "VITE_ESRI_API_KEY": invalid_key},
        )
        assert rejected.returncode != 0
        assert "must be configured" in rejected.stdout.decode()

    approved = _run_bash_step(validate_step["run"], base)
    assert approved.returncode == 0, approved.stderr.decode()
    tile = _run_bash_step(
        validate_step["run"],
        {**base, "ESRI_BASEMAP_USAGE_MODEL": "tile"},
    )
    assert tile.returncode == 0, tile.stderr.decode()
    rejected_model = _run_bash_step(
        validate_step["run"],
        {**base, "ESRI_BASEMAP_USAGE_MODEL": "per-request"},
    )
    assert rejected_model.returncode != 0


def test_production_deploy_verifies_all_images_before_coolify_patch():
    workflow = _workflow("deploy-production.yml")
    deploy_job = workflow["jobs"]["deploy-production"]
    step_names = _step_names(deploy_job)
    validate_step = _step(deploy_job, "Validate production deployment configuration")
    verify_step = _step(deploy_job, "Verify immutable image tags exist")

    assert deploy_job["env"]["IMAGE_TAG"] == "${{ inputs.image_tag }}"
    assert deploy_job["env"]["ESRI_WEB_IMAGE_APPROVED_SHA"] == (
        "${{ vars.ESRI_WEB_IMAGE_APPROVED_SHA }}"
    )
    assert deploy_job["env"]["ESRI_WEB_IMAGE_CREDENTIAL_ID"] == (
        "${{ vars.ESRI_WEB_IMAGE_CREDENTIAL_ID }}"
    )
    assert "Log in to GHCR for image verification" in step_names
    assert step_names.index("Verify immutable image tags exist") < step_names.index(
        "Patch Coolify service stack"
    )
    assert "full 40-character lowercase Git SHA" in validate_step["run"]
    assert "ESRI_WEB_IMAGE_CREDENTIAL_ID is required" in validate_step["run"]
    assert '"$ESRI_WEB_IMAGE_APPROVED_SHA" != "$IMAGE_TAG"' in validate_step["run"]
    assert step_names.index("Validate production deployment configuration") < step_names.index(
        "Verify immutable image tags exist"
    )
    assert "docker manifest inspect" in verify_step["run"]
    for image in AKASHA_IMAGES:
        assert image in verify_step["run"]


def test_production_deploy_rejects_unapproved_esri_web_image_sha():
    workflow = _workflow("deploy-production.yml")
    validate_step = _step(
        workflow["jobs"]["deploy-production"],
        "Validate production deployment configuration",
    )
    expected_sha = "a" * 40
    env = {
        "COOLIFY_API_URL": "https://coolify.example.test/api/v1",
        "COOLIFY_TOKEN": "test-token",
        "COOLIFY_SERVICE_UUID": "test-service",
        "IMAGE_TAG": expected_sha,
        "ESRI_WEB_IMAGE_APPROVED_SHA": "b" * 40,
        "ESRI_WEB_IMAGE_CREDENTIAL_ID": "credential-item-id",
    }

    rejected = _run_bash_step(validate_step["run"], env)
    assert rejected.returncode != 0
    assert "not approved for the production Esri referrer" in rejected.stdout.decode()

    env["ESRI_WEB_IMAGE_APPROVED_SHA"] = expected_sha
    approved = _run_bash_step(validate_step["run"], env)
    assert approved.returncode == 0, approved.stderr.decode()

    for name, invalid in (
        ("IMAGE_TAG", "abcd"),
        ("IMAGE_TAG", "g" * 40),
        ("ESRI_WEB_IMAGE_APPROVED_SHA", "abcd"),
        ("ESRI_WEB_IMAGE_CREDENTIAL_ID", "   "),
    ):
        rejected = _run_bash_step(validate_step["run"], {**env, name: invalid})
        assert rejected.returncode != 0, f"{name}={invalid!r} was accepted"


def test_staging_deploy_explicitly_triggers_and_verifies_runtime_revision():
    workflow = _workflow("deploy-staging.yml")
    deploy_job = workflow["jobs"]["deploy-staging"]
    step_names = _step_names(deploy_job)
    patch_step = _step(deploy_job, "Patch Coolify service stack")
    verify_step = _step(deploy_job, "Verify deployed image revisions")

    assert '"instant_deploy": True' in patch_step["run"]
    assert "/deploy?" in patch_step["run"]
    assert 'method="POST"' in patch_step["run"]
    assert step_names.index("Patch Coolify service stack") < step_names.index(
        "Verify deployed image revisions"
    )
    assert 'os.environ["IMAGE_TAG"]' in verify_step["run"]
    assert "org.opencontainers.image.revision" in verify_step["run"]
    assert 'values["health"] == "healthy"' in verify_step["run"]


def test_staging_deploy_renders_source_scoped_resourcesat_cutover():
    workflow = _workflow("deploy-staging.yml")
    deploy_job = workflow["jobs"]["deploy-staging"]
    render_step = _step(deploy_job, "Render Compose with immutable image tag")

    assert deploy_job["env"]["INGESTION_RESOURCESAT_CUTOVER_ENABLED"] == (
        "${{ vars.INGESTION_RESOURCESAT_CUTOVER_ENABLED || 'false' }}"
    )
    assert deploy_job["env"]["INGESTION_RESOURCESAT_CUTOVER_SOURCE_IDS"] == (
        "${{ vars.INGESTION_RESOURCESAT_CUTOVER_SOURCE_IDS || "
        "'resourcesat-2a-liss3-boa' }}"
    )
    assert "INGESTION_RESOURCESAT_CUTOVER_ENABLED must be true or false" in render_step["run"]
    assert "INGESTION_RESOURCESAT_CUTOVER_SOURCE_IDS is invalid" in render_step["run"]
    assert deploy_job["env"]["ESRI_BASEMAP_USAGE_MODEL"] == (
        "${{ vars.ESRI_BASEMAP_USAGE_MODEL || 'session' }}"
    )
    assert "ESRI_BASEMAP_USAGE_MODEL must be session or tile" in render_step["run"]
    assert '${ESRI_BASEMAP_USAGE_MODEL:-session}' in render_step["run"]


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
    """The app-only deploy template must keep provider triggers disabled."""
    env = _text("infra/selfhosted/env.example")
    compose = _text("infra/selfhosted/coolify-compose.yml")

    assert "INGESTION_JOB_INBOX_DIR=/srv/akasha/ingestion-inbox" not in env
    assert "/srv/akasha/ingestion-inbox" not in compose
    assert "ADMIN_INGESTION_LIVE_TRIGGER_ENABLED=false" in env
    assert "ADMIN_INGESTION_LIVE_TRIGGER_ENABLED" in compose
    assert 'ADMIN_INGESTION_LIVE_TRIGGER_ENABLED: "false"' in compose


def test_selfhosted_compose_forwards_validated_basemap_runtime_without_public_key():
    env = _text("infra/selfhosted/env.example")
    compose = _text("infra/selfhosted/coolify-compose.yml")

    for name, default in (
        ("BASEMAP_PROVIDER", "esri"),
        ("ESRI_BASEMAP_STYLE", "arcgis/imagery"),
        ("ESRI_BASEMAP_STYLE_FAMILY", "arcgis"),
        ("ESRI_BASEMAP_USAGE_MODEL", "session"),
        ("ESRI_BASEMAP_PLACES", "none"),
        ("ESRI_BASEMAP_SESSION_SECONDS", "43200"),
    ):
        assert f'{name}: "${{{name}:-{default}}}"' in compose
        assert f"{name}={default}" in env

    api_block = compose.split("  api:", 1)[1].split("  titiler:", 1)[0]
    assert "VITE_ESRI_API_KEY" not in api_block
    assert "VITE_ESRI_PUBLIC_ACCESS" not in api_block


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
