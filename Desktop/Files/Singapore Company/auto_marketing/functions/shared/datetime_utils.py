"""Shared datetime utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def coerce_datetime(value) -> datetime | None:
    """Coerce Firestore timestamps, ISO strings, or datetime objects to aware datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_datetime"):
        converted = value.to_datetime()
        return converted if converted.tzinfo else converted.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            converted = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                converted
                if converted.tzinfo
                else converted.replace(tzinfo=timezone.utc)
            )
        except ValueError:
            return None
    return None
