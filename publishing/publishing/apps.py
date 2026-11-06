from django.apps import AppConfig


class PublishingConfig(AppConfig):
    """Has no models: the publication state is on Station and in Valkey. An app
    so that the check of settings.PUBLISHERS runs at startup."""

    name = "publishing"

    def ready(self):
        from . import checks, publishers  # noqa: F401 (registers the check and cache reset)
