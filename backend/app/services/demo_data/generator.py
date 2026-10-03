"""Deterministic synthetic support-data generator (pure; no database access).

Phases are kept separate and each draws from its own named random stream, so
changing one phase never reshuffles another:

1. entity creation (teams, customers)
2. normal ticket generation
3. anomaly injection (the planted Billing incident)
4. incident/timeline creation
5. ref assignment

The generator only creates raw operational rows. It never computes metrics,
anomalies, contributors, briefs, or actions.

SLA modelling note: ``sla_breached`` and ``first_response_minutes`` are stamped for
every ticket (no right-censoring at the window end), so the final days keep an
unbiased breach rate. Only resolution fields are censored by the window end.
"""

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal

from app.models.enums import (
    CustomerTier,
    Product,
    Region,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.services.demo_data.config import (
    DEFAULT_CONFIG,
    TEAMS,
    DemoDataConfig,
    SentimentConfig,
)
from app.services.demo_data.records import (
    CustomerRecord,
    DemoDataset,
    IncidentRecord,
    TeamRecord,
    TicketRecord,
)

_NAME_STEMS = (
    "Northstar", "Brightwave", "Quillfeather", "Marblegate", "Lumenfield", "Copperleaf",
    "Tidewater", "Ironbloom", "Silverpine", "Harborlight", "Stonebridge", "Windmere",
    "Ashgrove", "Cobaltcrest", "Driftwood", "Emberfall", "Foxglen", "Glasshaven",
    "Highmeadow", "Juniperly", "Kestrelton", "Larkspur", "Mossvale", "Nightingale",
    "Oakhollow", "Pebblebrook", "Quartzmoor", "Ravenwick", "Saltmarsh", "Thistledown",
    "Umberfield", "Valewood", "Willowmere", "Yarrowbend", "Zephyrine", "Amberlock",
    "Birchwell", "Cinderwood", "Dunmoor", "Elmstead", "Fernhollow", "Goldcrest",
    "Hazelbrook", "Inkwell", "Jadestone", "Kingfisher", "Lotusbank", "Mistral",
    "Netherby", "Orchardly", "Pinecrest", "Quillon", "Rosemont", "Sundial",
    "Tamarind", "Underhill", "Vinewood", "Whitecap", "Yewgarden", "Zenithly",
)  # fmt: skip
_NAME_SUFFIXES = ("Labs", "Systems", "Cloud", "Analytics", "Works", "Logistics", "Health", "Retail")

_SUBJECTS: dict[TicketCategory, tuple[str, ...]] = {
    TicketCategory.BILLING: (
        "Invoice total does not match our plan",
        "Question about a charge on the latest invoice",
        "Need a copy of last month's invoice",
        "Proration looks wrong after seat change",
        "Payment method update failing",
    ),
    TicketCategory.TECHNICAL: (
        "Dashboard loads slowly for large workspaces",
        "Export job stuck in queue",
        "Unexpected error when saving a report",
        "Search results missing recent records",
        "Scheduled report did not run",
    ),
    TicketCategory.INTEGRATION: (
        "Webhook deliveries are delayed",
        "API token rejected by the sync connector",
        "Field mapping missing in the CRM integration",
        "Rate limit questions for the public API",
        "SSO connector configuration help",
    ),
    TicketCategory.ACCOUNT: (
        "Add a new admin to our workspace",
        "Change the account owner email",
        "Cancel a seat at renewal",
        "Request to rename the organisation",
        "Question about data retention settings",
    ),
}


class TicketRefCollisionError(Exception):
    """Raised when two generated tickets would share the same ``ticket_ref``."""


def _stream(config: DemoDataConfig, phase: str) -> random.Random:
    """Independent, process-stable random stream (string seeds are hash-seed safe)."""
    return random.Random(f"{config.seed}:{phase}")


def _weighted[T](rng: random.Random, weights: Mapping[T, float]) -> T:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


# --- 1. entity creation -----------------------------------------------------------


def build_teams() -> tuple[TeamRecord, ...]:
    return tuple(TeamRecord(team_key=t.team_key, name=t.name) for t in TEAMS)


def build_customers(config: DemoDataConfig, rng: random.Random) -> tuple[CustomerRecord, ...]:
    cells = [
        (region, tier, count)
        for region in Region
        for tier in (CustomerTier.ENTERPRISE, CustomerTier.BUSINESS, CustomerTier.STARTER)
        for count in (config.customers.customers_per_cell[tier],)
    ]
    total = sum(count for _, _, count in cells)
    names = [f"{stem} {suffix}" for stem in _NAME_STEMS for suffix in _NAME_SUFFIXES]
    rng.shuffle(names)
    if total > len(names):
        raise ValueError("Not enough synthetic customer names for the configured customer count")

    customers: list[CustomerRecord] = []
    for region, tier, count in cells:
        for _ in range(count):
            number = len(customers) + 1
            customers.append(
                CustomerRecord(
                    customer_ref=f"{config.customer_ref_prefix}{number:04d}",
                    name=names[number - 1],
                    tier=tier,
                    region=region,
                )
            )
    return tuple(customers)


# --- shared ticket construction ---------------------------------------------------


def _team_for(category: TicketCategory) -> str:
    return next(t.team_key for t in TEAMS if t.category is category)


def _sample_sentiment(rng: random.Random, cfg: SentimentConfig) -> Decimal:
    if rng.random() < cfg.negative_tail_probability:
        score = rng.gauss(cfg.tail_mean, cfg.tail_sd)
    else:
        score = rng.gauss(cfg.mean, cfg.sd)
    return Decimal(f"{max(-1.0, min(1.0, score)):.3f}")


def _build_ticket(
    rng: random.Random,
    config: DemoDataConfig,
    *,
    created_at: datetime,
    customer: CustomerRecord,
    category: TicketCategory,
    product: Product,
    priority: TicketPriority,
    breach_probability: float,
    escalation_probability: float,
    sentiment: SentimentConfig,
) -> TicketRecord:
    profile = config.priority
    target = profile.sla_target_minutes[priority]

    if rng.random() < breach_probability:
        first_response = int(target * (1.02 + rng.expovariate(4.0)))
    else:
        first_response = max(1, int(target * 0.97 * rng.betavariate(1.8, 3.2)))
    breached = first_response > target

    resolution = first_response + int(
        profile.median_resolution_minutes[priority]
        * rng.lognormvariate(0.0, profile.resolution_sigma)
    )
    resolved_at: datetime | None = created_at + timedelta(minutes=resolution)
    resolution_minutes: int | None = resolution
    pending_roll = rng.random()
    if resolved_at is not None and resolved_at < config.window_end:
        age = config.window_end - resolved_at
        status = TicketStatus.CLOSED if age > timedelta(days=3) else TicketStatus.SOLVED
    else:
        resolved_at = None
        resolution_minutes = None
        status = TicketStatus.PENDING if pending_roll < 0.5 else TicketStatus.OPEN

    return TicketRecord(
        ticket_ref="",  # assigned after global ordering
        customer_ref=customer.customer_ref,
        team_key=_team_for(category),
        created_at=created_at,
        resolved_at=resolved_at,
        priority=priority,
        status=status,
        channel=_weighted(rng, config.mix.channel_weights),
        category=category,
        product=product,
        first_response_minutes=first_response,
        resolution_minutes=resolution_minutes,
        sla_target_minutes=target,
        sla_breached=breached,
        sentiment_score=_sample_sentiment(rng, sentiment),
        escalated=rng.random() < escalation_probability,
        subject=rng.choice(_SUBJECTS[category]),
    )


# --- 2. normal ticket generation --------------------------------------------------


def generate_normal_tickets(
    config: DemoDataConfig,
    customers: Sequence[CustomerRecord],
    rng: random.Random,
) -> list[TicketRecord]:
    volume = config.volume
    weights = [config.customers.ticket_propensity[c.tier] for c in customers]
    hours = list(range(24))
    tickets: list[TicketRecord] = []

    day = config.window_start
    while day < config.window_end:
        mean = volume.weekend_mean if day.weekday() >= 5 else volume.weekday_mean
        count = max(0, round(rng.gauss(mean, mean * volume.daily_noise_sd)))
        for _ in range(count):
            hour = rng.choices(hours, weights=volume.hour_weights, k=1)[0]
            created_at = day + timedelta(
                hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60)
            )
            category = _weighted(rng, config.mix.category_weights)
            priority = _weighted(rng, config.priority.weights)
            tickets.append(
                _build_ticket(
                    rng,
                    config,
                    created_at=created_at,
                    customer=rng.choices(customers, weights=weights, k=1)[0],
                    category=category,
                    product=_weighted(rng, config.mix.product_affinity[category]),
                    priority=priority,
                    breach_probability=config.priority.base_breach_probability[priority],
                    escalation_probability=config.escalation.probability,
                    sentiment=config.sentiment,
                )
            )
        day += timedelta(days=1)
    return tickets


