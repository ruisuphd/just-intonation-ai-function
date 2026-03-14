from __future__ import annotations

from datetime import datetime, timezone, timedelta
from time import mktime

import feedparser

from shared.logger import get_logger
from shared.source_adapters.base import RawItem, SourceAdapter

logger = get_logger("adapter.rss")


class RSSAdapter(SourceAdapter):
    def __init__(self, feed_url: str, source_name: str):
        self.feed_url = feed_url
        self.source_name = source_name

    async def fetch_items(self) -> list[RawItem]:
        feed = feedparser.parse(self.feed_url)
        if feed.bozo and not feed.entries:
            logger.warning(
                "rss.parse_error",
                extra={"url": self.feed_url, "error": str(feed.bozo_exception)},
            )
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        items: list[RawItem] = []

        for entry in feed.entries:
            published = _parse_date(entry)
            if published and published < cutoff:
                continue

            content = ""
            if hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "content"):
                content = entry.content[0].get("value", "")

            items.append(
                RawItem(
                    source_url=entry.get("link", ""),
                    source_type="rss",
                    source_name=self.source_name,
                    title=entry.get("title", ""),
                    raw_content=content,
                    published_at=published,
                )
            )

        logger.info(
            "rss.fetched",
            extra={"url": self.feed_url, "count": len(items)},
        )
        return items


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    return None
