from django.contrib.auth.models import AbstractUser, Group
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models import F, Func, GeneratedField, Value
from django.db.models.fields.json import KT
from django.db.models.functions import Cast
from jsonpath_ng import parse

from .utils import update_station_geometry

wigos_identifier_expression = parse('$.id')
additional_wigos_identifier_expression = parse('$.properties.additionalIds')

class ExtractAndJoinJson(Func):
    function = 'join_jsonb_path_array'  # Matches the SQL function name exactly

# join_jsonb_path_array stores additional WSIs as ",wsi1,wsi2," (a comma can't
# appear in a WSI), so a whole WSI is matched by searching for it between
# separators rather than as a bare substring of a longer one.
ADDITIONAL_WSI_SEPARATOR = ','

def additional_wsi_lookup(wigos_identifier):
    return f"{ADDITIONAL_WSI_SEPARATOR}{wigos_identifier}{ADDITIONAL_WSI_SEPARATOR}"

class WIGOSNodeGroup(models.Model):

    # Establish the direct link to Django's Group
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='profile')

    issuer_identifier = models.IntegerField()

    def __str__(self):
        return f"{self.group.name} (Issuer ID: {self.issuer_identifier})"

class WIGOSNodeUser(AbstractUser):
    # 1. Require a unique email address
    email = models.EmailField(unique=True)

    # 2. Tell Django to use email as the login identifier
    USERNAME_FIELD = 'email'

    # 3. Specify fields prompted for when running 'createsuperuser'
    REQUIRED_FIELDS = ['username'] 

    def __str__(self):
        return self.email

class StationQuerySet(models.QuerySet):
    def with_additional_wigos_identifier(self, wigos_identifier):
        return self.filter(additional_wigos_identifiers__contains=additional_wsi_lookup(wigos_identifier))

    def check_wigos_identifier(self, wigos_identifier):
        return self.filter(wigos_identifier=wigos_identifier).exists() or self.with_additional_wigos_identifier(wigos_identifier).exists()

class Station(models.Model):
    class PublicationStatus(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        PROCESSED = "processed"  # every publisher ran (the WNM was sent, not yet confirmed)
        FAILED = "failed"

    objects = StationQuerySet.as_manager()

    wmdrv2 = models.JSONField(null=False, blank=False)

    name = GeneratedField(
        expression=Cast(
            KT("wmdrv2__properties__title"), 
            output_field=models.CharField(max_length=255)
        ),
        output_field=models.CharField(max_length=255),
        db_persist=True,
    )

    wigos_identifier = GeneratedField(
        expression=Cast(
            KT("wmdrv2__id"),
            output_field=models.CharField(max_length=255)
        ),
        output_field=models.CharField(max_length=255),
        db_persist=True,
        unique=True,
    )

    additional_wigos_identifiers = models.GeneratedField(
        expression=ExtractAndJoinJson(F('wmdrv2'), Value('$.properties.additionalIds[*]')),
        output_field=models.CharField(max_length=255),
        db_persist=True,
        db_index=True,
    )

    location = gis_models.PointField(srid=4326, null=False, blank=False)
    
    
    owner = models.ForeignKey("WIGOSNodeUser", on_delete=models.CASCADE, related_name='stations')

    # Empty for superusers and scripts, which aren't named.
    last_changed_by = models.ForeignKey(
        "WIGOSNodeUser", on_delete=models.SET_NULL, null=True, blank=True, related_name='changed_stations'
    )

    # Empty until the station is first queued for publishing.
    publication_status = models.CharField(max_length=10, choices=PublicationStatus.choices, blank=True, default="")

    def get_wigos_identifiers(self):
        wsis = []
        if self.wmdrv2:
            wsi = wigos_identifier_expression.find(self.wmdrv2)
            if wsi and len(wsi) > 0:
                wsis.append(wsi[0].value)

            for match in additional_wigos_identifier_expression.find(self.wmdrv2):
                value = match.value
                if isinstance(value, (list, tuple)):
                    wsis.extend(v for v in value if v)
                elif value:
                    wsis.append(value)

        return wsis

    def save(self, *args, **kwargs):
        """override save method to update name and location from wmdrv2 JSON data"""

        # wigos_identifier is a GeneratedField (unreadable before the row is
        # written), so derive the primary WSI from the JSON to pre-check it.
        for wsi in self.get_wigos_identifiers():
            print("checking ", wsi)
            if wsi and Station.objects.filter(wigos_identifier=wsi).exclude(pk=self.pk).exists():
                raise ValueError(f"WIGOS identifier '{wsi}' is already in use in another station")

            if wsi and Station.objects.with_additional_wigos_identifier(wsi).exclude(pk=self.pk).exists():
                raise ValueError(f"WIGOS identifier '{wsi}' is already in use in additional identifiers in another station")


        update_station_geometry(self, self.wmdrv2)

        super().save(*args, **kwargs)

    def __str__(self):
        try:
            return (
                f"{self.name} ({self.wigos_identifier}) "
                f"lat: {self.location.y} lon: {self.location.x} wmdrvs: {self.wmdrv2}"
            )
        except (AttributeError, TypeError):
            # unsaved instance: generated fields / location not available yet
            wsis = self.get_wigos_identifiers()
            return f"Station({wsis[0] if wsis else 'unsaved'})"
