def test_openapi_available(client):
    response=client.get("/api/v1/openapi.json")
    assert response.status_code==200
    assert "/api/v1/worklist" in response.json()["paths"]
