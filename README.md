# Prism Central FastAPI Demo

A lightweight FastAPI demo for managing two Nutanix Prism Central portals from one server-rendered dashboard: an on-prem environment and an NC2 AWS environment. The app uses a narrow signed-session login boundary today so future Azure AD SSO can replace only the authentication entry point without changing VM orchestration.

## Local setup

```bash
python -m pip install -e ".[dev]"
cp .env.example .env
# edit .env or export the variables in your shell
uvicorn app.main:app --reload
```

The local demo defaults are `admin` / `admin`. Use real values for `APP_ADMIN_USERNAME`, `APP_ADMIN_PASSWORD`, and `SESSION_SECRET` outside disposable demos.

## Environment variables

All credentials and Prism Central portal settings are loaded from environment variables, not code:

- `APP_ADMIN_USERNAME`
- `APP_ADMIN_PASSWORD`
- `SESSION_SECRET`
- `PRISM_VERIFY_SSL` (`true` by default; set `false` only for lab portals with private certificates when acceptable)
- `PRISM_ONPREM_URL`
- `PRISM_ONPREM_USERNAME`
- `PRISM_ONPREM_PASSWORD`
- `PRISM_NC2_AWS_URL`
- `PRISM_NC2_AWS_USERNAME`
- `PRISM_NC2_AWS_PASSWORD`

See `.env.example` for safe placeholder values.

## Demo behavior

After login, the dashboard independently loads both configured Prism Central environments. If one portal is unavailable, its panel shows an error while the other portal remains visible. Each environment panel lists normalized VM summaries, links to detail pages, links to console pages, and includes a VM creation form.

The console page renders an iframe plus an external launch link. Some Prism deployments block iframe embedding or require a one-time console ticket, so the external link is the supported fallback.

## Prism API assumptions

`app/prism_client.py` isolates Prism Central API paths and payload mapping from routes and templates. The demo targets common Prism Central v3 VM endpoints:

- `POST /api/nutanix/v3/vms/list` for VM inventory
- `GET /api/nutanix/v3/vms/{uuid}` for VM details
- `POST /api/nutanix/v3/vms` for VM creation
- `POST /api/nutanix/v3/vms/{uuid}/console` for console launch information

VM creation maps the form fields into a v3-style VM spec with cluster, CPU, memory, disk, image, and subnet references. If a target Prism version differs, update the client layer and its tests without changing UI templates.

## Authentication extension point

`app/auth.py` intentionally contains only credential verification, session issue/clear helpers, and route guard helpers. A future Azure AD SSO flow can replace credential verification and session creation while leaving `app/main.py` dashboard and VM orchestration intact.

## Verification

```bash
python -m pip install -e ".[dev]" && python -m compileall app tests
python -m pytest tests -q
```
