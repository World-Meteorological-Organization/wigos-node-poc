from django.conf import settings
from django.core.checks import Error, register

from .registry import ConfigurationError, build_publishers


@register()
def check_publishers(app_configs, **kwargs):
    """settings.PUBLISHERS must build: reported at startup (runserver,
    migrate, check) instead of at the first publish."""
    try:
        build_publishers(getattr(settings, "PUBLISHERS", []))
    except ConfigurationError as e:
        return [Error(error, hint="Fix settings.PUBLISHERS.", id="publishing.E001") for error in e.errors]
    return []
