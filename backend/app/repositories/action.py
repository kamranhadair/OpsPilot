"""Repositories for proposed actions, approvals and executions (persistence only).

The state machine lives in ``services/actions/state_machine.py``.
"""

from sqlalchemy import case, select

from app.models.action import ActionExecution, Approval, ProposedAction
from app.models.brief import Brief
from app.models.enums import ActionStatus
from app.repositories.base import BaseRepository


class ActionRepository(BaseRepository[ProposedAction]):
    model = ProposedAction

    def get_for_brief(self, brief_id: int) -> ProposedAction | None:
        return self.get_by(brief_id=brief_id)

    def get_for_update(self, action_id: int) -> ProposedAction | None:
        """Lock the row so concurrent transitions on one action are serialized."""
        stmt = select(ProposedAction).where(ProposedAction.id == action_id).with_for_update()
        return self.session.execute(stmt).scalars().first()

    def get_with_brief(self, action_id: int) -> tuple[ProposedAction, Brief] | None:
        stmt = (
            select(ProposedAction, Brief)
            .join(Brief, Brief.id == ProposedAction.brief_id)
            .where(ProposedAction.id == action_id)
        )
        row = self.session.execute(stmt).first()
        return None if row is None else (row[0], row[1])

    def list_with_briefs(
        self, *, status: ActionStatus | None, limit: int, offset: int
    ) -> list[tuple[ProposedAction, Brief]]:
        """Pending approvals first, then newest first."""
        pending_first = case((ProposedAction.status == ActionStatus.PENDING_APPROVAL, 0), else_=1)
        stmt = select(ProposedAction, Brief).join(Brief, Brief.id == ProposedAction.brief_id)
        if status is not None:
            stmt = stmt.where(ProposedAction.status == status)
        stmt = (
            stmt.order_by(pending_first, ProposedAction.created_at.desc(), ProposedAction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in self.session.execute(stmt)]


class ApprovalRepository(BaseRepository[Approval]):
    model = Approval

    def get_for_action(self, action_id: int) -> Approval | None:
        return self.get_by(action_id=action_id)


class ActionExecutionRepository(BaseRepository[ActionExecution]):
    model = ActionExecution

    def get_for_action(self, action_id: int) -> ActionExecution | None:
        return self.get_by(action_id=action_id)
