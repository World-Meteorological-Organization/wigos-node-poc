"""The job that publishes a station's record.

Every save queues its own job, in the same transaction (django_tasks_db), with
the record as saved and whether it's announced as new (canonical) or as an
update. The job only uses what it's given: it doesn't read the station's last
publication, it undoes only what it stored itself, and it writes its outcome
without reading the previous one. Jobs of the same station take turns on a
lock. Its outcome goes to StationPublication, which the publication API reads.
They are assumed to run in the order of the saves: nothing stops an
older record published after a newer one. The status on the station is the
source of truth: a job that no longer finds its own `processing` at the end
leaves it to the newer save's job.

Retries are manual: a failure makes the station failed, and a user retries it. A
crashed job isn't run again automatically either. Its lock goes with its
database connection and a user's retry starts over."""

import atexit
import logging
from contextlib import contextmanager
from datetime import datetime

from django.db import connection, transaction
from django.tasks import task
from django.utils import timezone

from .base import Event, Operation, PublishError
from .models import StationPublication
from .publishers import get_publishers
from .wmdr2 import identity

logger = logging.getLogger("publishing")

RETRYABLE = ("pending", "processing", "failed")  # publication statuses of a Station

# First key of the two-key advisory locks, so they can't clash with any other
# use of advisory locks in this database; the second is the station id.
_LOCK_NAMESPACE = 7001

_opened = None


def opened_publishers():
    """The publishers with their transports open, once per process. Opened in
    the process's first job, so never in the web processes, which only queue."""
    global _opened
    if _opened is None:
        publishers = get_publishers()
        for publisher in publishers:
            publisher.open()
        _opened = publishers
    return _opened


@atexit.register
def close_publishers():
    """So that a message handed over just before a stop still goes out."""
    global _opened
    if _opened is not None:
        for publisher in _opened:
            publisher.close()
        _opened = None


@contextmanager
def _station_lock(station_id):
    """Held while a job runs for the station: a second job for it waits here
    until the first one ends. A Postgres advisory lock on the worker's
    connection, so it's freed when the job ends or its process dies."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s, %s)", [_LOCK_NAMESPACE, station_id])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [_LOCK_NAMESPACE, station_id])


def _event(station_id, wmdrv2, operation):
    wigos_identifier, version = identity(wmdrv2)
    return Event(
        operation=operation,
        station_id=station_id,
        wigos_identifier=wigos_identifier,
        wmdrv2=wmdrv2,
        # The WNM's pubtime: the version of the record, the same on every retry
        occurred_at=datetime.fromisoformat(version.replace("Z", "+00:00")),
    )


def _dump_delivery(delivery):
    """A receipt as saved in StationPublication.deliveries. The body isn't kept."""
    return {
        "publisher": delivery.publisher,
        "step": delivery.step,
        "name": delivery.message.name,
        "media_type": delivery.message.media_type,
        "topic": delivery.message.topic,
        "url": delivery.location.url if delivery.location else None,
    }


def _undo(publisher, event, receipts):
    """Remove what this attempt stored. If that fails too, the files stay in
    storage (no WNM announced them) and the error says so."""
    stored = [d for d in receipts if d.location]
    try:
        publisher.undo(event, stored)
    except Exception as e:
        logger.exception("Could not undo %s, left in storage: %s", publisher.name, [d.location.url for d in stored])
        return f"\nundo {publisher.name}: {e}"
    return ""


def _run_publisher(publisher, station_id, wmdrv2, operation):
    """One publisher, independent of the others. Returns (receipts as saved,
    error); a failure has no receipts."""
    event = None
    receipts = []
    done = []

    def record_step(step, so_far):
        done.append(step.name)
        receipts[:] = so_far

    try:
        event = _event(station_id, wmdrv2, operation)
        published = publisher.publish(event, on_step=record_step)
    except Exception as e:
        if not isinstance(e, PublishError):  # a bug, not an outage
            logger.exception("Publisher %s crashed on station %s", publisher.name, station_id)
        pending = (step.name for step in publisher.steps if step.name not in done)
        error = f"{publisher.name}:{next(pending, '?')}: {e}"
        if event is not None:
            error += _undo(publisher, event, receipts)
        return [], error
    return [_dump_delivery(d) for d in published], ""


def _publish(station_id, wmdrv2, operation, publishers):
    """Run the publishers and save the outcome; True if all succeeded. Only the
    given fields are written: the file links are replaced only when a publisher
    succeeded, so after a failure the page still shows those of the last
    success, without reading them."""
    results = [_run_publisher(publisher, station_id, wmdrv2, operation) for publisher in publishers]
    errors = [error for _, error in results if error]
    outcome = {"error": "\n".join(errors), "finished_at": timezone.now()}
    if len(errors) < len(results):
        outcome["deliveries"] = [d for deliveries, _ in results for d in deliveries]
    StationPublication.objects.update_or_create(station_id=station_id, defaults=outcome)
    if errors:
        logger.error("Station %s failed: %s", station_id, "; ".join(errors))
    else:
        logger.info("Published station %s", station_id)
    return not errors


def request_publication(station_id, wmdrv2):
    """Queue a job for the record, in the caller's transaction. Canonical until
    a job has stored files for the station, an update after that."""
    published = StationPublication.objects.filter(station_id=station_id).exclude(deliveries=[]).exists()
    operation = Operation.UPDATE if published else Operation.CREATE
    publish_station.enqueue(station_id, wmdrv2, operation)


class RetryRefused(Exception):
    """The station can't be retried now; the message says why."""


def retry_publication(station_id):
    """Publish the station's current record again. Also for a station left pending
    or processing, which is how one recovers from a crash. If its job is in fact
    still running, the new one waits for it and publishes again."""
    from api.models import Station

    with transaction.atomic():
        stations = Station.objects.filter(pk=station_id, publication_status__in=RETRYABLE)
        if not stations.update(publication_status=Station.PublicationStatus.PENDING):
            raise RetryRefused("its current version was already published")
        request_publication(station_id, stations.values_list("wmdrv2", flat=True).get())


@task
def publish_station(station_id, wmdrv2, operation):
    from api.models import Station

    Status = Station.PublicationStatus
    stations = Station.objects.filter(pk=station_id)
    with _station_lock(station_id):
        if not stations.update(publication_status=Status.PROCESSING):
            return  # deleted since
        published = _publish(station_id, wmdrv2, Operation(operation), opened_publishers())
        # only if still processing: otherwise a newer save's job takes over
        stations.filter(publication_status=Status.PROCESSING).update(
            publication_status=Status.PROCESSED if published else Status.FAILED
        )
