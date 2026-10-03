"""Typed provenance for metric snapshots and the deterministic analysis signature.

Provenance is structured data, never a free-text explanation: a reviewer can see
the source, formula, windows, filters, daily baseline breakdown, and samples.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.services.metrics.definitions import (
    Aggregation,
    BaselineMethod,
    Cohort,
    Dimension,
    MetricDefinition,
    MetricUnit,
)
from app.services.metrics.engine import AnalysisWindow, MetricResult, WindowValue
from app.services.metrics.queries import SOURCE_JOINS, SOURCE_TABLE

PROVENANCE_SCHEMA_VERSION: Literal[1] = 1

_TIME_COLUMNS: Mapping[Cohort, tuple[str, ...]] = {
    Cohort.CREATED_IN_WINDOW: ("created_at",),
    Cohort.RESOLVED_IN_WINDOW: ("resolved_at",),
    Cohort.OPEN_AT_WINDOW_END: ("created_at", "resolved_at"),
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceProvenance(_Frozen):
    table: str
    joins: list[str]
    cohort: Cohort
    time_columns: list[str]


class DefinitionProvenance(_Frozen):
    key: str
    version: int
    unit: MetricUnit
    aggregation: Aggregation
    formula: str
    numerator: str
    denominator: str | None


class WindowProvenance(_Frozen):
    start: AwareDatetime
    end: AwareDatetime


class DailyWindowProvenance(_Frozen):
    start: AwareDatetime
    end: AwareDatetime
    value: float | None
    numerator: int
    denominator: int | None
    sample_size: int


class BaselineProvenance(_Frozen):
    start: AwareDatetime
    end: AwareDatetime
    method: BaselineMethod
    days: list[DailyWindowProvenance]


class SampleProvenance(_Frozen):
    current_sample_size: int
    current_numerator: int
    current_denominator: int | None
    baseline_sample_size: int
    min_required: int | None
    sufficient: bool


class ProvenanceFlags(_Frozen):
    baseline_zero: bool
    baseline_empty: bool


class MetricProvenance(_Frozen):
    schema_version: Literal[1] = PROVENANCE_SCHEMA_VERSION
    signature: str
    source: SourceProvenance
    definition: DefinitionProvenance
    current_window: WindowProvenance
    baseline: BaselineProvenance
    filters: dict[str, str]
    sample: SampleProvenance
    flags: ProvenanceFlags
    computed_at: AwareDatetime


def canonical_filters(filters: Mapping[Dimension, str]) -> dict[str, str]:
    return {str(dimension): value for dimension, value in sorted(filters.items())}


def analysis_signature(
    definition: MetricDefinition, window: AnalysisWindow, filters: Mapping[Dimension, str]
) -> str:
    """sha256 of the canonical analysis inputs; identical inputs -> identical signature."""
    payload = {
        "metric_key": definition.key,
        "definition_version": definition.version,
        "window_start": window.current.start.isoformat(),
        "window_end": window.current.end.isoformat(),
        "baseline_start": window.baseline.start.isoformat(),
        "baseline_end": window.baseline.end.isoformat(),
        "filters": canonical_filters(filters),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _as_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _daily(day: WindowValue, start: datetime, end: datetime) -> DailyWindowProvenance:
    return DailyWindowProvenance(
        start=start,
        end=end,
        value=_as_float(day.value),
        numerator=day.numerator,
        denominator=day.denominator,
        sample_size=day.sample_size,
    )


def build_provenance(
    result: MetricResult, signature: str, computed_at: datetime
) -> MetricProvenance:
    definition, window = result.definition, result.window
    return MetricProvenance(
        signature=signature,
        source=SourceProvenance(
            table=SOURCE_TABLE,
            joins=list(SOURCE_JOINS),
            cohort=definition.cohort,
            time_columns=list(_TIME_COLUMNS[definition.cohort]),
        ),
        definition=DefinitionProvenance(
            key=definition.key,
            version=definition.version,
            unit=definition.unit,
            aggregation=definition.aggregation,
            formula=definition.formula,
            numerator=definition.numerator,
            denominator=definition.denominator,
        ),
        current_window=WindowProvenance(start=window.current.start, end=window.current.end),
        baseline=BaselineProvenance(
            start=window.baseline.start,
            end=window.baseline.end,
            method=definition.baseline_method,
            days=[
                _daily(day, span.start, span.end)
                for day, span in zip(result.baseline_days, window.baseline_days, strict=True)
            ],
        ),
        filters=canonical_filters(result.filters),
        sample=SampleProvenance(
            current_sample_size=result.current.sample_size,
            current_numerator=result.current.numerator,
            current_denominator=result.current.denominator,
            baseline_sample_size=result.baseline_sample_size,
            min_required=definition.min_sample_size,
            sufficient=result.sample_sufficient,
        ),
        flags=ProvenanceFlags(
            baseline_zero=result.baseline_zero, baseline_empty=result.baseline_empty
        ),
        computed_at=computed_at,
    )
