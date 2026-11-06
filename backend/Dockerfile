FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc libgdal-dev gdal-bin  postgresql-client python3-gdal\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=publishing requirements.txt /tmp/publishing-requirements.txt
RUN pip install --no-cache-dir -r /tmp/publishing-requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

# The publishing plugins live outside backend/ (repo-root publishing/), passed
# in as the "publishing" build context by docker-compose.yml.
COPY --from=publishing . /publishing
ENV PYTHONPATH=/publishing

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
