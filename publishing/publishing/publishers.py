"""The publishers configured in settings.PUBLISHERS, built once per process."""

from functools import cache

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

from .registry import build_publishers


@cache
def get_publishers():
    """Raises publishing.registry.ConfigurationError for a broken config;
    the system check (checks.py) reports the same errors at startup."""
    return build_publishers(getattr(settings, "PUBLISHERS", []))


@receiver(setting_changed)
def _reset(setting, **kwargs):
    # override_settings in tests
    if setting == "PUBLISHERS":
        get_publishers.cache_clear()
