from fastapi.testclient import TestClient

from app.auth import read_session, verify_credentials
from app.config import Settings
from app.main import create_app


class EmptyClient:
    async def list_vms(self):
        return []


def test_default_admin_credentials_work():
    settings = Settings()
    assert verify_credentials("admin", "admin", settings)
    assert not verify_credentials("admin", "wrong", settings)


def test_login_issues_signed_session_and_protected_routes_redirect_without_it():
    app = create_app(settings=Settings(), prism_client_factory=lambda environment: EmptyClient())
    client = TestClient(app)

    protected = client.get("/", follow_redirects=False)
    assert protected.status_code == 303
    assert protected.headers["location"] == "/login"

    failed = client.post("/login", data={"username": "admin", "password": "bad"})
    assert failed.status_code == 401
    assert "Invalid username or password" in failed.text

    logged_in = client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
    assert logged_in.status_code == 303
    assert "prism_demo_session" in logged_in.cookies

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "VM Dashboard" in dashboard.text


def test_tampered_session_is_rejected():
    app = create_app(settings=Settings(), prism_client_factory=lambda environment: EmptyClient())
    client = TestClient(app)
    client.cookies.set("prism_demo_session", "not-a-valid-token")

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
