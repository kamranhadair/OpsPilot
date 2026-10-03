"""Support tickets.

``created_at`` is the ticket *event* timestamp supplied by the caller, not a
row-creation default, so it has no server default and tickets have no
``updated_at``.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, str_enum
from app.models.enums import (
    Product,
    TicketCategory,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("sentiment_score >= -1 AND sentiment_score <= 1", name="sentiment_range"),
        CheckConstraint("resolved_at IS NULL OR resolved_at >= created_at", name="resolved_order"),
        CheckConstraint(
            "first_response_minutes IS NULL OR first_response_minutes >= 0",
            name="first_response_nonneg",
        ),
        CheckConstraint(
            "resolution_minutes IS NULL OR resolution_minutes >= 0", name="resolution_nonneg"
        ),
        CheckConstraint("sla_target_minutes > 0", name="sla_target_positive"),
        Index("ix_tickets_created_at", "created_at"),
        Index("ix_tickets_category_created_at", "category", "created_at"),
        Index("ix_tickets_product_created_at", "product", "created_at"),
        Index("ix_tickets_customer_id_created_at", "customer_id", "created_at"),
        Index("ix_tickets_support_team_id_created_at", "support_team_id", "created_at"),
        Index("ix_tickets_sla_breached_created_at", "sla_breached", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_ref: Mapped[str] = mapped_column(String(64), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    support_team_id: Mapped[int] = mapped_column(
        ForeignKey("support_teams.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    priority: Mapped[TicketPriority] = mapped_column(str_enum(TicketPriority, "ticket_priority"))
    status: Mapped[TicketStatus] = mapped_column(str_enum(TicketStatus, "ticket_status"))
    channel: Mapped[TicketChannel] = mapped_column(str_enum(TicketChannel, "ticket_channel"))
    category: Mapped[TicketCategory] = mapped_column(str_enum(TicketCategory, "ticket_category"))
    product: Mapped[Product] = mapped_column(str_enum(Product, "ticket_product"))
    first_response_minutes: Mapped[int | None] = mapped_column(Integer)
    resolution_minutes: Mapped[int | None] = mapped_column(Integer)
    sla_target_minutes: Mapped[int] = mapped_column(Integer)
    sla_breached: Mapped[bool] = mapped_column(Boolean, server_default=false())
    sentiment_score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    escalated: Mapped[bool] = mapped_column(Boolean, server_default=false())
    subject: Mapped[str | None] = mapped_column(String(200))
