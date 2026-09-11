from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import current_user, login_user, logout_user, redirect_if_anonymous, require_user, verify_credentials
from app.config import Settings, get_settings
from app.prism_client import PrismClient, PrismClientError
from app.schemas import ConsoleURL, EnvironmentInfo, TaskReference, VMCreateRequest, VMDetail, VMSummary

PrismFactory = Callable[[Settings], Any]

templates = Jinja2Templates(directory="app/templates")


def default_prism_client_factory(settings: Settings) -> PrismClient:
    return PrismClient(settings)


async def _call_client(settings: Settings, factory: PrismFactory, method_name: str, *args: Any) -> Any:
    client = factory(settings)
    if hasattr(client, "__aenter__"):
        async with client as opened:
            method = getattr(opened, method_name)
            return await method(*args)
    method = getattr(client, method_name)
    return await method(*args)


def create_app(settings: Settings | None = None, prism_client_factory: PrismFactory | None = None) -> FastAPI:
    settings = settings or get_settings()
    prism_client_factory = prism_client_factory or default_prism_client_factory

    app = FastAPI(title="Prism Central Management Demo")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax", https_only=False)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.state.settings = settings
    app.state.prism_client_factory = prism_client_factory

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        redirect = redirect_if_anonymous(request)
        if redirect:
            return redirect

        environments = []
        for key, env in settings.environments.items():
            panel: dict[str, Any] = {
                "info": EnvironmentInfo(key=key, label=env.label, base_url=str(env.base_url)),
                "vms": [],
                "error": None,
            }
            try:
                panel["vms"] = await _call_client(settings, prism_client_factory, "list_vms", key)
            except Exception as exc:  # keep each environment independent for dashboard demos
                panel["error"] = str(exc)
            environments.append(panel)

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"user": current_user(request), "environments": environments},
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        if current_user(request):
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login", response_class=HTMLResponse)
    async def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ) -> HTMLResponse:
        if verify_credentials(username, password, settings):
            login_user(request, username)
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    @app.post("/logout")
    async def logout(request: Request) -> RedirectResponse:
        logout_user(request)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/api/environments/{environment}/vms", response_model=list[VMSummary])
    async def list_vms(environment: str, _user: str = Depends(require_user)) -> list[VMSummary]:
        return await _call_client(settings, prism_client_factory, "list_vms", environment)

    @app.post("/api/environments/{environment}/vms", response_model=TaskReference)
    async def create_vm_json(
        environment: str,
        vm_request: VMCreateRequest,
        _user: str = Depends(require_user),
    ) -> TaskReference:
        try:
            return await _call_client(settings, prism_client_factory, "create_vm", environment, vm_request)
        except PrismClientError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.post("/environments/{environment}/vms")
    async def create_vm_form(
        request: Request,
        environment: str,
        name: str = Form(...),
        cluster_uuid: str = Form(...),
        network_uuid: str = Form(...),
        image_uuid: str = Form(""),
        description: str = Form("Created by Prism FastAPI demo"),
        vcpus: int = Form(2),
        cores_per_vcpu: int = Form(1),
        memory_mib: int = Form(4096),
        disk_size_mib: int = Form(51200),
    ) -> RedirectResponse:
        require_user(request)
        vm_request = VMCreateRequest(
            name=name,
            description=description,
            cluster_uuid=cluster_uuid,
            network_uuid=network_uuid,
            image_uuid=image_uuid or None,
            vcpus=vcpus,
            cores_per_vcpu=cores_per_vcpu,
            memory_mib=memory_mib,
            disk_size_mib=disk_size_mib,
        )
        await _call_client(settings, prism_client_factory, "create_vm", environment, vm_request)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/environments/{environment}/vms/{vm_uuid}", response_class=HTMLResponse)
    async def vm_detail(request: Request, environment: str, vm_uuid: str) -> HTMLResponse:
        redirect = redirect_if_anonymous(request)
        if redirect:
            return redirect
        vm: VMDetail = await _call_client(settings, prism_client_factory, "get_vm", environment, vm_uuid)
        return templates.TemplateResponse(request, "vm_detail.html", {"vm": vm})

    @app.get("/environments/{environment}/vms/{vm_uuid}/console", response_class=HTMLResponse)
    async def vm_console(request: Request, environment: str, vm_uuid: str) -> HTMLResponse:
        redirect = redirect_if_anonymous(request)
        if redirect:
            return redirect
        console: ConsoleURL = await _call_client(settings, prism_client_factory, "get_console_url", environment, vm_uuid)
        return templates.TemplateResponse(request, "console.html", {"console": console, "environment": environment})

    return app


app = create_app()
