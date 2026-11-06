#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py populate_codelists

exec "$@"
