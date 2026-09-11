from contextlib import AbstractAsyncContextManager
from typing import Any, Dict, Iterable, Optional
from urllib.parse import quote

import httpx

from app.config import PrismEnvironmentConfig, Settings
from app.schemas import ConsoleURL, TaskReference, VMCreateRequest, VMDetail, VMSummary


class PrismClientError(RuntimeError):
    """Raised when Prism Central returns an unusable response."""


class PrismClient(AbstractAsyncContextManager):
    """Small Prism Central v3 API wrapper that normalizes VM responses."""

    def __init__(self, settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.settings = settings
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "PrismClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.aclose()

    def _environment(self, environment: str) -> PrismEnvironmentConfig:
        try:
            return self.settings.environments[environment]
        except KeyError as exc:
            raise PrismClientError(f"Unknown Prism environment: {environment}") from exc

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                verify=self.settings.prism_verify_ssl,
                timeout=httpx.Timeout(20.0),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, environment: str, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        env = self._environment(environment)
        url = f"{str(env.base_url).rstrip('/')}{path}"
        response = await self._http().request(
            method,
            url,
            auth=(env.username, env.password),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            **kwargs,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PrismClientError(f"Prism {environment} request failed: {exc.response.status_code}") from exc
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise PrismClientError(f"Prism {environment} returned non-JSON data") from exc

    async def list_vms(self, environment: str) -> list[VMSummary]:
        body = {"kind": "vm", "length": 100, "offset": 0}
        data = await self._request(environment, "POST", "/api/nutanix/v3/vms/list", json=body)
        entities = data.get("entities", [])
        return [self._summary_from_entity(environment, entity) for entity in entities]

    async def get_vm(self, environment: str, vm_uuid: str) -> VMDetail:
        data = await self._request(environment, "GET", f"/api/nutanix/v3/vms/{quote(vm_uuid)}")
        return self._detail_from_entity(environment, data)

    async def create_vm(self, environment: str, request: VMCreateRequest) -> TaskReference:
        payload = self._build_create_payload(request)
        data = await self._request(environment, "POST", "/api/nutanix/v3/vms", json=payload)
        task_uuid = (
            data.get("status", {}).get("execution_context", {}).get("task_uuid")
            or data.get("task_uuid")
            or data.get("metadata", {}).get("uuid")
            or "unknown"
        )
        status = data.get("status", {}).get("state") or data.get("status") or "submitted"
        return TaskReference(uuid=task_uuid, status=str(status), message=data.get("message"))

    async def get_console_url(self, environment: str, vm_uuid: str) -> ConsoleURL:
        data = await self._request(environment, "POST", f"/api/nutanix/v3/vms/{quote(vm_uuid)}/console", json={})
        url = data.get("url") or data.get("console_url") or data.get("status", {}).get("console_url")
        ticket = data.get("ticket") or data.get("status", {}).get("ticket")
        if not url and ticket:
            env = self._environment(environment)
            url = f"{str(env.base_url).rstrip('/')}/console/?vm={quote(vm_uuid)}&ticket={quote(ticket)}"
        if not url:
            env = self._environment(environment)
            url = f"{str(env.base_url).rstrip('/')}/console/?vm={quote(vm_uuid)}"
        return ConsoleURL(vm_uuid=vm_uuid, url=url, ticket=ticket)

    def _build_create_payload(self, request: VMCreateRequest) -> Dict[str, Any]:
        disk = {
            "device_properties": {"device_type": "DISK"},
            "disk_size_mib": request.disk_size_mib,
        }
        if request.image_uuid:
            disk["data_source_reference"] = {"kind": "image", "uuid": request.image_uuid}

        return {
            "spec": {
                "name": request.name,
                "description": request.description,
                "resources": {
                    "num_sockets": request.vcpus,
                    "num_vcpus_per_socket": request.cores_per_vcpu,
                    "memory_size_mib": request.memory_mib,
                    "disk_list": [disk],
                    "nic_list": [
                        {
                            "nic_type": "NORMAL_NIC",
                            "subnet_reference": {"kind": "subnet", "uuid": request.network_uuid},
                        }
                    ],
                },
                "cluster_reference": {"kind": "cluster", "uuid": request.cluster_uuid},
            },
            "metadata": {"kind": "vm"},
        }

    def _summary_from_entity(self, environment: str, entity: Dict[str, Any]) -> VMSummary:
        metadata = entity.get("metadata", {})
        spec = entity.get("spec", {})
        status = entity.get("status", {})
        resources = status.get("resources", {})
        return VMSummary(
            uuid=metadata.get("uuid") or entity.get("uuid") or "unknown",
            name=status.get("name") or spec.get("name") or entity.get("name") or "Unnamed VM",
            power_state=resources.get("power_state") or status.get("power_state") or "UNKNOWN",
            environment=environment,
            description=spec.get("description") or status.get("description"),
            ip_addresses=list(self._ip_addresses(resources.get("nic_list", []))),
        )

    def _detail_from_entity(self, environment: str, entity: Dict[str, Any]) -> VMDetail:
        summary = self._summary_from_entity(environment, entity)
        status = entity.get("status", {})
        resources = status.get("resources", {})
        cluster_ref = status.get("cluster_reference") or entity.get("spec", {}).get("cluster_reference") or {}
        return VMDetail(
            **summary.model_dump(),
            cluster_name=cluster_ref.get("name"),
            num_vcpus=resources.get("num_sockets"),
            num_cores_per_vcpu=resources.get("num_vcpus_per_socket"),
            memory_mib=resources.get("memory_size_mib"),
            disks=resources.get("disk_list", []),
            nics=resources.get("nic_list", []),
            raw=entity,
        )

    def _ip_addresses(self, nic_list: Iterable[Dict[str, Any]]) -> Iterable[str]:
        for nic in nic_list:
            for endpoint in nic.get("ip_endpoint_list", []) or []:
                ip = endpoint.get("ip")
                if ip:
                    yield ip
