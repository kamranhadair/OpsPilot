"""Configuration for the deterministic synthetic support dataset.

Everything that shapes the dataset lives here as explicit, frozen configuration.
The generator is a pure function of ``DemoDataConfig``: no wall-clock reads, no
global ``random`` state. Changing any number that alters the generated data must
be accompanied by a ``SEED_VERSION`` bump (the golden checksum test enforces it).

Window semantics: ``WINDOW_START`` is inclusive and ``WINDOW_END`` is exclusive,
so the 45 demo days run 2026-08-20 .. 2026-10-03 (UTC) inclusive.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.models.enums import (
    CustomerTier,
    Product,
    Region,
    TicketCategory,
    TicketChannel,
    TicketPriority,
)

DEMO_SEED = "opspilot-demo-seed"
SEED_KEY = "opspilot-demo"
# Bump whenever a config/generator change alters the generated dataset.
SEED_VERSION = "1"

WINDOW_START = datetime(2026, 8, 20, tzinfo=UTC)
WINDOW_END = datetime(2026, 10, 4, tzinfo=UTC)
DEPLOYMENT_AT = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)

CUSTOMER_REF_PREFIX = "DEMO-CUST-"
TICKET_REF_PREFIX = "DEMO-TCK-"

# Serialises concurrent seed/reset runs (pg_advisory_xact_lock key).
SEED_LOCK_KEY = 703_003_001


@dataclass(frozen=True)
class TeamSpec:
    team_key: str
    name: str
    category: TicketCategory


TEAMS: tuple[TeamSpec, ...] = (
    TeamSpec("billing-support", "Billing Support", TicketCategory.BILLING),
    TeamSpec("technical-support", "Technical Support", TicketCategory.TECHNICAL),
    TeamSpec("integration-support", "Integration Support", TicketCategory.INTEGRATION),
    TeamSpec("account-support", "Account Support", TicketCategory.ACCOUNT),
)


@dataclass(frozen=True)
class VolumeConfig:
    """Daily ticket volume: ~880/week with a weekday/weekend split."""

    weekday_mean: float = 150.0
    weekend_mean: float = 65.0
    daily_noise_sd: float = 0.07  # relative standard deviation
    # Relative arrival weight per UTC hour (business-hours heavy).
    hour_weights: tuple[float, ...] = (
        1, 1, 1, 1, 1, 2, 3, 5, 8, 10, 10, 9,
        8, 9, 10, 9, 8, 6, 4, 3, 2, 2, 1, 1,
    )  # fmt: skip


@dataclass(frozen=True)
class MixConfig:
    category_weights: dict[TicketCategory, float] = field(
        default_factory=lambda: {
            TicketCategory.BILLING: 0.25,
            TicketCategory.TECHNICAL: 0.40,
            TicketCategory.INTEGRATION: 0.20,
            TicketCategory.ACCOUNT: 0.15,
        }
    )
    # Category -> product affinity weights.
    product_affinity: dict[TicketCategory, dict[Product, float]] = field(
        default_factory=lambda: {
            TicketCategory.BILLING: {
                Product.BILLING_API: 0.40,
                Product.INVOICING: 0.35,
                Product.SUBSCRIPTIONS: 0.25,
            },
            TicketCategory.TECHNICAL: {
                Product.CORE_PLATFORM: 0.75,
                Product.SUBSCRIPTIONS: 0.15,
                Product.INVOICING: 0.05,
                Product.BILLING_API: 0.05,
            },
            TicketCategory.INTEGRATION: {
                Product.CORE_PLATFORM: 0.45,
                Product.BILLING_API: 0.30,
                Product.INVOICING: 0.15,
                Product.SUBSCRIPTIONS: 0.10,
            },
            TicketCategory.ACCOUNT: {
                Product.SUBSCRIPTIONS: 0.45,
                Product.CORE_PLATFORM: 0.35,
                Product.INVOICING: 0.10,
                Product.BILLING_API: 0.10,
            },
        }
    )
    channel_weights: dict[TicketChannel, float] = field(
        default_factory=lambda: {
            TicketChannel.EMAIL: 0.45,
            TicketChannel.WEB: 0.30,
            TicketChannel.CHAT: 0.15,
            TicketChannel.API: 0.10,
        }
    )


@dataclass(frozen=True)
class PriorityProfile:
    """Priority mix and SLA behaviour. SLA target = first-response minutes."""

    weights: dict[TicketPriority, float] = field(
        default_factory=lambda: {
            TicketPriority.P1: 0.03,
            TicketPriority.P2: 0.12,
            TicketPriority.P3: 0.45,
            TicketPriority.P4: 0.40,
        }
    )
    sla_target_minutes: dict[TicketPriority, int] = field(
        default_factory=lambda: {
            TicketPriority.P1: 60,
            TicketPriority.P2: 240,
            TicketPriority.P3: 480,
            TicketPriority.P4: 1440,
        }
    )
    # Baseline probability that a ticket breaches its first-response SLA (~8% overall).
    base_breach_probability: dict[TicketPriority, float] = field(
        default_factory=lambda: {
            TicketPriority.P1: 0.12,
            TicketPriority.P2: 0.10,
            TicketPriority.P3: 0.08,
            TicketPriority.P4: 0.07,
        }
    )
    # Median time from first response to resolution, before lognormal noise.
    median_resolution_minutes: dict[TicketPriority, int] = field(
        default_factory=lambda: {
            TicketPriority.P1: 240,
            TicketPriority.P2: 720,
            TicketPriority.P3: 1800,
            TicketPriority.P4: 3600,
        }
    )
    resolution_sigma: float = 0.6


@dataclass(frozen=True)
class CustomerConfig:
    """Customers per region x tier cell, and how much each tier files tickets."""

    customers_per_cell: dict[CustomerTier, int] = field(
        default_factory=lambda: {
            CustomerTier.ENTERPRISE: 4,
            CustomerTier.BUSINESS: 6,
            CustomerTier.STARTER: 8,
        }
    )
    ticket_propensity: dict[CustomerTier, float] = field(
        default_factory=lambda: {
            CustomerTier.ENTERPRISE: 3.0,
            CustomerTier.BUSINESS: 1.5,
            CustomerTier.STARTER: 0.7,
        }
    )


@dataclass(frozen=True)
class SentimentConfig:
    """Mostly neutral/positive scores with a negative tail. Range is [-1, 1]."""

    mean: float = 0.25
    sd: float = 0.30
    negative_tail_probability: float = 0.10
    tail_mean: float = -0.55
    tail_sd: float = 0.20


@dataclass(frozen=True)
class EscalationConfig:
    probability: float = 0.04


@dataclass(frozen=True)
class IncidentScenarioConfig:
    """The planted Billing anomaly that follows the Billing API deployment.

    ``daily_excess`` is the expected number of *additional* Billing tickets per UTC
    day. It ramps up after the deployment and is not damped on the weekend, so the
    final day (a Saturday) still stands clearly above its trailing 7-day baseline.
    """

    category: TicketCategory = TicketCategory.BILLING
    daily_excess: tuple[tuple[date, float], ...] = (
        (date(2026, 10, 1), 15.0),  # only from the deployment time onward
        (date(2026, 10, 2), 40.0),
        (date(2026, 10, 3), 55.0),
    )
    concentrated_region: Region = Region.EMEA
    concentrated_tier: CustomerTier = CustomerTier.ENTERPRISE
    # Share of excess tickets raised by the concentrated segment.
    concentration: float = 0.85
    product_weights: dict[Product, float] = field(
        default_factory=lambda: {
            Product.BILLING_API: 0.80,
            Product.INVOICING: 0.12,
            Product.SUBSCRIPTIONS: 0.08,
        }
    )
    priority_weights: dict[TicketPriority, float] = field(
        default_factory=lambda: {
            TicketPriority.P1: 0.05,
            TicketPriority.P2: 0.20,
            TicketPriority.P3: 0.45,
            TicketPriority.P4: 0.30,
        }
    )
    breach_probability: float = 0.25
    escalation_probability: float = 0.12
    sentiment: SentimentConfig = SentimentConfig(mean=0.0, sd=0.35, negative_tail_probability=0.40)


@dataclass(frozen=True)
class DemoDataConfig:
    seed: str = DEMO_SEED
    seed_key: str = SEED_KEY
    seed_version: str = SEED_VERSION
    window_start: datetime = WINDOW_START
    window_end: datetime = WINDOW_END
    deployment_at: datetime = DEPLOYMENT_AT
    customer_ref_prefix: str = CUSTOMER_REF_PREFIX
    ticket_ref_prefix: str = TICKET_REF_PREFIX
    volume: VolumeConfig = VolumeConfig()
    mix: MixConfig = MixConfig()
    priority: PriorityProfile = PriorityProfile()
    customers: CustomerConfig = CustomerConfig()
    sentiment: SentimentConfig = SentimentConfig()
    escalation: EscalationConfig = EscalationConfig()
    scenario: IncidentScenarioConfig = IncidentScenarioConfig()


DEFAULT_CONFIG = DemoDataConfig()
