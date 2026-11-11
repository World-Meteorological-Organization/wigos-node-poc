from django.apps import AppConfig


class PublishingConfig(AppConfig):
    """Its model holds what the last job left for each station (the status is on
    Station)."""

    name = "publishing"

    def ready(self):
        from . import publishers  # noqa: F401 (registers the cache reset)
