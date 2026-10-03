"""Typed contracts for the health endpoint and the shared error body."""

from typing import Literal

from pydantic import BaseModel, Field

ComponentStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """Successful health payload."""

    status: ComponentStatus = Field(description="Overall service status.")
    service: str = Field(description="Logical service name.")
    database: ComponentStatus = Field(description="Result of the database connectivity check.")


class ErrorResponse(BaseModel):
    """Stable machine-readable error body used across the API."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")
