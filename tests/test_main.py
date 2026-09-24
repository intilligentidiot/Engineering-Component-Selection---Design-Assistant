def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_api_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"api": "operational"}
