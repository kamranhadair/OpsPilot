"""Fixtures for anomaly tests: reuse the metrics ticket world and the guarded test DB."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Anomaly, Customer, Incident, MetricSnapshot, SupportTeam, Ticket
from app.models.enums import TicketCategory
from app.services.demo_data.seeder import seed_demo_data
from tests.metrics.conftest import (  # noqa: F401  (re-exported fixtures)
    World,
    clean_db,
    db_client,
    db_session,
    engine,
    test_db_url,
    world,
)

END = datetime(2026, 3, 10, tzinfo=UTC)
DAY = timedelta(days=1)


def build_billing_spike(target: World) -> None:
    """Seven baseline days (03-02..03-08) then a current day (03-09) with a Billing spike.

    Billing: 10 tickets/day -> 20 (+100%). Technical: flat 15/day. Every ticket is
    resolved within an hour so open backlog stays at zero and cannot add noise.
    """
    for day in range(8):
        start = END - DAY * (8 - day)
        billing = 20 if day == 7 else 10
        for i in range(billing):
            target.ticket(
                start + timedelta(minutes=10 * i + 5),
                category=TicketCategory.BILLING,
                resolved_after=timedelta(hours=1),
            )
        for i in range(15):
            target.ticket(
                start + timedelta(minutes=10 * i + 5),
                category=TicketCategory.TECHNICAL,
                resolved_after=timedelta(hours=1),
            )
    target.session.flush()


@pytest.fixture
def spike_world(world: World) -> World:  # noqa: F811
    build_billing_spike(world)
    return world


@pytest.fixture
def demo_session(db_session: Session) -> Session:  # noqa: F811
    """The deterministic demo dataset seeded into an empty, rolled-back test database."""
    for model in (Anomaly, MetricSnapshot, Ticket, Customer, Incident, SupportTeam):
        db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    db_session.flush()
    seed_demo_data(db_session, settings=Settings(environment="development"))
    return db_session


SessionFactory = Callable[[], Session]
