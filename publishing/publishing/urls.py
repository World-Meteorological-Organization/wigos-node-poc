from django.urls import path

from . import views

urlpatterns = [
    path("", views.PublicationListView.as_view(), name="publications"),
    path("<int:station_id>/retry/", views.PublicationRetryView.as_view(), name="publication-retry"),
]
