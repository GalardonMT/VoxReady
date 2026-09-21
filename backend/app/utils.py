"""Shared helpers: controlled enums, ISO-8601 formatting, UI constants."""
from datetime import datetime, timezone

LANGUAGES = ("es", "en", "pt")
ROLES = ("spokesperson", "client_admin", "master_config")
PIPELINES = ("content", "voice", "image", "fusion")
ALLOWED_RECORDING_MIME = ("video/webm", "video/mp4")

AREA_COLORS = {
    "expression": "#8B5CF6",
    "voice": "#3B82F6",
    "coherence": "#10B981",
    "empathy": "#F59E0B",
}
DEFAULT_AREA_COLOR = "#6B7280"


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (portable across DB engines)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    """Format a naive UTC datetime as ISO 8601 with trailing Z."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
