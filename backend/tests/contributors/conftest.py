"""Fixtures for contributor tests: reuse the anomaly/metrics ticket world and test DB."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.enums import TicketCategory
from app.services.anomalies.service import AnomalyService
from tests.anomalies.conftest import (  # noqa: F401  (re-exported fixtures)
    DAY,
    END,
    clean_db,
    db_client,
    db_session,
    demo_session,
    engine,
    test_db_url,
    world,
)
from tests.metrics.conftest import World


def build_volume_split(target: World) -> None:
    """Billing 10/day (5 EMEA Enterprise + 5 APAC Starter), then 30 on the current day.

    Current day: 22 EMEA Enterprise (+17) and 8 APAC Starter (+3): shares 85% / 15%.
    """
    for day in range(8):
        start = END - DAY * (8 - day)
        current = day == 7
        for customer, count in (
            (target.emea_enterprise, 22 if current else 5),
            (target.apac_starter, 8 if current else 5),
        ):
            for i in range(count):
                target.ticket(
                    start + timedelta(minutes=10 * i + 5),
                    customer=customer,
                    category=TicketCategory.BILLING,
                    resolved_after=timedelta(hours=1),
                )
    target.session.flush()


def build_breach_split(target: World) -> None:
    """Billing 20 tickets/day per segment. Baseline breaches 2/20 each (10%).

    Current day: EMEA Enterprise breaches 16/20, APAC Starter 4/20. Expected events
    are 2 each, so excess is +14 / +2 and the shares are 87.5% / 12.5%.
    """
    for day in range(8):
        start = END - DAY * (8 - day)
        current = day == 7
        for customer, breaches in (
            (target.emea_enterprise, 16 if current else 2),
            (target.apac_starter, 4 if current else 2),
        ):
            for i in range(20):
                target.ticket(
                    start + timedelta(minutes=10 * i + 5),
                    customer=customer,
                    category=TicketCategory.BILLING,
                    resolved_after=timedelta(hours=1),
                    sla_breached=i < breaches,
                )
    target.session.flush()


def billing_anomaly_id(session: Session, metric_key: str) -> str:
    """Detect over the test window and return the Billing-slice ANOM- ID for the metric."""
    response = AnomalyService(session).detect(END)
    item = next(
        i
        for i in response.items
        if i.metric_key == metric_key and i.filters == {"category": "billing"}
    )
    assert item.anomaly is not None, f"no {metric_key} anomaly was detected"
    return item.anomaly.evidence_id


@pytest.fixture
def volume_world(world: World) -> World:  # noqa: F811
    build_volume_split(world)
    return world


@pytest.fixture
def breach_world(world: World) -> World:  # noqa: F811
    build_breach_split(world)
    return world
