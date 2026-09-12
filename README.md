# Prism FastAPI Demo

A small server-rendered FastAPI demo for viewing and creating VMs across two Nutanix Prism Central environments: on-prem and NC2 AWS.

## Local setup

```bash
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Development login defaults to `admin` / `admin`. Override these for any production-like demo.

## Environment

Copy `.env.example` into your environment manager and set real values before connecting to Prism:

- `APP_ADMIN_USERNAME` and `APP_ADMIN_PASSWORD`
- `SESSION_SECRET` (must be non-default outside local development)
- `PRISM_ONPREM_URL`, `PRISM_ONPREM_USERNAME`, `PRISM_ONPREM_PASSWORD`
- `PRISM_NC2_AWS_URL`, `PRISM_NC2_AWS_USERNAME`, `PRISM_NC2_AWS_PASSWORD`
- `PRISM_VERIFY_SSL` (`true` by default)

The application keeps Prism API endpoint paths and payload mapping inside `app/prism_client.py`; routes and templates work with normalized app schemas.

## Checks

```bash
python -m pip install -e ".[dev]" && python -m compileall app tests
python -m pytest tests -q
```
