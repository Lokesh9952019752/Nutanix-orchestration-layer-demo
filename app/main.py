from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.auth import clear_session, issue_session, require_user, verify_credentials
from app.config import EnvironmentKey, PrismEnvironmentSettings, Settings, get_settings
from app.prism_client import PrismClient, PrismClientError
from app.schemas import EnvironmentIdentity, PrismErrorDisplay, VMCreateRequest

PrismClientFactory = Callable[[PrismEnvironmentSettings], PrismClient]

templates = Jinja2Templates(directory="app/templates")


def create_app(settings: Settings | None = None, prism_client_factory: PrismClientFactory | None = None) -> FastAPI:
    app = FastAPI(title="Prism FastAPI Demo")
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.state.settings = settings or get_settings()
    app.state.prism_client_factory = prism_client_factory or (lambda environment: PrismClient(environment))

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        if _current_user(request):
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)  # type: ignore[return-value]
        return _render(request, "login.html", {"error": None})

    @app.post("/login")
    async def login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
        settings = _settings(request)
        if not verify_credentials(username, password, settings):
            return _render(
                request,
                "login.html",
                {"error": "Invalid username or password."},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        issue_session(response, username, settings)
        return response

    @app.post("/logout")
    async def logout(request: Request) -> RedirectResponse:
        response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        clear_session(response, _settings(request))
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, user: str = Depends(_require_user)) -> HTMLResponse:
        panels = []
        for environment in _settings(request).configured_environments():
            try:
                vms = await _client(request, environment).list_vms()
                panels.append({"environment": _identity(environment), "vms": vms, "error": None})
            except PrismClientError as exc:
                panels.append({"environment": _identity(environment), "vms": [], "error": _error(exc)})
        return _render(request, "dashboard.html", {"user": user, "panels": panels})

    @app.get("/status")
    async def status_api(request: Request, user: str = Depends(_require_user)) -> dict[str, Any]:
        del user
        statuses = {}
        for environment in _settings(request).configured_environments():
            try:
                statuses[environment.key] = {"ok": True, "vm_count": len(await _client(request, environment).list_vms())}
            except PrismClientError as exc:
                statuses[environment.key] = {"ok": False, "message": str(exc), "status_code": exc.status_code}
        return {"environments": statuses}

    @app.get("/environments/{environment_key}/vms/{vm_uuid}", response_class=HTMLResponse)
    async def vm_detail(
        request: Request, environment_key: EnvironmentKey, vm_uuid: str, user: str = Depends(_require_user)
    ) -> HTMLResponse:
        del user
        environment = _environment(request, environment_key)
        try:
            vm = await _client(request, environment).get_vm(vm_uuid)
            return _render(
                request, "vm_detail.html", {"environment": _identity(environment), "vm": vm, "error": None}
            )
        except PrismClientError as exc:
            return _render(
                request,
                "vm_detail.html",
                {"environment": _identity(environment), "vm": None, "error": _error(exc)},
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

    @app.post("/environments/{environment_key}/vms")
    async def create_vm(
        request: Request,
        environment_key: EnvironmentKey,
        name: str = Form(...),
        cpu_count: int = Form(...),
        cores_per_socket: int = Form(...),
        memory_gib: float = Form(...),
        disk_gib: float = Form(...),
        image_uuid: str = Form(...),
        subnet_uuid: str = Form(...),
        cluster_uuid: str = Form(...),
        description: str = Form(""),
        address_mode: str = Form("dhcp"),
        static_ip: str = Form(""),
        user: str = Depends(_require_user),
    ) -> Response:
        del user
        environment = _environment(request, environment_key)
        try:
            create_request = VMCreateRequest(
                name=name,
                cpu_count=cpu_count,
                cores_per_socket=cores_per_socket,
                memory_gib=memory_gib,
                disk_gib=disk_gib,
                image_uuid=image_uuid,
                subnet_uuid=subnet_uuid,
                cluster_uuid=cluster_uuid,
                description=description,
                address_mode=address_mode,
                static_ip=static_ip,
            )
            vm_uuid = await _client(request, environment).create_vm(create_request)
        except ValidationError as exc:
            panels = [{"environment": _identity(environment), "vms": [], "error": PrismErrorDisplay(environment_key=environment.key, environment_label=environment.label, message=str(exc))}]
            return _render(request, "dashboard.html", {"user": "", "panels": panels}, status_code=400)
        except PrismClientError as exc:
            panels = [{"environment": _identity(environment), "vms": [], "error": _error(exc)}]
            return _render(request, "dashboard.html", {"user": "", "panels": panels}, status_code=502)
        return RedirectResponse(f"/environments/{environment.key}/vms/{vm_uuid}", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/environments/{environment_key}/vms/{vm_uuid}/console", response_class=HTMLResponse)
    async def vm_console(
        request: Request, environment_key: EnvironmentKey, vm_uuid: str, user: str = Depends(_require_user)
    ) -> HTMLResponse:
        del user
        environment = _environment(request, environment_key)
        try:
            console = await _client(request, environment).get_console(vm_uuid)
            return _render(
                request,
                "console.html",
                {"environment": _identity(environment), "console": console, "error": None},
            )
        except PrismClientError as exc:
            return _render(
                request,
                "console.html",
                {"environment": _identity(environment), "console": None, "error": _error(exc)},
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

    return app


def _render(request: Request, template_name: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, template_name, context, status_code=status_code)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _client(request: Request, environment: PrismEnvironmentSettings) -> PrismClient:
    return request.app.state.prism_client_factory(environment)


def _environment(request: Request, key: str) -> PrismEnvironmentSettings:
    try:
        return _settings(request).environment_by_key(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _identity(environment: PrismEnvironmentSettings) -> EnvironmentIdentity:
    return EnvironmentIdentity(key=environment.key, label=environment.label, base_url=environment.base_url)


def _error(exc: PrismClientError) -> PrismErrorDisplay:
    return PrismErrorDisplay(
        environment_key=exc.environment.key,
        environment_label=exc.environment.label,
        message=str(exc),
        status_code=exc.status_code,
    )


def _current_user(request: Request) -> str | None:
    try:
        return require_user(request, _settings(request))
    except HTTPException:
        return None


def _require_user(request: Request) -> str:
    return require_user(request, _settings(request))


app = create_app()
