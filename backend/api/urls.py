from django.urls import include, path

from . import auth, views
from .views import Wmdrv2BatchView, Wmdrv2ByWsiView, Wmdrv2View

urlpatterns = [
    path("health/", views.health, name="health"),
    path("hello/", views.hello, name="hello"),
    path("geojson/", views.geojson, name="geojson"),
    path("codelists/<str:scheme>.csv", views.codelist, name="codelist"),
    path("my_stations/", views.my_stations, name="my_stations"),
    path("wmdrv2/batch/", Wmdrv2BatchView.as_view(), name="wmdrv2-batch"), # GET and POST, before wmdrv2/<int:station_id>
    path("wmdrv2/wsi/<str:wsi>", Wmdrv2ByWsiView.as_view(), name="wmdrv2-wsi"), # GET
    path("wmdrv2/",  Wmdrv2View.as_view() , name="wmdrv2"), # POST
    path("wmdrv2/<int:station_id>",  Wmdrv2View.as_view() , name="wmdrv2"), # GET and PUT
    path("my_issuer_of_identifiers/", views.my_issuer_of_identifiers, name="my_issuer_of_identifiers"),
    path('check_wigosidentifiers/', views.check_wigosidentifiers, name='check_wigosidentifiers'),
    # JSON auth endpoints for the SPA (the DRF HTML login stays at auth/ below)
    path("csrf/", auth.csrf, name="auth-csrf"),
    path("login/", auth.login, name="auth-login"),
    path("logout/", auth.logout, name="auth-logout"),
    path("whoami/", auth.me, name="auth-me"),
    path("auth/", include("rest_framework.urls", namespace="rest_framework")),
]
