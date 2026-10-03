"""Developer/demo inspection of the bundle the model would receive."""

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.evidence import EvidenceBundle
from app.services.evidence.assembler import EvidenceBundleAssembler
from app.services.evidence.errors import EvidenceInspectionDisabledError


class EvidenceBundleService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.settings = settings
        self.assembler = EvidenceBundleAssembler(
            session, event_lookback_hours=settings.evidence_event_lookback_hours
        )

    def latest(self) -> EvidenceBundle:
        """The current bundle; only available in demo/development configuration.

        Raises:
            EvidenceInspectionDisabledError: outside a demo environment.
        """
        if not self.settings.is_demo_environment:
            raise EvidenceInspectionDisabledError(
                "Evidence bundle inspection is disabled outside demo environments."
            )
        return self.assembler.assemble(None)
