import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",")

INSTALLED_APPS = [
    "api.apps.ApiConfig",
    "publishing.apps.PublishingConfig",
    "django_tasks_db",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "django.contrib.postgres",
    "guardian"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.environ.get("POSTGRES_DB", "app_db"),
        "USER": os.environ.get("POSTGRES_USER", "app_user"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "app_password"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = 'api.WIGOSNodeUser'

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# Allow the SPA to send the session cookie on cross-origin API calls (used when
# the frontend talks to :8000 directly instead of through the Vite dev proxy).
CORS_ALLOW_CREDENTIALS = True

# Origins Django trusts for unsafe (POST/PUT) requests. The Vite dev proxy keeps
# the browser on :5173 while forwarding to Django, so that origin must be listed
# or every login/write request is rejected with 403.
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# Publishing jobs are kept in the database and run by `manage.py run_publishers`
# (several `db_worker` processes).
TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}

# WIS2 publishing (repo-root publishing/, built in publishing/publishers.py):
# store each record file in web storage, then announce it with a WNM.
WNM_CENTRE_ID = os.environ.get("WNM_CENTRE_ID", "io-wis2dev-test-wigosnode")
# Options of publishing.transports.s3.S3Transport (the minio service by default)
WNM_STORAGE = {
    "endpoint": os.environ.get("WNM_STORAGE_ENDPOINT", "minio:9000"),
    "bucket": os.environ.get("WNM_STORAGE_BUCKET", "webstorage"),
    # defaults: the minio service's root user in docker-compose.yml
    "access_key": os.environ.get("WNM_STORAGE_ACCESS_KEY", "minioadmin"),
    "secret_key": os.environ.get("WNM_STORAGE_SECRET_KEY", "minioadmin"),
    "secure": os.environ.get("WNM_STORAGE_SECURE", "false").lower() == "true",
    # where the public reaches the files (the WNM links)
    "public_url": os.environ.get("WNM_STORAGE_URL", "https://wigosnode.test.wis2dev.io/webstorage"),
    # development: create the bucket with anonymous read if missing
    "create_bucket": os.environ.get("WNM_STORAGE_CREATE_BUCKET", str(DEBUG)).lower() == "true",
}
# Options of publishing.transports.mqtt.MQTTTransport; false stores the files
# but sends no WNMs
WIS2_PUBLISH_WNM = os.environ.get("WIS2_PUBLISH_WNM", "true") == "true"
WIS2_BROKER = {
    # default: the mosquitto service in docker-compose.yml
    "url": os.environ.get("WIS2_BROKER_URL", "mqtt://wis2:wis2@mosquitto:1883"),
    # Placeholder: the WMDR2 topic is not decided yet
    "topic": os.environ.get("WIS2_TOPIC", f"origin/a/wis2/{WNM_CENTRE_ID}/TBD-wmdr2"),
}

# Publishing logs to the console (docker compose logs publisher); INFO shows
# every published station and, with the log transports, every message.
PUBLISHING_LOG_LEVEL = os.environ.get("PUBLISHING_LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "publishing": {"handlers": ["console"], "level": PUBLISHING_LOG_LEVEL, "propagate": False},
    },
}

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # this is default
    'guardian.backends.ObjectPermissionBackend',
)
