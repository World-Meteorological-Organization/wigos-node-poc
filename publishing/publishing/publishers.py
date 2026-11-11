"""The publishers each publishing process runs for every station change, built once per
process from the options in settings. Each is one process from start to end,
and they don't depend on each other: to add a channel, write its generator
and transport and add a publisher here."""

from functools import cache

from django.conf import settings

from .base import DefaultPublisher, Step
from .generators.wmdr2 import RecordFileGenerator
from .generators.wnm import WNMGenerator
from .transports.mqtt import MQTTTransport
from .transports.s3 import S3Transport


@cache
def get_publishers():
    # WIS2, from start to end: store the record file, then announce it
    steps = [Step("storage", RecordFileGenerator(centre_id=settings.WNM_CENTRE_ID), S3Transport(**settings.WNM_STORAGE))]
    if settings.WIS2_PUBLISH_WNM:
        steps.append(Step("wnm", WNMGenerator(centre_id=settings.WNM_CENTRE_ID), MQTTTransport(**settings.WIS2_BROKER)))
    return [DefaultPublisher("wis2", steps)]
