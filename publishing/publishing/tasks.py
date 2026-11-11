"""The job that brings a station's published record up to date.

Every save queues its own job, in the same transaction (django_tasks_db), with
the record as saved; the job publishes that record. Jobs of the same station
take turns on its lock (state.py). They are assumed to run in the order of the
saves: nothing stops an older record published after a newer one. The status
on the station is the source of truth: a job that no longer finds its own
`processing` at the end leaves it to the newer save's job.

Retries are manual: a failure makes the station failed, and a user retries it. A
crashed job isn't run again automatically either. Its lock goes with its
database connection and a user's retry starts over."""

import atexit
import logging
from datetime import datetime

from django.db import transaction
from django.tasks import task
from django.utils import timezone

from . import state
from .base import Event, Operation, PublishError
from .publishers import get_publishers
from .wmdr2 import identity

logger = logging.getLogger("publishing")

RETRYABLE = ("pending", "processing", "failed")  # publication statuses of a Station

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


def _undo(publisher, event, receipts, previous):
    """Remove what this attempt stored, apart from files the last successful
    publication still links to. If that fails too, the files stay in storage
    (no WNM announced them) and the error says so."""
    kept = {d.location.url for d in previous if d.location}
    stored = [d for d in receipts if d.location and d.location.url not in kept]
    try:
        publisher.undo(event, stored)
    except Exception as e:
        logger.exception("Could not undo %s, left in storage: %s", publisher.name, [d.location.url for d in stored])
        return f"\nundo {publisher.name}: {e}"
    return ""


def _run_publisher(publisher, station_id, wmdrv2, saved):
    """One publisher, independent of the others. Returns (receipts as saved,
    error); a failure keeps the receipts of its last success."""
    previous_data = [d for d in saved["deliveries"] if d["publisher"] == publisher.name]
    previous = [state.load_delivery(d) for d in previous_data]
    # never published through this publisher: canonical, not update
    operation = Operation.UPDATE if previous else Operation.CREATE

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
            error += _undo(publisher, event, receipts, previous)
        return previous_data, error
    return [state.dump_delivery(d) for d in published] or previous_data, ""


def _publish(station_id, wmdrv2, publishers):
    """Run the publishers and save the outcome; True if all succeeded."""
    saved = state.load(station_id)
    results = [_run_publisher(publisher, station_id, wmdrv2, saved) for publisher in publishers]
    errors = [error for _, error in results if error]
    state.save(
        station_id,
        {
            "deliveries": [d for deliveries, _ in results for d in deliveries],
            "error": "\n".join(errors),
            "finished_at": timezone.now(),
        },
    )
    if errors:
        logger.error("Station %s failed: %s", station_id, "; ".join(errors))
    else:
        logger.info("Published station %s", station_id)
    return not errors


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
        publish_station.enqueue(station_id, stations.values_list("wmdrv2", flat=True).get())


@task
def publish_station(station_id, wmdrv2):
    from api.models import Station

    Status = Station.PublicationStatus
    stations = Station.objects.filter(pk=station_id)
    with state.station_lock(station_id):
        if not stations.update(publication_status=Status.PROCESSING):
            return  # deleted since
        final = Status.PROCESSED if _publish(station_id, wmdrv2, opened_publishers()) else Status.FAILED
        # only if still processing: otherwise a newer save's job takes over
        stations.filter(publication_status=Status.PROCESSING).update(publication_status=final)
