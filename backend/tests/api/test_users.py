from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth_headers, make_user


async def test_get_me_success(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "me@example.com", full_name="Me User")
    headers = await auth_headers(client, "me@example.com")

    response = await client.get(f"{API}/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["full_name"] == "Me User"


async def test_get_me_unauthorized(client: AsyncClient):
    response = await client.get(f"{API}/users/me")
    assert response.status_code == 401


async def test_get_me_rejects_a_refresh_token(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "tokentype@example.com")
    from tests.conftest import login

    tokens = await login(client, "tokentype@example.com")
    response = await client.get(
        f"{API}/users/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token type, access token required"


async def test_update_me_success(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "update@example.com", full_name="Original Name")
    headers = await auth_headers(client, "update@example.com")

    response = await client.patch(
        f"{API}/users/me", headers=headers, json={"full_name": "Updated Name"}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"


async def test_update_me_cannot_grant_roles(client: AsyncClient, mock_emails, db_session: AsyncSession):
    """Regression: PATCH /users/me must not accept privilege fields."""
    await make_user(db_session, "escalate@example.com", is_verified=False)
    headers = await auth_headers(client, "escalate@example.com")

    response = await client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"roles": ["admin"], "is_verified": True, "is_active": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["sales_rep"]
    assert body["is_verified"] is False

    # And the flags really did not change server side.
    me = await client.get(f"{API}/users/me", headers=headers)
    assert me.json()["roles"] == ["sales_rep"]

    # The escalated account still cannot reach the admin area.
    admin = await client.get(f"{API}/admin/users", headers=headers)
    assert admin.status_code == 403


async def test_update_me_email_change_resets_verification(
    client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "changing@example.com")
    headers = await auth_headers(client, "changing@example.com")
    mock_emails["verification_emails"].clear()

    response = await client.patch(
        f"{API}/users/me", headers=headers, json={"email": "changed@example.com"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "changed@example.com"
    assert body["is_verified"] is False
    assert len(mock_emails["verification_emails"]) == 1


async def test_update_me_email_conflict(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "usera@example.com", full_name="User A")
    await make_user(db_session, "userb@example.com", full_name="User B")
    headers_b = await auth_headers(client, "userb@example.com")

    response = await client.patch(
        f"{API}/users/me", headers=headers_b, json={"email": "usera@example.com"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "A user with this email address already exists."


async def test_delete_me(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "goodbye@example.com")
    headers = await auth_headers(client, "goodbye@example.com")

    response = await client.delete(f"{API}/users/me", headers=headers)
    assert response.status_code == 200

    # The token is well formed but the account is gone.
    me = await client.get(f"{API}/users/me", headers=headers)
    assert me.status_code == 401
