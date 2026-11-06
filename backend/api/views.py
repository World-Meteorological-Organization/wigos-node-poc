import logging
import re
from pathlib import Path

import django.http
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import (
    api_view,
)
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import stations
from .models import Station, WIGOSNodeGroup
from .renderers import CompactJSONRenderer
from .stations import StationError

logger = logging.getLogger(__name__)


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS

# Same pattern as "id" and "additionalIds" in schemas/wmdr2-bundled.json (and WIGOS_ID_PATTERN in the frontend).
def check_wigos_identifier(wigos_identifier):
    return not (wigos_identifier is None or not re.match(r'^(0|1|2|3)-([1-9][0-9]*)-([0-9]+)-([A-Za-z0-9._-]+)$', wigos_identifier))

@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


def codelist(request, scheme):
    path = Path(settings.BASE_DIR) / "api" / "codelists" / f"{scheme}.csv"
    if not path.exists():
        return django.http.HttpResponseNotFound(f"No cached codelist for '{scheme}'")
    return django.http.HttpResponse(path.read_text(encoding="utf-8"), content_type="text/csv")


@api_view(["GET"])
def hello(request):
    return Response({"message": "Hello from Django!"})


@api_view(["POST"])
def geojson(request):
    body = request.data
    if body.get("type") != "Feature" or "geometry" not in body:
        return Response({"detail": "Payload must be a GeoJSON Feature"}, status=400)
    return Response({"received": body}, status=201)


@api_view(["GET"])
def my_stations(request):
    my_stations = Station.objects.filter(wmdrv2__isnull=False) # return all stations in the meantime
    editable = stations.editable_station_ids(request.user)
    return Response([
        {
            "station_id": station.id,
            "wsi": station.wigos_identifier,
            "name": station.name,
            "latitude": station.location.y,
            "longitude": station.location.x,
            "can_edit": station.id in editable,
            "publication_status": station.publication_status if station.id in editable else None,
        }
        for station in my_stations
    ])

@api_view(["GET"])
def check_wigosidentifiers(request):
    wigos_identifiers = request.query_params.getlist("wigos_identifier")
    if len(wigos_identifiers) == 0:
        return Response({"detail": "No WIGOS identifiers provided"}, status=400)
    results = {wigos_identifier: Station.objects.check_wigos_identifier(wigos_identifier) for wigos_identifier in wigos_identifiers}
    return Response(results)

@api_view(["GET"])
def my_issuer_of_identifiers(request):
    groups = WIGOSNodeGroup.objects.filter(group__user=request.user)
    issuer_identifiers = [group.issuer_identifier for group in groups]
    return Response({"issuer_of_identifiers": issuer_identifiers})    


def _error_response(error):
    # 403s keep their historical {"error": ...} shape, everything else {"detail": ...}.
    body = {"error" if error.status == status.HTTP_403_FORBIDDEN else "detail": error.message}
    if error.errors:
        body["errors"] = error.errors
    return Response(body, status=error.status)


