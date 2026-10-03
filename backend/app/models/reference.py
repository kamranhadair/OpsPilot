"""Reference data: customers and support teams."""

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RowTimestampsMixin, str_enum
from app.models.enums import CustomerTier, Region


class Customer(RowTimestampsMixin, Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_ref: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[CustomerTier] = mapped_column(str_enum(CustomerTier, "customer_tier"))
    region: Mapped[Region] = mapped_column(str_enum(Region, "customer_region"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class SupportTeam(RowTimestampsMixin, Base):
    __tablename__ = "support_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
