def test_health(client):
    response=client.get("/health")
    assert response.status_code==200
    assert response.json()["status"]=="ok"

def test_unhandled_error_uses_envelope(client):
    from app.main import app
    @app.get("/boom")
    def boom(): raise RuntimeError("x")
    from fastapi.testclient import TestClient
    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR" and r.json()["success"] is False
