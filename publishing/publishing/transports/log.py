import logging
from urllib.parse import quote

from ..base import Location, TransportLayer

logger = logging.getLogger("publishing")


class LogTransport(TransportLayer):
    """Logs messages instead of delivering them; for development and tests.

    Options: topic (default topic, as a real transport would use it),
    max_body (characters of the body to log, default 500; 0 logs none), and
    url / internal_url (base URLs: when set, named messages are reported as
    stored at <url>/<name>, like a storage transport would)."""

    def __init__(self, *, topic=None, max_body=500, url=None, internal_url=None, **options):
        super().__init__(topic=topic, max_body=max_body, url=url, internal_url=internal_url, **options)
        self.topic = topic
        self.max_body = max_body
        self.url = url
        self.internal_url = internal_url

    def send(self, message):
        body = message.body.decode("utf-8", errors="replace")
        if len(body) > self.max_body:
            body = body[: self.max_body] + "..."
        logger.info(
            "publish name=%s topic=%s type=%s size=%d %s",
            message.name,
            message.topic or self.topic,
            message.media_type,
            len(message.body),
            body,
        )
        if self.url and message.name:
            name = quote(message.name)
            internal_url = f"{self.internal_url.rstrip('/')}/{name}" if self.internal_url else None
            return Location(f"{self.url.rstrip('/')}/{name}", internal_url)
        return None

    def remove(self, location):
        logger.info("remove url=%s", location.url)
