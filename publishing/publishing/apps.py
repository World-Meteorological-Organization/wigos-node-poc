from django.apps import AppConfig


class PublishingConfig(AppConfig):
    """Its model holds what the last job left for each station (the status is on
    Station)."""

    name = "publishing"
