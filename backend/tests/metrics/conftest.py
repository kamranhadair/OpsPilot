"""Fixtures for metrics tests: the guarded test DB plus a small ticket world."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import Anomaly, Customer, MetricSnapshot, SupportTeam, Ticket
from app.models.enums import CustomerTier, Region, TicketCategory, TicketPriority
from tests.db import factories
from tests.db.conftest import db_session, engine, test_db_url  # noqa: F401  (re-exported)


@dataclass
class World:
    """Two customers in different segments and two teams."""

    session: Session
    emea_enterprise: Customer
    apac_starter: Customer
    billing_team: SupportTeam
    technical_team: SupportTeam

    def ticket(
        self,
        created_at: datetime,
        *,
        customer: Customer | None = None,
        category: TicketCategory = TicketCategory.BILLING,
        priority: TicketPriority = TicketPriority.P3,
        first_response_minutes: int | None = 30,
        resolved_after: timedelta | None = None,
        sla_breached: bool = False,
        escalated: bool = False,
        sentiment: str = "0.200",
    ) -> Ticket:
        customer = customer or self.emea_enterprise
        team = self.billing_team if category is TicketCategory.BILLING else self.technical_team
        resolved_at = None if resolved_after is None else created_at + resolved_after
        resolution = None if resolved_after is None else int(resolved_after.total_seconds() // 60)
        row = factories.ticket(
            customer.id,
            team.id,
            created_at=created_at,
            category=category,
            priority=priority,
            first_response_minutes=first_response_minutes,
            resolved_at=resolved_at,
            resolution_minutes=resolution,
            sla_breached=sla_breached,
            escalated=escalated,
            sentiment_score=Decimal(sentiment),
        )
        self.session.add(row)
        return row


@pytest.fixture
def clean_db(db_session: Session) -> Session:  # noqa: F811
    """Empty domain tables inside the always-rolled-back outer transaction."""
    for model in (Anomaly, MetricSnapshot, Ticket, Customer, SupportTeam):
        db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    db_session.flush()
    return db_session


@pytest.fixture
def world(clean_db: Session) -> World:
    emea = factories.customer(region=Region.EMEA, tier=CustomerTier.ENTERPRISE)
    apac = factories.customer(region=Region.APAC, tier=CustomerTier.STARTER)
    billing = factories.team(team_key="billing-support", name="Billing Support")
    technical = factories.team(team_key="technical-support", name="Technical Support")
    clean_db.add_all([emea, apac, billing, technical])
    clean_db.flush()
    return World(clean_db, emea, apac, billing, technical)


@pytest.fixture
def db_client(clean_db: Session) -> Iterator[TestClient]:
    """API client bound to the rolled-back test session."""
    app.dependency_overrides[get_db] = lambda: clean_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
