"""The publication status of the stations a user can edit, and publishing one
again. The status on the station is the only record of how publishing went;
the details of a failure are in the publisher's log."""

from django.db import transaction
from django.db.models import F
from django.db.models.fields.json import KT
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Station
from .stations import editable_station_ids, publish

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
        .defer("location")
        .order_by(F("updated").desc(nulls_last=True), "-id")
    )


def station_data(station):
    return {
        "station_id": station.pk,
        "wigos_identifier": station.wigos_identifier,
        "name": station.name,
        "status": station.publication_status,
        "updated": station.updated,
        # username, not get_username(), which is the email; never set for superusers
        "changed_by": station.last_changed_by.username if station.last_changed_by else None,
        # the page offers a retry only after a failure; the endpoint takes any status
        "can_retry": station.publication_status == Status.FAILED,
    }


class PublicationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stations = visible_stations(request.user).defer("wmdrv2")
        if "status" in request.query_params:
            stations = stations.filter(publication_status=request.query_params["status"])

        paginator = PublicationPagination()
        page = paginator.paginate_queryset(stations, request, view=self)
        return paginator.get_paginated_response([station_data(s) for s in page])


class PublicationRetryView(APIView):
    """Publishes the station's current record again, whatever its status, as an
    update. Publishing a record more than once does no harm. If an earlier job
    is still running, both run, and whichever finishes last writes the status."""

    permission_classes = [IsAuthenticated]

    def post(self, request, station_id):
        with transaction.atomic():
            station = visible_stations(request.user).filter(pk=station_id).first()
            if station is None:  # one they can't edit looks the same
                return Response({"detail": f"Station {station_id} not found"}, status=404)
            Station.objects.filter(pk=station.pk).update(publication_status=Status.PENDING)
            station.publication_status = Status.PENDING
            publish(station)
        return Response(station_data(station))
