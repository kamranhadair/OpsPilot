"""Repositories for briefs, their claims and LLM call traces."""

from sqlalchemy import select

from app.models.brief import Brief, BriefClaim
from app.models.enums import BriefStatus
from app.models.observability import LLMTrace
from app.repositories.base import BaseRepository


class BriefRepository(BaseRepository[Brief]):
    model = Brief

    def add_claims(self, brief_id: int, claims: list[BriefClaim]) -> None:
        for claim in claims:
            claim.brief_id = brief_id
        self.session.add_all(claims)
        self.session.flush()

    def claims_for(self, brief_id: int) -> list[BriefClaim]:
        stmt = (
            select(BriefClaim).where(BriefClaim.brief_id == brief_id).order_by(BriefClaim.ordinal)
        )
        return list(self.session.execute(stmt).scalars())

    def get_with_claims(self, brief_id: int) -> tuple[Brief, list[BriefClaim]] | None:
        brief = self.get(brief_id)
        if brief is None:
            return None
        return brief, self.claims_for(brief_id)

    def latest(self) -> Brief | None:
        stmt = select(Brief).order_by(Brief.created_at.desc(), Brief.id.desc()).limit(1)
        return self.session.execute(stmt).scalars().first()

    def latest_with_status(self, status: BriefStatus) -> Brief | None:
        stmt = (
            select(Brief)
            .where(Brief.status == status)
            .order_by(Brief.created_at.desc(), Brief.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()


class LLMTraceRepository(BaseRepository[LLMTrace]):
    model = LLMTrace
