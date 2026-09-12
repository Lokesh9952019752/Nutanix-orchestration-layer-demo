from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.prism_client import PrismClientError
from app.schemas import ConsoleLaunchInfo, VMDisk, VMCreateRequest, VMDetail, VMNic, VMSummary


class FakePrismClient:
    created_requests: list[tuple[str, VMCreateRequest]] = []

    def __init__(self, environment):
        self.environment = environment

    async def list_vms(self):
        if self.environment.key == "onprem":
            return [VMSummary(uuid="onprem-vm", name="OnPrem VM", power_state="ON", cpu_count=2, memory_mib=4096)]
        raise PrismClientError(self.environment, "NC2 unavailable", 503)

    async def get_vm(self, uuid: str):
        return VMDetail(
            uuid=uuid,
            name="Detail VM",
            power_state="ON",
            cpu_count=4,
            memory_mib=8192,
            cores_per_socket=2,
            cluster_uuid="cluster-1",
            nics=[VMNic(subnet_uuid="subnet-1", ip_address="10.0.0.5")],
            disks=[VMDisk(size_gib=20, device_type="DISK")],
        )

    async def create_vm(self, request: VMCreateRequest):
        self.created_requests.append((self.environment.key, request))
        return "created-vm"

    async def get_console(self, uuid: str):
        return ConsoleLaunchInfo(vm_uuid=uuid, url=f"https://console.example/{uuid}")


def make_client() -> TestClient:
    FakePrismClient.created_requests = []
    app = create_app(settings=Settings(), prism_client_factory=lambda environment: FakePrismClient(environment))
    client = TestClient(app)
    response = client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
    assert response.status_code == 303
    return client


def test_dashboard_renders_independent_environment_error():
    client = make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "OnPrem VM" in response.text
    assert "NC2 unavailable" in response.text
    assert "On-prem Prism Central" in response.text
    assert "NC2 AWS Prism Central" in response.text


def test_status_endpoint_reports_partial_failure():
    client = make_client()

    response = client.get("/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["environments"]["onprem"] == {"ok": True, "vm_count": 1}
    assert payload["environments"]["nc2_aws"]["ok"] is False
    assert payload["environments"]["nc2_aws"]["status_code"] == 503


def test_vm_detail_and_console_routes_use_client_models():
    client = make_client()

    detail = client.get("/environments/onprem/vms/onprem-vm")
    console = client.get("/environments/onprem/vms/onprem-vm/console")

    assert detail.status_code == 200
    assert "Detail VM" in detail.text
    assert "10.0.0.5" in detail.text
    assert console.status_code == 200
    assert "https://console.example/onprem-vm" in console.text
    assert "Launch console in a new tab" in console.text


def test_create_vm_validates_form_and_redirects_to_detail():
    client = make_client()

    response = client.post(
        "/environments/onprem/vms",
        data={
            "name": "created",
            "cpu_count": "2",
            "cores_per_socket": "1",
            "memory_gib": "4",
            "disk_gib": "20",
            "image_uuid": "image-1",
            "subnet_uuid": "subnet-1",
            "cluster_uuid": "cluster-1",
            "address_mode": "dhcp",
            "description": "route test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/environments/onprem/vms/created-vm"
    assert FakePrismClient.created_requests[0][0] == "onprem"
    assert FakePrismClient.created_requests[0][1].memory_mib == 4096
