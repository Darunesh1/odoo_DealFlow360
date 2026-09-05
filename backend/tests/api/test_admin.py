import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, admin_headers, auth_headers, make_user


async def test_admin_routes_require_an_admin_role(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "plain@example.com")
    headers = await auth_headers(client, "plain@example.com")

    response = await client.get(f"{API}/admin/users", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "The user does not have enough privileges"


async def test_admin_routes_require_authentication(client: AsyncClient):
    response = await client.get(f"{API}/admin/users")
    assert response.status_code == 401


async def test_list_users_paginates(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    headers = await admin_headers(client, db_session)
    for index in range(4):
        await make_user(db_session, f"user{index}@example.com")

    response = await client.get(f"{API}/admin/users?page=1&size=2", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5  # 4 users plus the admin
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["pages"] == 3
    assert len(body["items"]) == 2

    page_two = await client.get(f"{API}/admin/users?page=3&size=2", headers=headers)
    assert len(page_two.json()["items"]) == 1


async def test_list_users_search_and_filter(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    headers = await admin_headers(client, db_session)
    await make_user(db_session, "findme@example.com", full_name="Findable Person")
    await make_user(db_session, "other@example.com", full_name="Someone Else")

    by_email = await client.get(f"{API}/admin/users?search=findme", headers=headers)
    assert [item["email"] for item in by_email.json()["items"]] == ["findme@example.com"]

    by_name = await client.get(f"{API}/admin/users?search=findable", headers=headers)
    assert by_name.json()["total"] == 1

    active = await client.get(f"{API}/admin/users?is_active=false", headers=headers)
    assert active.json()["total"] == 0


async def test_admin_can_update_and_delete_a_user(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    headers = await admin_headers(client, db_session)
    target = await make_user(db_session, "target@example.com")

    updated = await client.patch(
        f"{API}/admin/users/{target.id}",
        headers=headers,
        json={"is_active": False, "is_verified": True, "full_name": "Renamed"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["is_active"] is False
    assert body["is_verified"] is True
    assert body["full_name"] == "Renamed"

    # A deactivated account can no longer authenticate.
    denied = await client.post(
        f"{API}/auth/login",
        data={"username": "target@example.com", "password": "password123"},
    )
    assert denied.status_code == 403

    deleted = await client.delete(f"{API}/admin/users/{target.id}", headers=headers)
    assert deleted.status_code == 200

    missing = await client.get(f"{API}/admin/users/{target.id}", headers=headers)
    assert missing.status_code == 404


async def test_admin_cannot_lock_themselves_out(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    headers = await admin_headers(client, db_session)
    me = await client.get(f"{API}/users/me", headers=headers)
    admin_id = me.json()["id"]

    demote = await client.patch(
        f"{API}/admin/users/{admin_id}", headers=headers, json={"roles": ["sales_rep"]}
    )
    assert demote.status_code == 400

    deactivate = await client.patch(
        f"{API}/admin/users/{admin_id}", headers=headers, json={"is_active": False}
    )
    assert deactivate.status_code == 400

    self_delete = await client.delete(f"{API}/admin/users/{admin_id}", headers=headers)
    assert self_delete.status_code == 400


async def test_admin_get_unknown_user_is_404(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    headers = await admin_headers(client, db_session)
    response = await client.get(f"{API}/admin/users/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
