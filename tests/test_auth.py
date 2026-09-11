from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class EmptyPrismClient:
    async def list_vms(self, environment: str):
        return []


def build_client() -> TestClient:
    settings = Settings(
        APP_ADMIN_USERNAME="boss",
        APP_ADMIN_PASSWORD="secret",
        SESSION_SECRET="test-secret",
    )
    return TestClient(create_app(settings=settings, prism_client_factory=lambda settings: EmptyPrismClient()))


def test_valid_login_creates_session_and_reaches_dashboard():
    client = build_client()

    response = client.post("/login", data={"username": "boss", "password": "secret"})

    assert response.status_code == 200
    assert "Prism Central dashboard" in response.text


def test_invalid_login_shows_error_without_session():
    client = build_client()

    response = client.post("/login", data={"username": "boss", "password": "wrong"})

    assert response.status_code == 401
    assert "Invalid username or password" in response.text
    protected = client.get("/api/environments/on_prem/vms")
    assert protected.status_code == 401


def test_logout_clears_session():
    client = build_client()
    client.post("/login", data={"username": "boss", "password": "secret"})

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    protected = client.get("/api/environments/on_prem/vms")
    assert protected.status_code == 401
