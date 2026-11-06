"""The publication state of the stations a user can edit, and retrying them."""

import logging

import redis
from django.db.models import F
from django.db.models.fields.json import KT
from kombu.exceptions import OperationalError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Station
from api.stations import editable_station_ids

from . import state, tasks

logger = logging.getLogger("publishing")

Status = Station.PublicationStatus


class PublicationPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


def visible_stations(user):
    """The stations the user can edit that were queued at least once, latest
    version first. Filtering and paging stay in SQL."""
    return (
        Station.objects.filter(pk__in=editable_station_ids(user))
        .exclude(publication_status="")
        .annotate(updated=KT("wmdrv2__properties__updated"))
        .select_related("last_changed_by")
        .defer("wmdrv2", "location")
        .order_by(F("updated").desc(nulls_last=True), "-id")
    )


def saved_records(stations):
    """The Valkey records of these stations. Without Valkey the list still works,
    without the error and the file links."""
    try:
        return state.load_many(station.pk for station in stations)
    except redis.RedisError:
        logger.exception("Could not read the publication records")
        return {}


def station_data(station, saved):
    """`saved` is the station's Valkey record, if there is one. The error and the
    finish time are those of the last job, which a newer save makes out of date."""
    finished = station.publication_status in (Status.PROCESSED, Status.FAILED)
    saved = saved or {}
    return {
        "station_id": station.pk,
        "wigos_identifier": station.wigos_identifier,
        "name": station.name,
        "status": station.publication_status,
        "updated": station.updated,
        # username, not get_username(), which is the email; never set for superusers
        "changed_by": station.last_changed_by.username if station.last_changed_by else None,
        "finished_at": saved.get("finished_at") if finished else None,
        "last_error": saved.get("error", "") if station.publication_status == Status.FAILED else "",
        "files": [d["url"] for d in saved.get("deliveries", []) if d["url"]],
        "can_retry": station.publication_status in tasks.RETRYABLE,
    }


class PublicationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stations = visible_stations(request.user)
        if "status" in request.query_params:
            stations = stations.filter(publication_status=request.query_params["status"])

        paginator = PublicationPagination()
        page = paginator.paginate_queryset(stations, request, view=self)
        records = saved_records(page)
        return paginator.get_paginated_response([station_data(s, records.get(s.pk)) for s in page])


class PublicationRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, station_id):
        stations = visible_stations(request.user).filter(pk=station_id)
        if not stations.exists():  # one they can't edit looks the same
            return Response({"detail": f"Station {station_id} not found"}, status=404)
        try:
            tasks.retry_publication(station_id)
        except tasks.RetryRefused as e:
            return Response({"detail": f"This station can't be retried: {e}."}, status=409)
        except (redis.RedisError, OperationalError):
            logger.exception("Could not retry station %s", station_id)
            return Response({"detail": "The publishing queue can't be reached, try again later."}, status=503)
        station = stations.get()
        return Response(station_data(station, saved_records([station]).get(station.pk)))
