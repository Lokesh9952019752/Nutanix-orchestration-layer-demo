import asyncio
import json

import httpx

from app.config import Settings
from app.prism_client import PrismClient
from app.schemas import VMCreateRequest


def run(coro):
    return asyncio.run(coro)


def settings() -> Settings:
    return Settings(
        SESSION_SECRET="test-secret",
        PRISM_ONPREM_URL="https://onprem.example.com",
        PRISM_ONPREM_USERNAME="on-user",
        PRISM_ONPREM_PASSWORD="on-pass",
        PRISM_NC2_AWS_URL="https://nc2.example.com",
        PRISM_NC2_AWS_USERNAME="aws-user",
        PRISM_NC2_AWS_PASSWORD="aws-pass",
    )


def json_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_list_vms_uses_environment_endpoint_auth_and_normalizes_response():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://onprem.example.com/api/nutanix/v3/vms/list"
        assert request.method == "POST"
        assert request.headers["authorization"].startswith("Basic ")
        assert json.loads(request.content)["kind"] == "vm"
        return json_response(
            {
                "entities": [
                    {
                        "metadata": {"uuid": "vm-1"},
                        "spec": {"name": "web-1", "description": "demo"},
                        "status": {
                            "resources": {
                                "power_state": "ON",
                                "nic_list": [{"ip_endpoint_list": [{"ip": "10.1.2.3"}]}],
                            }
                        },
                    }
                ]
            }
        )

    client = PrismClient(settings(), transport=httpx.MockTransport(handler))
    vms = run(client.list_vms("on_prem"))

    assert len(requests) == 1
    assert vms[0].uuid == "vm-1"
    assert vms[0].environment == "on_prem"
    assert vms[0].ip_addresses == ["10.1.2.3"]


def test_create_vm_maps_payload_to_prism_v3_shape_and_selected_environment():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return json_response({"status": {"execution_context": {"task_uuid": "task-1"}, "state": "PENDING"}})

    client = PrismClient(settings(), transport=httpx.MockTransport(handler))
    task = run(
        client.create_vm(
            "nc2_aws",
            VMCreateRequest(
                name="app-1",
                description="created in test",
                cluster_uuid="cluster-1",
                image_uuid="image-1",
                network_uuid="subnet-1",
                vcpus=4,
                cores_per_vcpu=2,
                memory_mib=8192,
                disk_size_mib=102400,
            ),
        )
    )

    assert captured["url"] == "https://nc2.example.com/api/nutanix/v3/vms"
    spec = captured["payload"]["spec"]
    assert spec["name"] == "app-1"
    assert spec["cluster_reference"] == {"kind": "cluster", "uuid": "cluster-1"}
    assert spec["resources"]["num_sockets"] == 4
    assert spec["resources"]["num_vcpus_per_socket"] == 2
    assert spec["resources"]["memory_size_mib"] == 8192
    assert spec["resources"]["disk_list"][0]["data_source_reference"] == {"kind": "image", "uuid": "image-1"}
    assert spec["resources"]["nic_list"][0]["subnet_reference"] == {"kind": "subnet", "uuid": "subnet-1"}
    assert task.uuid == "task-1"
    assert task.status == "PENDING"


def test_get_vm_detail_and_console_url_are_normalized():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/console"):
            return json_response({"status": {"console_url": "https://console.example.com/session"}, "ticket": "abc"})
        return json_response(
            {
                "metadata": {"uuid": "vm-2"},
                "spec": {"name": "db-1"},
                "status": {
                    "cluster_reference": {"name": "cluster-a"},
                    "resources": {
                        "power_state": "OFF",
                        "num_sockets": 2,
                        "num_vcpus_per_socket": 1,
                        "memory_size_mib": 4096,
                        "disk_list": [{"disk_size_mib": 51200}],
                        "nic_list": [],
                    },
                },
            }
        )

    client = PrismClient(settings(), transport=httpx.MockTransport(handler))

    detail = run(client.get_vm("on_prem", "vm-2"))
    console = run(client.get_console_url("on_prem", "vm-2"))

    assert detail.name == "db-1"
    assert detail.cluster_name == "cluster-a"
    assert detail.memory_mib == 4096
    assert str(console.url) == "https://console.example.com/session"
    assert console.ticket == "abc"
