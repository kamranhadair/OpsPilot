"""Repository for proposed actions (persistence only; the state machine is Spec 12)."""

from app.models.action import ProposedAction
from app.repositories.base import BaseRepository


class ActionRepository(BaseRepository[ProposedAction]):
    model = ProposedAction
