from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.conftest import API, auth_headers, login, make_user





async def test_verify_email_success(
    client: AsyncClient, db_session: AsyncSession, mock_emails
):
    """An unverified account is verified by the token from its email."""
    await make_user(db_session, "verify@example.com", full_name="Verify Me", is_verified=False)

    await client.post(f"{API}/auth/resend-verification", json={"email": "verify@example.com"})
    _, kwargs = mock_emails["verification_emails"][-1]

    response = await client.post(f"{API}/auth/verify-email", json={"token": kwargs["token"]})
    assert response.status_code == 200

    # The session maker sets expire_on_commit=False, so this session would
    # otherwise hand back its own cached copy from before the API's write.
    db_session.expire_all()
    result = await db_session.execute(
        select(User).where(User.email == "verify@example.com")
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.is_verified is True

    assert len(mock_emails["welcome_emails"]) == 1
    _, welcome_kwargs = mock_emails["welcome_emails"][0]
    assert welcome_kwargs["email"] == "verify@example.com"


async def test_verify_email_rejects_wrong_token_type(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "typemix@example.com")
    tokens = await login(client, "typemix@example.com")

    # An access token must not be accepted as a verification token.
    response = await client.post(
        f"{API}/auth/verify-email", json={"token": tokens["access_token"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid token type"


async def test_resend_verification_is_not_an_account_oracle(
    client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "resend@example.com", is_verified=False)
    mock_emails["verification_emails"].clear()

    known = await client.post(
        f"{API}/auth/resend-verification", json={"email": "resend@example.com"}
    )
    unknown = await client.post(
        f"{API}/auth/resend-verification", json={"email": "ghost@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # Only the real account actually receives mail.
    assert len(mock_emails["verification_emails"]) == 1


async def test_login_success(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "loginuser@example.com")

    tokens = await login(client, "loginuser@example.com")
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"


async def test_login_failure(client: AsyncClient):
    response = await client.post(
        f"{API}/auth/login",
        data={"username": "nonexistent@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


async def test_refresh_token_rotates_and_revokes_the_old_token(
    client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "refresh@example.com")
    tokens = await login(client, "refresh@example.com")

    response = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # Replaying the consumed refresh token must fail.
    replay = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["detail"] == "Refresh token has been revoked"


async def test_refresh_rejects_an_access_token(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "wrongtype@example.com")
    tokens = await login(client, "wrongtype@example.com")

    response = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token type, refresh token required"


async def test_logout_revokes_the_refresh_token(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "logout@example.com")
    tokens = await login(client, "logout@example.com")

    response = await client.post(
        f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200

    replay = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


async def test_forgot_password_is_not_an_account_oracle(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "forgot@example.com")

    known = await client.post(
        f"{API}/auth/forgot-password", json={"email": "forgot@example.com"}
    )
    unknown = await client.post(
        f"{API}/auth/forgot-password", json={"email": "ghost@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(mock_emails["reset_emails"]) == 1


async def test_password_reset_flow(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "reset@example.com")
    await client.post(f"{API}/auth/forgot-password", json={"email": "reset@example.com"})

    _, kwargs = mock_emails["reset_emails"][0]
    response = await client.post(
        f"{API}/auth/reset-password",
        json={"token": kwargs["token"], "new_password": "brandnewpass1"},
    )
    assert response.status_code == 200

    # The old password no longer works, the new one does.
    old = await client.post(
        f"{API}/auth/login",
        data={"username": "reset@example.com", "password": "password123"},
    )
    assert old.status_code == 401
    await login(client, "reset@example.com", "brandnewpass1")


async def test_change_password_requires_the_current_one(client: AsyncClient, mock_emails, db_session: AsyncSession):
    await make_user(db_session, "change@example.com")
    headers = await auth_headers(client, "change@example.com")

    wrong = await client.post(
        f"{API}/auth/change-password",
        headers=headers,
        json={"current_password": "notitatall1", "new_password": "anotherpass1"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "Current password is incorrect"

    ok = await client.post(
        f"{API}/auth/change-password",
        headers=headers,
        json={"current_password": "password123", "new_password": "anotherpass1"},
    )
    assert ok.status_code == 200
    await login(client, "change@example.com", "anotherpass1")
