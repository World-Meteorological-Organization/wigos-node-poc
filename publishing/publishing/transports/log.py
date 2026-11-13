import logging
from urllib.parse import quote

from ..base import Location, TransportLayer

logger = logging.getLogger("publishing")


class LogTransport(TransportLayer):
    """Logs messages instead of delivering them; for development and tests.

    Options: topic (default topic, as a real transport would use it),
    max_body (characters of the body to log, default 500; 0 logs none), and
    url (base URL: when set, named messages are reported as stored at
    <url>/<name>, like a storage transport would)."""

    def __init__(self, *, topic=None, max_body=500, url=None, **options):
        super().__init__(topic=topic, max_body=max_body, url=url, **options)
        self.topic = topic
        self.max_body = max_body
        self.url = url

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
            return Location(f"{self.url.rstrip('/')}/{quote(message.name)}")
        return None

    def remove(self, location):
        logger.info("remove url=%s", location.url)
