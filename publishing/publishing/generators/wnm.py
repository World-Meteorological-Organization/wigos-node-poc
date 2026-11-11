"""WIS2 Notification Messages (WNM) announcing stored WMDR2 records.

Spec: https://wmo-im.github.io/wis2-notification-message/standard/wis2-notification-message-STABLE.html

Every version of a record is its own data granule: data_id carries the
record's WIGOS identifier and its version (properties.updated, else
properties.created). The link, integrity and content describe the bytes the
storage step stored, never a second rendering of the record."""

import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from ..base import Message, MessageGenerator, Operation, PublishError
from ..wmdr2 import MEDIA_TYPE as WMDR2_MEDIA_TYPE
from ..wmdr2 import identity

WNM_CONFORMANCE_CLASS = "http://wis.wmo.int/spec/wnm/1/conf/core"
WNM_MEDIA_TYPE = "application/geo+json"

# Link relations for a new, updated or removed record (Req 12E-12G). Exactly
# one of them appears in a notification (Req 12I).
LINK_RELATIONS = {
    Operation.CREATE: "canonical",
    Operation.UPDATE: "update",
    Operation.DELETE: "deletion",
}

# Data larger than this must not be embedded via properties.content (Req 11A)
MAX_INLINE_CONTENT_SIZE = 4096

logger = logging.getLogger("publishing")


def _rfc3339_utc(value):
    """Format a datetime or an RFC3339 string as RFC3339 in UTC (Req 7B, 10B)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wnm_geometry(wmdrv2):
    """Point or Polygon from the record, else null (Req 6B)."""
    geometry = wmdrv2.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") in ("Point", "Polygon"):
        return {"type": geometry["type"], "coordinates": geometry.get("coordinates")}
    return None


def _inline(content):
    """properties.content for a file: UTF-8 text as is, anything else base64."""
    try:
        return {"encoding": "utf-8", "value": content.decode("utf-8"), "size": len(content)}
    except UnicodeDecodeError:
        return {"encoding": "base64", "value": base64.b64encode(content).decode("ascii"), "size": len(content)}


def create_wnm(wmdrv2, operation, href, centre_id, content=None, media_type=WMDR2_MEDIA_TYPE, pubtime=None):
    """A WNM (as a dict) announcing the record `wmdrv2`, stored at `href`.

    `content` is the stored file's bytes; integrity, length and inline
    content are computed over it. A deletion carries none of them."""
    if operation not in LINK_RELATIONS:
        raise ValueError(f"Unknown operation '{operation}', expected one of {tuple(LINK_RELATIONS)}")

    wigos_identifier, version = identity(wmdrv2)
    properties = {
        "pubtime": _rfc3339_utc(pubtime or datetime.now(timezone.utc)),
        "data_id": f"wmdr2/{centre_id}/{wigos_identifier}/{version}",
        "metadata_id": wigos_identifier,
        "datetime": _rfc3339_utc(version),
    }
    link = {"href": href, "rel": LINK_RELATIONS[operation], "type": media_type}

    if operation != Operation.DELETE:
        if content is None:
            raise ValueError("A canonical or update WNM needs the stored file's content")
        properties["integrity"] = {
            "method": "sha512",
            "value": base64.b64encode(hashlib.sha512(content).digest()).decode("ascii"),
        }
        if len(content) <= MAX_INLINE_CONTENT_SIZE:
            properties["content"] = _inline(content)
        link["length"] = len(content)

    return {
        "id": str(uuid.uuid4()),
        "conformsTo": [WNM_CONFORMANCE_CLASS],
        "type": "Feature",
        "geometry": _wnm_geometry(wmdrv2),
        "properties": properties,
        "links": [link],
    }


class WNMGenerator(MessageGenerator):
    """One WNM per stored record file among the earlier deliveries.

    Options: centre_id (this node's WIS2 centre id, part of data_id),
    media_type (of the stored files to announce, default WMDR2) and
    skip_missing (default False: a create/update with no stored file raises
    PublishError; True logs a warning and announces nothing, for setups
    whose storage gives no links yet)."""

    def __init__(self, *, centre_id, media_type=WMDR2_MEDIA_TYPE, skip_missing=False, **options):
        super().__init__(centre_id=centre_id, media_type=media_type, skip_missing=skip_missing, **options)
        self.centre_id = centre_id
        self.media_type = media_type
        self.skip_missing = skip_missing

    def generate(self, event, deliveries):
        files = [d for d in deliveries if d.location and d.message.media_type == self.media_type]
        if not files:
            if event.operation == Operation.DELETE:
                return []  # nothing was announced, so nothing to retract
            problem = f"No stored {self.media_type} file to announce for station {event.station_id}"
            if self.skip_missing:
                logger.warning("%s; no WNM sent (skip_missing)", problem)
                return []
            raise PublishError(problem)
        return [
            Message(
                body=json.dumps(
                    create_wnm(
                        event.wmdrv2,
                        event.operation,
                        href=delivery.location.url,
                        centre_id=self.centre_id,
                        content=delivery.message.body,  # none needed for a deletion
                        media_type=self.media_type,
                        # the same on every retry, so receivers can drop repeats
                        # by data_id and pubtime
                        pubtime=event.occurred_at,
                    )
                ).encode("utf-8"),
                media_type=WNM_MEDIA_TYPE,
            )
            for delivery in files
        ]
