import asyncio
import json

import httpx

from app.config import PrismEnvironmentSettings
from app.prism_client import PrismClient, PrismClientError
from app.schemas import VMCreateRequest


def environment() -> PrismEnvironmentSettings:
    return PrismEnvironmentSettings(
        key="onprem",
        label="On-prem Prism Central",
        base_url="https://prism.example.com/",
        username="user",
        password="pass",
        verify_ssl=False,
    )


def run(coro):
    return asyncio.run(coro)


def test_list_vms_shapes_request_and_normalizes_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "entities": [
                    {
                        "metadata": {"uuid": "vm-1"},
                        "spec": {"name": "web-1", "resources": {"num_sockets": 2, "memory_size_mib": 4096}},
                        "status": {"resources": {"power_state": "ON"}},
                    }
                ]
            },
        )

    client = PrismClient(environment(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        vms = run(client.list_vms(length=25))
    finally:
        run(client._client.aclose())

    assert seen["method"] == "POST"
    assert seen["path"] == "/api/nutanix/v3/vms/list"
    assert seen["body"] == {"kind": "vm", "offset": 0, "length": 25}
    assert seen["auth"].startswith("Basic ")
    assert vms[0].uuid == "vm-1"
    assert vms[0].name == "web-1"
    assert vms[0].power_state == "ON"


def test_get_vm_and_console_use_expected_endpoints():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append((request.method, request.url.path))
        if request.url.path.endswith("/console"):
            return httpx.Response(200, json={"status": {"resources": {"console_url": "https://console.example/vm-1"}}})
        return httpx.Response(
            200,
            json={
                "metadata": {"uuid": "vm-1"},
                "spec": {
                    "name": "db-1",
                    "resources": {
                        "num_sockets": 4,
                        "num_vcpus_per_socket": 2,
                        "memory_size_mib": 8192,
                        "cluster_reference": {"uuid": "cluster-1"},
                        "nic_list": [{"subnet_reference": {"uuid": "subnet-1"}, "ip_endpoint_list": [{"ip": "10.0.0.5"}]}],
                        "disk_list": [{"disk_size_mib": 20480, "device_properties": {"device_type": "DISK"}}],
                    },
                },
                "status": {"resources": {"power_state": "OFF"}},
            },
        )

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PrismClient(environment(), async_client)
    try:
        detail = run(client.get_vm("vm-1"))
        console = run(client.get_console("vm-1"))
    finally:
        run(async_client.aclose())

    assert paths == [("GET", "/api/nutanix/v3/vms/vm-1"), ("POST", "/api/nutanix/v3/vms/vm-1/console")]
    assert detail.cluster_uuid == "cluster-1"
    assert detail.nics[0].ip_address == "10.0.0.5"
    assert detail.disks[0].size_gib == 20
    assert console.url == "https://console.example/vm-1"


def test_create_vm_payload_contains_demo_form_fields():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"metadata": {"uuid": "created-vm"}})

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PrismClient(environment(), async_client)
    try:
        created = run(
            client.create_vm(
                VMCreateRequest(
                    name="new-vm",
                    cpu_count=2,
                    cores_per_socket=1,
                    memory_gib=4,
                    disk_gib=30,
                    image_uuid="image-1",
                    subnet_uuid="subnet-1",
                    cluster_uuid="cluster-1",
                    address_mode="static",
                    static_ip="10.0.0.10",
                    description="demo",
                )
            )
        )
    finally:
        run(async_client.aclose())

    resources = captured["body"]["spec"]["resources"]
    assert captured["path"] == "/api/nutanix/v3/vms"
    assert created == "created-vm"
    assert resources["memory_size_mib"] == 4096
    assert resources["disk_list"][0]["data_source_reference"]["uuid"] == "image-1"
    assert resources["nic_list"][0]["ip_endpoint_list"][0]["ip"] == "10.0.0.10"


def test_http_error_becomes_prism_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "maintenance"})

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PrismClient(environment(), async_client)
    try:
        try:
            run(client.list_vms())
        except PrismClientError as exc:
            assert exc.status_code == 503
            assert "maintenance" in str(exc)
        else:
            raise AssertionError("expected PrismClientError")
    finally:
        run(async_client.aclose())
