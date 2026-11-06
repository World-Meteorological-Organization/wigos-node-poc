import logging

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)

User = get_user_model()


def _user_payload(user):
    return {
        "username": user.get_username(),
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def _resolve_login_identifier(identifier):
    """The SPA login field accepts either the email (the USERNAME_FIELD) or the
    plain username; map a bare username to its email so authenticate() works."""
    if not identifier or "@" in identifier or User.USERNAME_FIELD == "username":
        return identifier
    try:
        return User.objects.get(username=identifier).get_username()
    except User.DoesNotExist:
        return identifier


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request):
    """Set the csrftoken cookie so the SPA can echo it in the X-CSRFToken header
    on subsequent unsafe (POST/PUT) requests."""
    return Response({"detail": "CSRF cookie set."})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    identifier = _resolve_login_identifier(request.data.get("username"))
    user = authenticate(request, username=identifier, password=request.data.get("password"))
    if user is None:
        return Response({"detail": "Invalid username or password."}, status=401)
    django_login(request, user)  # sets the sessionid cookie, rotates the CSRF token
    return Response(_user_payload(user))


@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):
    django_logout(request)
    return Response(status=204)


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Not authenticated."}, status=401)
    return Response(_user_payload(request.user))
