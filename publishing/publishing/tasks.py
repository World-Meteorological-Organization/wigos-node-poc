"""The job that brings a station's published record up to date.

A job only carries the station id and publishes its current record. The status
on the station is the source of truth: a save always sets it to pending, so a
job that no longer finds its own `processing` at the end knows a newer save came
in. The rest of the state is in Valkey (state.py).

Retries are manual: a failure makes the station failed, and a user retries it. A
crashed job isn't run again automatically either. Its lock expires by itself and
a user's retry starts over.

Models are imported inside the functions: this module is loaded while Celery
starts, before Django is set up."""

import logging
import time
from datetime import datetime

from celery.signals import worker_process_shutdown
from django.utils import timezone
from kombu.exceptions import OperationalError

from . import state
from .base import Event, Operation, PublishError
from .celery import app
from .publishers import get_publishers
from .wmdr2 import identity

logger = logging.getLogger("publishing")

BROKER_DOWN_WINDOW = 10  # seconds without trying to queue after a failure
RETRYABLE = ("pending", "processing", "failed")  # publication statuses of a Station

_opened = None
_broker_down_until = 0.0


def opened_publishers():
    """The publishers with their transports open, once per process. Opened in
    the process's first job, so after Celery forks it: the MQTT client's network
    thread wouldn't survive the fork."""
    global _opened
    if _opened is None:
        publishers = get_publishers()
        for publisher in publishers:
            publisher.open()
        _opened = publishers
    return _opened


@worker_process_shutdown.connect
def close_publishers(**kwargs):
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


def _remove_leftovers(publisher, event, leftovers):
    """Try again to remove what a failed undo left; returns what's still there."""
    kept = []
    for data in leftovers:
        try:
            publisher.undo(event, [state.load_delivery(data)])
        except Exception:
            logger.exception("Could not remove leftover %s", data["url"])
            kept.append(data)
    return kept


def _undo(publisher, event, receipts, previous):
    """Remove what this attempt stored, apart from files the last successful
    publication still links to. Returns (leftovers, error)."""
    kept = {d.location.url for d in previous if d.location}
    stored = [d for d in receipts if d.location and d.location.url not in kept]
    try:
        publisher.undo(event, stored)
    except Exception as e:
        logger.exception("Could not undo %s", publisher.name)
        return [state.dump_delivery(d) for d in stored], f"undo {publisher.name}: {e}"
    return [], ""


def _run_publisher(publisher, station_id, wmdrv2, saved):
    """One publisher, independent of the others. Returns (receipts as saved,
    leftovers, error); a failure keeps the receipts of its last success."""
    previous_data = [d for d in saved["deliveries"] if d["publisher"] == publisher.name]
    previous = [state.load_delivery(d) for d in previous_data]
    leftovers = [d for d in saved["leftovers"] if d["publisher"] == publisher.name]
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
        leftovers = _remove_leftovers(publisher, event, leftovers)
        published = publisher.publish(event, on_step=record_step)
    except Exception as e:
        if not isinstance(e, PublishError):  # a bug, not an outage
            logger.exception("Publisher %s crashed on station %s", publisher.name, station_id)
        pending = (step.name for step in publisher.steps if step.name not in done)
        error = f"{publisher.name}:{next(pending, '?')}: {e}"
        if event is not None:
            stranded, undo_error = _undo(publisher, event, receipts, previous)
            leftovers += stranded
            if undo_error:
                error += f"\n{undo_error}"
        return previous_data, leftovers, error
    return [state.dump_delivery(d) for d in published] or previous_data, leftovers, ""


def _publish(station_id, wmdrv2, publishers):
    """Run the publishers and save the outcome in Valkey; True if all succeeded."""
    saved = state.load(station_id)
    results = [_run_publisher(publisher, station_id, wmdrv2, saved) for publisher in publishers]
    errors = [error for _, _, error in results if error]
    state.save(
        station_id,
        {
            "deliveries": [d for deliveries, _, _ in results for d in deliveries],
            "leftovers": [d for _, leftovers, _ in results for d in leftovers],
            "error": "\n".join(errors),
            "finished_at": timezone.now().isoformat(),
        },
    )
    if errors:
        logger.error("Station %s failed: %s", station_id, "; ".join(errors))
    else:
        logger.info("Published station %s", station_id)
    return not errors


def _claim_and_publish(station_id):
    """With the station's lock held. Returns whether a newer save needs a new job."""
    from api.models import Station

    Status = Station.PublicationStatus
    stations = Station.objects.filter(pk=station_id)
    if not stations.filter(publication_status=Status.PENDING).update(publication_status=Status.PROCESSING):
        return False  # another job already covered this station
    wmdrv2 = stations.values_list("wmdrv2", flat=True).first()
    if wmdrv2 is None:
        return False  # deleted in between

    final = Status.PROCESSED if _publish(station_id, wmdrv2, opened_publishers()) else Status.FAILED
    # only if still processing: otherwise a save came in during the job
    finished = stations.filter(publication_status=Status.PROCESSING).update(publication_status=final)
    return not finished


def request_publication(station_id):
    """Queue a job for the station. If the broker can't be reached the station
    stays pending, for a user to retry, and this process doesn't try again for
    BROKER_DOWN_WINDOW, so that only the first save of a batch waits for it."""
    global _broker_down_until
    if time.monotonic() < _broker_down_until:
        logger.warning("Station %s not queued: the broker was unreachable moments ago", station_id)
        return
    try:
        publish_station.delay(station_id)
    except OperationalError:
        _broker_down_until = time.monotonic() + BROKER_DOWN_WINDOW
        logger.exception("Station %s not queued: the broker is unreachable", station_id)


class RetryRefused(Exception):
    """The station can't be retried now; the message says why."""


def retry_publication(station_id):
    """Publish the station's current record again. Also for a station left pending
    or processing, which is how one recovers from a crash or a Valkey outage.

    Refused while its lock is held: the job may still be running, and a new job
    would only stop at the lock. Unlike a save, this tells the user when the
    broker can't be reached (redis.RedisError, OperationalError)."""
    from api.models import Station

    if state.is_locked(station_id):
        raise RetryRefused("its job may still be running, try again in a few minutes")
    stations = Station.objects.filter(pk=station_id, publication_status__in=RETRYABLE)
    if not stations.update(publication_status=Station.PublicationStatus.PENDING):
        raise RetryRefused("its current version was already published")
    publish_station.delay(station_id)


@app.task
def publish_station(station_id):
    lock = state.station_lock(station_id)
    if not lock.acquire():
        return  # the running job picks up any newer save when it finishes
    try:
        newer_save = _claim_and_publish(station_id)
    finally:
        try:
            lock.release()
        except state.redis.exceptions.LockError:
            logger.warning("The lock of station %s expired during its job", station_id)
    if newer_save:
        # after releasing the lock, or this job would stop at it; the save's
        # own job may already have stopped there
        publish_station.delay(station_id)