class Wmdrv2View(APIView):
    permission_classes = [IsAuthenticated | ReadOnly]
    # GET serves the same bytes for every client (see renderers.py)
    renderer_classes = [CompactJSONRenderer]

    def get(self, request, station_id=None):

        if station_id is None:
            return Response(
                {"error": "Station ID is required for retrieval."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            station = Station.objects.get(id=station_id)
        except Station.DoesNotExist:
            return Response({"detail": f"Station {station_id} not found"}, status=404)

        return Response(station.wmdrv2)

    def put(self, request, station_id=None):

        if station_id is None:
            return Response(
                {"error": "Station ID is required for updating."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            station = Station.objects.get(id=station_id)
        except Station.DoesNotExist:
            return Response({"detail": f"Station {station_id} not found"}, status=404)

        try:
            stations.update_station(request.user, station, request.data)
        except StationError as e:
            return _error_response(e)

        return Response({"message": f"WMDv2 data for station {station_id} updated successfully."}, status=200)

    def post(self, request, station_id=None):
        if station_id is not None:
            return Response(
                {"error": "Station ID should not be provided for creation."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            station = stations.create_station(request.user, request.data)
        except StationError as e:
            return _error_response(e)

        return Response({"message": f"Station {station.id} created successfully.", "station_id": station.id}, status=201)


class Wmdrv2ByWsiView(APIView):
    """A record by any of its WIGOS identifiers, primary or additional. Each
    record's `self` link points here with its primary identifier."""

    permission_classes = [ReadOnly]
    renderer_classes = [CompactJSONRenderer]

    def get(self, request, wsi):
        station = (
            Station.objects.filter(wigos_identifier=wsi).first()
            or Station.objects.with_additional_wigos_identifier(wsi).first()
        )
        if station is None:
            return Response({"detail": f"No station with WIGOS identifier {wsi}"}, status=404)
        return Response(station.wmdrv2)


MAX_BATCH_UPDATES = 500


def _parse_station_id(value):
    # bool is an int subclass; reject it along with anything non-integer.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


class Wmdrv2BatchView(APIView):
    """Reads and edits many existing stations at once. Never creates stations."""

    permission_classes = [IsAuthenticated | ReadOnly]

    def get(self, request):
        """?station_id=1&station_id=2 -> { "1": <wmdrv2>, "2": <wmdrv2> }.
        Unknown IDs are left out."""
        raw_ids = request.query_params.getlist("station_id")
        ids = [_parse_station_id(raw) for raw in raw_ids]
        if not ids or None in ids:
            return Response({"detail": "Provide one or more numeric station_id parameters."}, status=400)
        if len(ids) > MAX_BATCH_UPDATES:
            return Response({"detail": f"At most {MAX_BATCH_UPDATES} stations can be read at once."}, status=400)
        return Response({str(station.id): station.wmdrv2 for station in Station.objects.filter(id__in=ids)})

    def post(self, request):
        """Body: { "dry_run": bool, "updates": [{ "station_id": int, "wmdrv2": {...} }] }.

        Every update runs in its own savepoint inside one transaction: a failing
        update is rolled back alone and later updates see the earlier ones (so
        the same WIGOS ID given to two stations in one batch is caught). A dry
        run rolls everything back at the end."""
        body = request.data if isinstance(request.data, dict) else {}
        updates = body.get("updates")
        dry_run = body.get("dry_run", False)
        if not isinstance(updates, list) or not isinstance(dry_run, bool):
            return Response({"detail": "Expected { \"dry_run\": bool, \"updates\": [...] }."}, status=400)
        if len(updates) > MAX_BATCH_UPDATES:
            return Response({"detail": f"At most {MAX_BATCH_UPDATES} updates are allowed per request."}, status=400)

        results = []
        with transaction.atomic():
            for index, update in enumerate(updates):
                results.append(self._apply(request.user, index, update))
            if dry_run:
                transaction.set_rollback(True)

        summary = {"ok": sum(r["status"] == "ok" for r in results)}
        summary["error"] = len(results) - summary["ok"]
        return Response({"dry_run": dry_run, "summary": summary, "results": results})

    def _apply(self, user, index, update):
        update = update if isinstance(update, dict) else {}
        station_id = _parse_station_id(update.get("station_id"))
        wmdrv2 = update.get("wmdrv2")
        result = {"index": index, "station_id": station_id, "wsi": None}
        try:
            if station_id is None:
                raise StationError("A numeric station_id is required. Batch operations never create stations.")
            try:
                station = Station.objects.select_for_update().get(id=station_id)
            except Station.DoesNotExist:
                raise StationError(f"Station {station_id} not found.", status=404)
            result["wsi"] = station.wigos_identifier
            with transaction.atomic():  # savepoint: a failure only undoes this update
                stations.update_station(user, station, wmdrv2)
            result["wsi"] = wmdrv2.get("id")
            result["status"] = "ok"
        except StationError as e:
            result.update(status="error", message=e.message)
            if e.errors:
                result["errors"] = e.errors
        return result
