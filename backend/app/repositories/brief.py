"""Repository for briefs."""

from app.models.brief import Brief
from app.repositories.base import BaseRepository


class BriefRepository(BaseRepository[Brief]):
    model = Brief
