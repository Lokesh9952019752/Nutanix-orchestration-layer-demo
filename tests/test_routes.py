from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas import ConsoleURL, TaskReference, VMDetail, VMSummary


class FakePrismClient:
    def __init__(self):
        self.created = []

    async def list_vms(self, environment: str):
        if environment == "on_prem":
            return [VMSummary(uuid="vm-1", name="onprem-vm", power_state="ON", environment=environment)]
        if environment == "nc2_aws":
            return [VMSummary(uuid="vm-2", name="aws-vm", power_state="OFF", environment=environment)]
        raise AssertionError(environment)

    async def create_vm(self, environment: str, request):
        self.created.append((environment, request))
        return TaskReference(uuid="task-123", status="PENDING")

    async def get_vm(self, environment: str, vm_uuid: str):
        return VMDetail(uuid=vm_uuid, name="detail-vm", power_state="ON", environment=environment, memory_mib=2048)

    async def get_console_url(self, environment: str, vm_uuid: str):
        return ConsoleURL(vm_uuid=vm_uuid, url="https://console.example.com/session")


class PartiallyFailingClient(FakePrismClient):
    async def list_vms(self, environment: str):
        if environment == "on_prem":
            raise RuntimeError("portal unavailable")
        return await super().list_vms(environment)


def make_client(fake=None):
    fake = fake or FakePrismClient()
    settings = Settings(
        APP_ADMIN_USERNAME="admin",
        APP_ADMIN_PASSWORD="password",
        SESSION_SECRET="test-secret",
    )
    return TestClient(create_app(settings=settings, prism_client_factory=lambda settings: fake)), fake


def login(client: TestClient):
    response = client.post("/login", data={"username": "admin", "password": "password"})
    assert response.status_code == 200


def test_protected_routes_require_login():
    client, _fake = make_client()

    html_response = client.get("/")
    api_response = client.get("/api/environments/on_prem/vms")

    assert html_response.status_code == 200
    assert "Management login" in html_response.text
    assert api_response.status_code == 401


def test_dashboard_shows_both_environments_after_login():
    client, _fake = make_client()
    login(client)

    response = client.get("/")

    assert response.status_code == 200
    assert "On-Prem Prism Central" in response.text
    assert "NC2 AWS Prism Central" in response.text
    assert "onprem-vm" in response.text
    assert "aws-vm" in response.text


def test_vm_creation_calls_selected_environment():
    client, fake = make_client()
    login(client)

    response = client.post(
        "/api/environments/nc2_aws/vms",
        json={
            "name": "created-vm",
            "cluster_uuid": "cluster-1",
            "network_uuid": "subnet-1",
            "vcpus": 2,
            "cores_per_vcpu": 1,
            "memory_mib": 4096,
            "disk_size_mib": 51200,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"uuid": "task-123", "status": "PENDING", "message": None}
    assert fake.created[0][0] == "nc2_aws"
    assert fake.created[0][1].name == "created-vm"


def test_failed_environment_does_not_hide_other_environment():
    client, _fake = make_client(PartiallyFailingClient())
    login(client)

    response = client.get("/")

    assert response.status_code == 200
    assert "portal unavailable" in response.text
    assert "aws-vm" in response.text


def test_detail_and_console_pages_render():
    client, _fake = make_client()
    login(client)

    detail = client.get("/environments/on_prem/vms/vm-1")
    console = client.get("/environments/on_prem/vms/vm-1/console")

    assert detail.status_code == 200
    assert "detail-vm" in detail.text
    assert console.status_code == 200
    assert "https://console.example.com/session" in console.text
