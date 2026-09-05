from httpx import AsyncClient


async def test_liveness(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_each_dependency(client: AsyncClient):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "redis": True}


async def test_root_advertises_the_api_prefix(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["api_prefix"] == "/api/v1"
