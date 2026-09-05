from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import unusable_password, verify_password
from tests.conftest import API, admin_headers, login


def test_an_unusable_password_never_verifies():
    """The whole invite design rests on this: a pending account cannot be signed into."""
    sentinel = unusable_password()
    assert verify_password("anything", sentinel) is False
    assert verify_password("", sentinel) is False
    assert verify_password(sentinel, sentinel) is False


async def test_invite_flow(client: AsyncClient, db_session: AsyncSession, mock_emails):
    """An admin creates an account; the invitee sets their own password."""
    headers = await admin_headers(client, db_session)

    created = await client.post(
        f"{API}/admin/users",
        headers=headers,
        json={
            "email": "invited@example.com",
            "full_name": "Invited Person",
            "roles": ["sales_rep", "sales_manager"],
        },
    )
    assert created.status_code == 201
    assert created.json()["roles"] == ["sales_rep", "sales_manager"]
    assert created.json()["is_verified"] is False

    # Nobody can sign in before the invitation is accepted.
    blocked = await client.post(
        f"{API}/auth/login",
        data={"username": "invited@example.com", "password": "anything123"},
    )
    assert blocked.status_code == 401

    _, kwargs = mock_emails["invite_emails"][-1]
    accepted = await client.post(
        f"{API}/auth/accept-invite",
        json={"token": kwargs["token"], "new_password": "chosenpass123"},
    )
    assert accepted.status_code == 200

    tokens = await login(client, "invited@example.com", "chosenpass123")
    me = await client.get(
        f"{API}/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.json()["is_verified"] is True
    assert me.json()["roles"] == ["sales_rep", "sales_manager"]


async def test_accept_invite_is_single_use(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    """Replaying the link must not let anyone overwrite a live password."""
    headers = await admin_headers(client, db_session)
    await client.post(
        f"{API}/admin/users",
        headers=headers,
        json={"email": "once@example.com", "full_name": "Once", "roles": ["customer"]},
    )
    _, kwargs = mock_emails["invite_emails"][-1]

    first = await client.post(
        f"{API}/auth/accept-invite",
        json={"token": kwargs["token"], "new_password": "chosenpass123"},
    )
    assert first.status_code == 200

    replay = await client.post(
        f"{API}/auth/accept-invite",
        json={"token": kwargs["token"], "new_password": "hijacked123"},
    )
    assert replay.status_code == 400

    # The original password still works, so the replay changed nothing.
    await login(client, "once@example.com", "chosenpass123")
