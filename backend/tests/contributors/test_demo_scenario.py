"""The planted Billing scenario in the seeded demo dataset, end to end."""

import pytest
from sqlalchemy.orm import Session

from app.schemas.contributors import ContributorAnalysisResponse, ContributorGroupOut
from app.services.anomalies.service import AnomalyService
from app.services.contributors.service import ContributorService

pytestmark = pytest.mark.db


def billing_contributors(session: Session, metric_key: str) -> ContributorAnalysisResponse:
    detected = AnomalyService(session).detect(None)
    item = next(
        i
        for i in detected.items
        if i.metric_key == metric_key and i.filters == {"category": "billing"}
    )
    assert item.anomaly is not None
    return ContributorService(session).compute(item.anomaly.evidence_id)


def group(response: ContributorAnalysisResponse, key: str) -> ContributorGroupOut:
    return next(g for g in response.groups if g.family_key == key)


def test_emea_enterprise_is_the_top_billing_volume_contributor(demo_session: Session) -> None:
    response = billing_contributors(demo_session, "ticket_volume")

    top = group(response, "region+customer_tier").contributors[0]
    assert top.segment == {"region": "emea", "customer_tier": "enterprise"}
    assert top.rank == 1
    assert top.contribution_pct > 50  # a clear majority of the positive change
    assert top.evidence_id.startswith("SEG-")
    assert "EMEA / Enterprise" in top.statement


def test_single_dimension_families_agree_on_emea_and_enterprise(demo_session: Session) -> None:
    response = billing_contributors(demo_session, "ticket_volume")

    assert group(response, "region").contributors[0].segment == {"region": "emea"}
    assert group(response, "customer_tier").contributors[0].segment == {
        "customer_tier": "enterprise"
    }
    assert group(response, "product").contributors[0].segment == {"product": "billing_api"}


def test_billing_sla_breach_anomaly_also_computes_contributors(demo_session: Session) -> None:
    response = billing_contributors(demo_session, "sla_breach_rate")

    assert response.groups
    for g in response.groups:
        assert g.method.value == "rate_excess"
        shares = sum(c.contribution_pct for c in g.contributors)
        assert shares + g.other_contribution_pct == pytest.approx(100.0, abs=0.001)


def test_demo_contributor_computation_is_idempotent(demo_session: Session) -> None:
    first = billing_contributors(demo_session, "ticket_volume")
    second = billing_contributors(demo_session, "ticket_volume")

    assert (first.status, second.status) == ("computed", "reused")
    assert second.groups == first.groups
