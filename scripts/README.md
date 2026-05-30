# `scripts`

| Script | Purpose | Needs Docker? |
|---|---|---|
| `validate_slice0.py` | Static validation of all Slice 0 skeleton artifacts (files, pinned images, compose structure, health-check wiring, railway configs, env-secret hygiene). | No |
| `smoke-test.py` | Hits the live health/skeleton endpoints in order. Future-slice checks are listed as SKIPPED. | No (needs a running gateway/api) |

## Run

```bash
# Static artifact validation (works in any environment)
python scripts/validate_slice0.py

# Smoke test against a running stack (local Docker Compose default :8080)
python scripts/smoke-test.py http://localhost:8080

# ...or against the deployed public web URL
python scripts/smoke-test.py https://<web-public-domain>
```

`smoke-test.py` uses only the Python standard library. `validate_slice0.py`
requires `pyyaml`.
