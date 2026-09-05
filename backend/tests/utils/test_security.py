from datetime import timedelta
import uuid

from app.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    RESET_TOKEN_TYPE,
    VERIFICATION_TOKEN_TYPE,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    create_verification_token,
    decode_token,
    hash_password,
    parse_uuid,
    verify_password,
)


def test_password_hashing():
    password = "supersecretpassword123"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_password_hashing_is_salted():
    assert hash_password("samepassword1") != hash_password("samepassword1")


def test_verify_password_handles_a_malformed_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_access_token_claims():
    token = create_access_token(subject="user-12345", expires_delta=timedelta(minutes=5))

    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user-12345"
    assert decoded["type"] == ACCESS_TOKEN_TYPE
    # Access tokens are not revocable and carry no jti.
    assert "jti" not in decoded


def test_refresh_token_carries_a_unique_jti():
    first = decode_token(create_refresh_token(subject="user-67890"))
    second = decode_token(create_refresh_token(subject="user-67890"))

    assert first is not None and second is not None
    assert first["type"] == REFRESH_TOKEN_TYPE
    assert first["jti"] != second["jti"]


def test_email_tokens_are_typed():
    subject = str(uuid.uuid4())
    assert decode_token(create_verification_token(subject))["type"] == VERIFICATION_TOKEN_TYPE
    assert decode_token(create_password_reset_token(subject))["type"] == RESET_TOKEN_TYPE


def test_expired_token_is_rejected():
    token = create_access_token(subject="user-1", expires_delta=timedelta(seconds=-10))
    assert decode_token(token) is None


def test_decode_invalid_token():
    assert decode_token("invalidtokenstring") is None


def test_parse_uuid():
    value = uuid.uuid4()
    assert parse_uuid(str(value)) == value
    assert parse_uuid("not-a-uuid") is None
    assert parse_uuid(None) is None
