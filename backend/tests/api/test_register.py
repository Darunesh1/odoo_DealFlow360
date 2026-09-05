"""Public sign-up.

Everyone who registers becomes a customer, and the route is not an account
oracle. Both are security properties, so both get a test.
"""

from app.models.user import Role
from app.services import get_user_by_email

API = "/api"


async def _tier(db_session, name="Bronze", ceiling=5.0):
    from app.models.customer import CustomerTier

    tier = CustomerTier(name=name, max_discount_percent=ceiling)
    db_session.add(tier)
    await db_session.commit()
    return tier


async def test_registration_creates_a_customer_and_nothing_else(
    client, db_session, mock_emails
):
    await _tier(db_session)
    await _tier(db_session, "Gold", 15.0)

    response = await client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Priya Raman",
            "email": "Priya@NovaTech.example",
            "password": "testpass123",
            "company_name": "NovaTech Systems",
        },
    )
    assert response.status_code == 201, response.text

    user = await get_user_by_email(db_session, email="priya@novatech.example")
    assert user is not None
    assert user.roles == [Role.CUSTOMER]
    # Unverified until they follow the emailed link.
    assert user.is_verified is False
    assert user.customer_id is not None
    assert len(mock_emails["verification_emails"]) == 1


async def test_the_company_gets_the_lowest_tier(client, db_session, mock_emails):
    """Nobody talks their way into Gold pricing by filling in a form."""
    from app.models.customer import Customer

    await _tier(db_session, "Gold", 15.0)
    await _tier(db_session, "Bronze", 5.0)

    await client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Sam Buyer",
            "email": "sam@example.com",
            "password": "testpass123",
        },
    )
    user = await get_user_by_email(db_session, email="sam@example.com")
    customer = await db_session.get(Customer, user.customer_id)
    # No company name, so the customer record carries the person's own name.
    assert customer.name == "Sam Buyer"
    assert float(customer.tier.max_discount_percent) == 5.0


async def test_registration_cannot_ask_for_another_role(
    client, db_session, mock_emails
):
    """The schema has no roles field, so an extra one is simply ignored."""
    await _tier(db_session)

    response = await client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Sneaky",
            "email": "sneaky@example.com",
            "password": "testpass123",
            "roles": ["admin"],
            "is_verified": True,
        },
    )
    assert response.status_code == 201

    user = await get_user_by_email(db_session, email="sneaky@example.com")
    assert user.roles == [Role.CUSTOMER]
    assert user.is_verified is False


async def test_registration_is_not_an_account_oracle(client, db_session, mock_emails):
    """A taken address answers exactly as a free one does."""
    await _tier(db_session)

    payload = {
        "full_name": "First Person",
        "email": "taken@example.com",
        "password": "testpass123",
    }
    first = await client.post(f"{API}/auth/register", json=payload)
    second = await client.post(
        f"{API}/auth/register",
        json={**payload, "full_name": "Someone Else"},
    )

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    # And the second attempt created nothing.
    user = await get_user_by_email(db_session, email="taken@example.com")
    assert user.full_name == "First Person"
