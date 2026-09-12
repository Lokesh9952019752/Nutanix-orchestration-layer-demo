from __future__ import annotations

from typing import Any

import httpx

from app.config import PrismEnvironmentSettings
from app.schemas import ConsoleLaunchInfo, VMDisk, VMCreateRequest, VMDetail, VMNic, VMSummary


class PrismClientError(Exception):
    """Application-facing Prism error with environment context."""

    def __init__(self, environment: PrismEnvironmentSettings, message: str, status_code: int | None = None):
        self.environment = environment
        self.status_code = status_code
        super().__init__(message)


class PrismClient:
    """Small Prism Central v3 client that maps API payloads to app schemas."""

    def __init__(self, environment: PrismEnvironmentSettings, client: httpx.AsyncClient | None = None):
        self.environment = environment
        self._client = client

    async def list_vms(self, length: int = 50) -> list[VMSummary]:
        data = await self._request("POST", "/api/nutanix/v3/vms/list", json={"kind": "vm", "offset": 0, "length": length})
        return [self._summary_from_entity(entity) for entity in data.get("entities", [])]

    async def get_vm(self, uuid: str) -> VMDetail:
        data = await self._request("GET", f"/api/nutanix/v3/vms/{uuid}")
        return self._detail_from_entity(data)

    async def create_vm(self, request: VMCreateRequest) -> str:
        data = await self._request("POST", "/api/nutanix/v3/vms", json=self._create_payload(request))
        metadata = data.get("metadata", {})
        status = data.get("status", {})
        return metadata.get("uuid") or status.get("execution_context", {}).get("task_uuid") or status.get("state", "created")

    async def get_console(self, uuid: str) -> ConsoleLaunchInfo:
        data = await self._request("POST", f"/api/nutanix/v3/vms/{uuid}/console", json={})
        resources = data.get("status", {}).get("resources", {})
        url = (
            data.get("url")
            or data.get("console_url")
            or resources.get("url")
            or resources.get("console_url")
            or f"{self.environment.base_url}/console/#/vm/{uuid}"
        )
        ticket = data.get("ticket") or resources.get("ticket")
        return ConsoleLaunchInfo(vm_uuid=uuid, url=url, ticket=ticket, iframe_allowed=True)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.environment.base_url}{path}"
        try:
            if self._client is not None:
                response = await self._client.request(method, url, auth=(self.environment.username, self.environment.password), **kwargs)
            else:
                async with httpx.AsyncClient(verify=self.environment.verify_ssl, timeout=20) as client:
                    response = await client.request(
                        method, url, auth=(self.environment.username, self.environment.password), **kwargs
                    )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error(exc.response)
            raise PrismClientError(self.environment, detail, exc.response.status_code) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise PrismClientError(self.environment, str(exc)) from exc

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or response.reason_phrase
        return str(payload.get("message") or payload.get("error") or payload.get("details") or response.reason_phrase)

    @staticmethod
    def _summary_from_entity(entity: dict[str, Any]) -> VMSummary:
        metadata = entity.get("metadata", {})
        spec = entity.get("spec", {})
        status = entity.get("status", {})
        spec_resources = spec.get("resources", {})
        status_resources = status.get("resources", {})
        return VMSummary(
            uuid=metadata.get("uuid") or entity.get("uuid") or status.get("uuid") or "unknown",
            name=spec.get("name") or status.get("name") or entity.get("name") or "Unnamed VM",
            power_state=status_resources.get("power_state") or status.get("state") or "UNKNOWN",
            cpu_count=spec_resources.get("num_sockets") or status_resources.get("num_sockets"),
            memory_mib=spec_resources.get("memory_size_mib") or status_resources.get("memory_size_mib"),
            description=spec.get("description"),
        )

    @classmethod
    def _detail_from_entity(cls, entity: dict[str, Any]) -> VMDetail:
        summary = cls._summary_from_entity(entity)
        metadata = entity.get("metadata", {})
        spec = entity.get("spec", {})
        resources = spec.get("resources", {}) or entity.get("status", {}).get("resources", {})
        nics = [cls._nic_from_payload(nic) for nic in resources.get("nic_list", [])]
        disks = [cls._disk_from_payload(disk) for disk in resources.get("disk_list", [])]
        cluster_reference = resources.get("cluster_reference", {}) or metadata.get("cluster_reference", {})
        return VMDetail(
            **summary.model_dump(),
            cores_per_socket=resources.get("num_vcpus_per_socket"),
            cluster_uuid=cluster_reference.get("uuid"),
            nics=nics,
            disks=disks,
        )

    @staticmethod
    def _nic_from_payload(payload: dict[str, Any]) -> VMNic:
        subnet = payload.get("subnet_reference", {})
        ip_endpoint_list = payload.get("ip_endpoint_list") or []
        return VMNic(
            subnet_uuid=subnet.get("uuid"),
            ip_address=ip_endpoint_list[0].get("ip") if ip_endpoint_list else None,
            address_mode=payload.get("ip_address_mode") or ("static" if ip_endpoint_list else "dhcp"),
            mac_address=payload.get("mac_address"),
        )

    @staticmethod
    def _disk_from_payload(payload: dict[str, Any]) -> VMDisk:
        disk_size = payload.get("disk_size_mib") or payload.get("disk_size_bytes")
        size_gib = None
        if disk_size is not None:
            size_gib = round(disk_size / 1024, 2) if payload.get("disk_size_mib") else round(disk_size / (1024**3), 2)
        return VMDisk(
            size_gib=size_gib,
            storage_container_uuid=(payload.get("storage_config", {}).get("storage_container_reference", {}) or {}).get("uuid"),
            device_type=(payload.get("device_properties", {}).get("device_type")),
        )

    @staticmethod
    def _create_payload(request: VMCreateRequest) -> dict[str, Any]:
        nic: dict[str, Any] = {
            "subnet_reference": {"kind": "subnet", "uuid": request.subnet_uuid},
            "ip_address_mode": request.address_mode.upper(),
        }
        if request.address_mode == "static" and request.static_ip:
            nic["ip_endpoint_list"] = [{"ip": request.static_ip, "type": "ASSIGNED"}]

        return {
            "api_version": "3.1.0",
            "metadata": {"kind": "vm"},
            "spec": {
                "name": request.name,
                "description": request.description or "",
                "resources": {
                    "num_sockets": request.cpu_count,
                    "num_vcpus_per_socket": request.cores_per_socket,
                    "memory_size_mib": request.memory_mib,
                    "cluster_reference": {"kind": "cluster", "uuid": request.cluster_uuid},
                    "disk_list": [
                        {
                            "data_source_reference": {"kind": "image", "uuid": request.image_uuid},
                            "device_properties": {"device_type": "DISK", "disk_address": {"adapter_type": "SCSI", "device_index": 0}},
                            "disk_size_mib": int(request.disk_gib * 1024),
                        }
                    ],
                    "nic_list": [nic],
                },
            },
        }