# --- 3. anomaly injection ---------------------------------------------------------


def inject_billing_anomaly(
    config: DemoDataConfig,
    customers: Sequence[CustomerRecord],
    rng: random.Random,
) -> list[TicketRecord]:
    """Extra Billing tickets after the deployment, concentrated in one segment."""
    scenario = config.scenario
    concentrated = [
        c
        for c in customers
        if c.region is scenario.concentrated_region and c.tier is scenario.concentrated_tier
    ]
    others = [c for c in customers if c not in concentrated]
    other_weights = [config.customers.ticket_propensity[c.tier] for c in others]
    deploy = config.deployment_at
    hours = list(range(24))
    tickets: list[TicketRecord] = []

    for day_date, expected in scenario.daily_excess:
        day = datetime.combine(day_date, time(), tzinfo=config.window_start.tzinfo)
        on_deploy_day = day.date() == deploy.date()
        count = max(0, round(rng.gauss(expected, math.sqrt(expected))))
        weights = [
            0.0 if on_deploy_day and h < deploy.hour else w
            for h, w in zip(hours, config.volume.hour_weights, strict=True)
        ]
        for _ in range(count):
            hour = rng.choices(hours, weights=weights, k=1)[0]
            first_minute = (
                deploy.minute if day.date() == deploy.date() and hour == deploy.hour else 0
            )
            created_at = day + timedelta(
                hours=hour, minutes=rng.randrange(first_minute, 60), seconds=rng.randrange(60)
            )
            if rng.random() < scenario.concentration:
                customer = rng.choice(concentrated)
            else:
                customer = rng.choices(others, weights=other_weights, k=1)[0]
            tickets.append(
                _build_ticket(
                    rng,
                    config,
                    created_at=created_at,
                    customer=customer,
                    category=scenario.category,
                    product=_weighted(rng, scenario.product_weights),
                    priority=_weighted(rng, scenario.priority_weights),
                    breach_probability=scenario.breach_probability,
                    escalation_probability=scenario.escalation_probability,
                    sentiment=scenario.sentiment,
                )
            )
    return tickets


