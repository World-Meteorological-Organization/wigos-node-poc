"""The job that publishes a station's record.

Every save queues its own job, in the same transaction (django_tasks_db), with
the record as saved and whether it's announced as new (canonical, the save that
created the station) or as an update (every later save, and every retry). The
job only uses what it's given: it undoes only what it stored itself, and its
outcome is the station's publication status. The details of a failure go to the
log.

There are no guards: jobs of the same station can run at the same time, every
job publishes its record and writes the station's status, and the last to
finish wins, even if its record is older. WNMs of two such jobs can go out in
either order; their pubtime tells receivers which version is newer. The
station's record is always right, so a later check or sync that republishes it
fixes whatever such a race leaves wrong.

Retries are manual: a failure makes the station failed, and a user publishes it
again. That includes a job that crashed (any exception, fails_on_crash)."""

import atexit
import functools
import logging
from datetime import datetime

from django.tasks import task

from .base import Event, Operation, PublishError
from .publishers import get_publishers
from .wmdr2 import identity

logger = logging.getLogger("publishing")

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
    """One publisher, independent of the others. Returns the error, empty on
    success."""
    event = None
    receipts = []
    done = []

    def record_step(step, so_far):
        done.append(step.name)
        receipts[:] = so_far

    try:
        event = _event(station_id, wmdrv2, operation)
        publisher.publish(event, on_step=record_step)
    except Exception as e:
        if not isinstance(e, PublishError):  # a bug, not an outage
            logger.exception("Publisher %s crashed on station %s", publisher.name, station_id)
        pending = (step.name for step in publisher.steps if step.name not in done)
        error = f"{publisher.name}:{next(pending, '?')}: {e}"
        if event is not None:
            error += _undo(publisher, event, receipts)
        return error
    return ""


def _publish(station_id, wmdrv2, operation, publishers):
    """Run the publishers; True when all succeeded. Failures are logged."""
    errors = [error for publisher in publishers if (error := _run_publisher(publisher, station_id, wmdrv2, operation))]
    if errors:
        logger.error("Station %s failed: %s", station_id, "; ".join(errors))
    else:
        logger.info("Published station %s", station_id)
    return not errors


def request_publication(station_id, wmdrv2, operation):
    """Queue a job for the record, in the caller's transaction."""
    publish_station.enqueue(station_id, wmdrv2, operation)


def fails_on_crash(job):
    """Any exception in the job makes the station failed, and is raised again
    so the job is recorded as failed too."""

    @functools.wraps(job)
    def run(station_id, wmdrv2, operation):
        try:
            return job(station_id, wmdrv2, operation)
        except Exception:
            from api.models import Station

            logger.exception("The job of station %s crashed", station_id)
            Station.objects.filter(pk=station_id).update(
                publication_status=Station.PublicationStatus.FAILED
            )
            raise

    return run


@task
@fails_on_crash
def publish_station(station_id, wmdrv2, operation):
    """Publishes the record and writes the outcome to the station's status,
    whether or not a newer save replaced the record meanwhile."""
    from api.models import Station

    Status = Station.PublicationStatus
    station = Station.objects.filter(pk=station_id)
    station.update(publication_status=Status.PROCESSING)
    published = _publish(station_id, wmdrv2, Operation(operation), opened_publishers())
    station.update(publication_status=Status.PROCESSED if published else Status.FAILED)
