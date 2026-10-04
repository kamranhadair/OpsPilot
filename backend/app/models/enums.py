"""Named enums for every constrained state set in the domain model.

Columns store the string value (VARCHAR + named CHECK constraint), so adding a
value later is a constraint change rather than a PostgreSQL ``ENUM`` alteration.
"""

from enum import StrEnum


class CustomerTier(StrEnum):
    STARTER = "starter"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class Region(StrEnum):
    EMEA = "emea"
    NORTH_AMERICA = "north_america"
    APAC = "apac"


class TicketPriority(StrEnum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"


class TicketStatus(StrEnum):
    OPEN = "open"
    PENDING = "pending"
    SOLVED = "solved"
    CLOSED = "closed"


class TicketChannel(StrEnum):
    EMAIL = "email"
    WEB = "web"
    API = "api"
    CHAT = "chat"


class TicketCategory(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    INTEGRATION = "integration"
    ACCOUNT = "account"


class Product(StrEnum):
    BILLING_API = "billing_api"
    INVOICING = "invoicing"
    SUBSCRIPTIONS = "subscriptions"
    CORE_PLATFORM = "core_platform"


class AnomalySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class BriefStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"


class ClaimType(StrEnum):
    OBSERVATION = "observation"
    INFERENCE = "inference"


class ClaimValidationStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class ActionType(StrEnum):
    """V1 allow-list: ``open_investigation`` is the only executable action."""

    OPEN_INVESTIGATION = "open_investigation"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionStatus(StrEnum):
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TraceStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class LLMOperation(StrEnum):
    """Every model operation the application performs. ``llm_traces.operation`` stays a
    plain string column so a new operation needs no migration."""

    BRIEF_GENERATION = "brief_generation"
    ACTION_PROPOSAL = "action_proposal"
    CITATION_JUDGE_EVAL = "citation_judge_eval"


class ActorType(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    AI = "ai"


class EvidenceType(StrEnum):
    """Evidence kinds; the value is the externally visible ID prefix."""

    EVENT = "EVT"
    METRIC = "MTR"
    ANOMALY = "ANOM"
    SEGMENT = "SEG"