# --- 4. incident / timeline creation ----------------------------------------------


def build_deployment_event(config: DemoDataConfig) -> IncidentRecord:
    """The Billing API deployment timeline event (stored as an ``EVT-*`` incident)."""
    return IncidentRecord(
        event_type="deployment",
        title="Billing API v2.14.0 deployed",
        occurred_at=config.deployment_at,
        product=Product.BILLING_API,
        metadata={
            "synthetic": True,
            "seed_key": config.seed_key,
            "seed_version": config.seed_version,
            "service": "billing-api",
            "version": "2.14.0",
            "change_ref": "CHG-DEMO-1042",
            "summary": "Synthetic rollout of Billing API v2.14.0 (invoice rounding changes).",
        },
    )


# --- 5. ref assignment ------------------------------------------------------------


def assign_refs(tickets: Sequence[TicketRecord], prefix: str) -> tuple[TicketRecord, ...]:
    """Number tickets in (created_at, generation order) order; refuse duplicate refs."""
    ordered = sorted(tickets, key=lambda t: t.created_at)  # stable
    numbered = tuple(
        replace(ticket, ticket_ref=f"{prefix}{index:06d}")
        for index, ticket in enumerate(ordered, start=1)
    )
    seen: set[str] = set()
    for ticket in numbered:
        if ticket.ticket_ref in seen:
            raise TicketRefCollisionError(f"Duplicate ticket_ref generated: {ticket.ticket_ref}")
        seen.add(ticket.ticket_ref)
    return numbered


def generate_dataset(config: DemoDataConfig = DEFAULT_CONFIG) -> DemoDataset:
    """Generate the full dataset. Pure: identical config -> identical dataset."""
    customers = build_customers(config, _stream(config, "entities"))
    normal = generate_normal_tickets(config, customers, _stream(config, "normal"))
    excess = inject_billing_anomaly(config, customers, _stream(config, "anomaly"))
    return DemoDataset(
        teams=build_teams(),
        customers=customers,
        tickets=assign_refs([*normal, *excess], config.ticket_ref_prefix),
        incident=build_deployment_event(config),
    )
