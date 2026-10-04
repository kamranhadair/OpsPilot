"""Allow-listed incident fields shared by the bundle and the evidence resolver."""

from app.models import Incident

# Incident metadata is allow-listed field by field; nothing else leaves the backend.
EVENT_DETAIL_KEYS = ("service", "version", "change_ref", "summary")


def event_details(incident: Incident) -> dict[str, str]:
    metadata = incident.metadata_json
    return {key: value for key in EVENT_DETAIL_KEYS if isinstance(value := metadata.get(key), str)}
