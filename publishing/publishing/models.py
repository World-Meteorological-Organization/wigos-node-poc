from django.db import models


class StationPublication(models.Model):
    """What the last job left for a station: everything apart from the status,
    which lives on the station. One row per station that has been published."""

    station = models.OneToOneField("api.Station", on_delete=models.CASCADE, primary_key=True, related_name="publication")
    deliveries = models.JSONField(default=list)  # receipts, as tasks._dump_delivery saves them
    error = models.TextField(blank=True)
    finished_at = models.DateTimeField(null=True)
