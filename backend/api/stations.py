"""Rules shared by every endpoint that creates or changes a station: schema
validation, the per-issuer group check and object permissions. The single
station endpoints (views.Wmdrv2View) and the batch endpoint
(views.Wmdrv2BatchView) both go through here, so they can't drift apart."""

import json
import logging
from functools import cache
from pathlib import Path

from django.db import IntegrityError, transaction
from guardian.shortcuts import assign_perm, get_objects_for_user
from jsonschema import Draft202012Validator

from publishing.tasks import publish_station

from .models import Station, WIGOSNodeGroup

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "wmdr2-bundled.json"


class StationError(Exception):
    """A station couldn't be created or changed. `status` is the HTTP status the
    single-station endpoints answer with; `errors` lists schema failures."""

    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.errors = errors or []


@cache
def _validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Format checking matches ajv-formats on the frontend.
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _error_path(error):
    return "/" + "/".join(str(part) for part in error.absolute_path)


def validation_errors(wmdrv2):
    """JSON Schema errors for a WMDR2 record, e.g.
    "/properties/observations/0: 'configurations' is a required property".
    Empty when the record is valid."""
    errors = sorted(_validator().iter_errors(wmdrv2), key=lambda e: list(map(str, e.absolute_path)))
    return [f"{_error_path(error)}: {error.message}" for error in errors]


def validate(wmdrv2):
    if not isinstance(wmdrv2, dict):
        raise StationError("The record must be a JSON object.")
    errors = validation_errors(wmdrv2)
    if errors:
        raise StationError("The record is not valid against the WMDR2 schema.", errors=errors)


def issuer_of(wsi):
    parts = wsi.split("-")
    return parts[1] if len(parts) > 1 else wsi


def wsis_of(wmdrv2):
    """Primary and additional WIGOS identifiers of a record."""
    return Station(wmdrv2=wmdrv2).get_wigos_identifiers()


def user_issuers(user):
    """Issuers of identifiers the user may manage, as strings (e.g. {"756"})."""
    if not user.is_authenticated:
        return set()
    return {str(i) for i in WIGOSNodeGroup.objects.filter(group__user=user).values_list("issuer_identifier", flat=True)}


def check_issuers(user, wsis, action, issuers=None):
    """The user must be in a group for every issuer of identifier in `wsis`.
    Superusers bypass the check (Django convention)."""
    if user.is_superuser:
        return
    issuers = user_issuers(user) if issuers is None else issuers
    for issuer_id in dict.fromkeys(issuer_of(wsi) for wsi in wsis):
        if issuer_id not in issuers:
            raise StationError(
                f"You do not have permission to {action} a station for the issuer of identifier {issuer_id}.",
                status=403,
            )


def editable_station_ids(user):
    """IDs of the stations the user may change, by the same rules as
    update_station (object permission plus the issuer check on the stored
    identifiers)."""
    if not user.is_authenticated:
        return set()
    # Object permissions only, like user.has_perm('change_station', station):
    # issuer groups also hold the global change_station permission.
    stations = get_objects_for_user(user, "api.change_station", klass=Station, accept_global_perms=False)
    if user.is_superuser:
        return set(stations.values_list("id", flat=True))
    issuers = user_issuers(user)
    editable = set()
    for station in stations.only("id", "wmdrv2"):
        try:
            check_issuers(user, station.get_wigos_identifiers(), "update", issuers)
        except StationError:
            continue
        editable.add(station.id)
    return editable


def assign_issuer_groups(station, wsis):
    """Lets the groups of every issuer in `wsis` change the station."""
    for issuer_id in dict.fromkeys(issuer_of(wsi) for wsi in wsis):
        node_groups = WIGOSNodeGroup.objects.filter(issuer_identifier=issuer_id) if issuer_id.isdigit() else []
        if not node_groups:
            logger.warning(f"No group found for issuer_identifier {issuer_id}. Station {station.id} will not be assigned to any group for this WSI.")
        for node_group in node_groups:
            assign_perm("change_station", node_group.group, station)


def _mark_changed(station, user):
    """Who changed the station, and that this version isn't published yet. Saved
    with the record."""
    station.last_changed_by = None if user.is_superuser else user  # superusers aren't named
    station.publication_status = Station.PublicationStatus.PENDING


def _save(station):
    try:
        station.save()
    except ValueError as e:
        raise StationError(str(e)) from e
    except IntegrityError as e:
        raise StationError(f"The station could not be saved: {e}") from e


def _publish(station):
    """Queue the station's job, with the record as saved, in the same
    transaction as the change: the job is a row in the database, so a rolled
    back batch update or dry run queues nothing, and a saved change always has
    its job."""
    publish_station.enqueue(station.pk, station.wmdrv2)


@transaction.atomic
def create_station(user, wmdrv2):
    validate(wmdrv2)
    wsis = wsis_of(wmdrv2)
    check_issuers(user, wsis, "create")
    station = Station(wmdrv2=wmdrv2, owner=user)
    _mark_changed(station, user)
    _save(station)
    # after save so the station has a pk to attach object permissions to
    assign_perm("change_station", user, station)
    assign_issuer_groups(station, wsis)
    _publish(station)
    return station


@transaction.atomic
def update_station(user, station, wmdrv2):
    if not user.has_perm("change_station", station):
        raise StationError("You do not have permission to change this station.", status=403)
    validate(wmdrv2)
    old_wsis = station.get_wigos_identifiers()
    new_wsis = wsis_of(wmdrv2)
    # Old and new: the primary and additional IDs may both change.
    check_issuers(user, old_wsis + new_wsis, "update")
    station.wmdrv2 = wmdrv2  # save() updates the index fields
    _mark_changed(station, user)
    _save(station)  # owner is unchanged on update
    added = [wsi for wsi in new_wsis if issuer_of(wsi) not in {issuer_of(old) for old in old_wsis}]
    assign_issuer_groups(station, added)
    _publish(station)
    return station
