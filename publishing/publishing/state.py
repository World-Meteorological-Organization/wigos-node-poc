"""The publication state of each station apart from its status, which lives on the
station: the per-station lock and what the last job left (StationPublication)."""

from contextlib import contextmanager

from django.db import connection

from .base import Delivery, Location, Message
from .models import StationPublication

# First key of the two-key advisory locks, so they can't clash with any other
# use of advisory locks in this database; the second is the station id.
LOCK_NAMESPACE = 7001


@contextmanager
def station_lock(station_id):
    """Held while a job runs for the station: a second job for it waits here
    until the first one ends. A Postgres advisory lock on the worker's
    connection, so it's freed when the job ends or its process dies."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s, %s)", [LOCK_NAMESPACE, station_id])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [LOCK_NAMESPACE, station_id])


def _as_record(publication):
    if publication is None:
        return {"deliveries": [], "error": "", "finished_at": None}
    return {
        "deliveries": publication.deliveries,
        "error": publication.error,
        "finished_at": publication.finished_at.isoformat() if publication.finished_at else None,
    }


def load(station_id):
    """{"deliveries": [...], "error": str, "finished_at": str | None}"""
    return _as_record(StationPublication.objects.filter(station_id=station_id).first())


def load_many(station_ids):
    """{station_id: its record, as load() returns it}, in one query."""
    station_ids = list(station_ids)
    found = StationPublication.objects.in_bulk(station_ids)
    return {station_id: _as_record(found.get(station_id)) for station_id in station_ids}


def save(station_id, record):
    StationPublication.objects.update_or_create(station_id=station_id, defaults=record)


def dump_delivery(delivery):
    """A receipt as saved. The body isn't kept."""
    location = delivery.location
    return {
        "publisher": delivery.publisher,
        "step": delivery.step,
        "name": delivery.message.name,
        "media_type": delivery.message.media_type,
        "topic": delivery.message.topic,
        "url": location.url if location else None,
    }


def load_delivery(data):
    return Delivery(
        publisher=data["publisher"],
        message=Message(body=None, media_type=data["media_type"], name=data["name"], topic=data["topic"]),
        location=Location(data["url"]) if data["url"] else None,
        step=data["step"],
    )
