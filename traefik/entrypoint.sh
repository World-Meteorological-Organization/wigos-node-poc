#!/bin/sh
# Starts Traefik for WIGOS_NODE_URL.
#   https://host  everything on 443, with a Let's Encrypt certificate for host;
#                 80 only answers the ACME challenge and redirects to https.
#   http://host   everything on 80, no TLS.
# Routes (host only, so it must match the URL):
#   /api, /static          backend (Django; /admin isn't routed)
#   /mqtt                  mosquitto's WebSocket listener
#   /data/... (GET, HEAD)  the WNM_STORAGE_BUCKET bucket on minio, read-only
#   everything else        frontend (Vite)
set -eu

url="${WIGOS_NODE_URL:-http://localhost}"
scheme="${url%%://*}"
host="${url#*://}"
host="${host%%/*}"
host="${host%%:*}"
bucket="${WNM_STORAGE_BUCKET:-webstorage}"

# readtimeout 0: long-lived WebSockets (MQTT, Vite's reload) aren't cut off
case "$scheme" in
  https)
    entrypoint=websecure
    set -- \
      --entrypoints.web.address=:80 \
      --entrypoints.web.http.redirections.entrypoint.to=websecure \
      --entrypoints.web.http.redirections.entrypoint.scheme=https \
      --entrypoints.websecure.address=:443 \
      --entrypoints.websecure.transport.respondingtimeouts.readtimeout=0s \
      --entrypoints.websecure.http.tls.certresolver=letsencrypt \
      --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json \
      --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
    if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
      set -- "$@" --certificatesresolvers.letsencrypt.acme.email="$LETSENCRYPT_EMAIL"
    fi
    ;;
  http)
    entrypoint=web
    set -- \
      --entrypoints.web.address=:80 \
      --entrypoints.web.transport.respondingtimeouts.readtimeout=0s
    ;;
  *)
    echo "WIGOS_NODE_URL must start with http:// or https://, got: $url" >&2
    exit 1
    ;;
esac

mkdir -p /etc/traefik
cat > /etc/traefik/routes.yml <<EOF
http:
  routers:
    frontend:
      rule: "Host(\`$host\`)"
      entryPoints: [$entrypoint]
      service: frontend
    backend:
      rule: "Host(\`$host\`) && (PathPrefix(\`/api\`) || PathPrefix(\`/static\`))"
      entryPoints: [$entrypoint]
      service: backend
    mqtt:
      rule: "Host(\`$host\`) && PathPrefix(\`/mqtt\`)"
      entryPoints: [$entrypoint]
      service: mqtt
    data:
      rule: "Host(\`$host\`) && PathPrefix(\`/data/\`) && (Method(\`GET\`) || Method(\`HEAD\`))"
      entryPoints: [$entrypoint]
      middlewares: [data-to-bucket]
      service: minio
  middlewares:
    data-to-bucket:
      replacePathRegex:
        regex: "^/data/(.*)"
        replacement: "/$bucket/\$1"
  services:
    frontend:
      loadBalancer:
        servers: [{url: "http://frontend:5173"}]
    backend:
      loadBalancer:
        servers: [{url: "http://backend:8000"}]
    mqtt:
      loadBalancer:
        servers: [{url: "http://mosquitto:8884"}]
    minio:
      loadBalancer:
        servers: [{url: "http://minio:9000"}]
EOF

echo "Serving $scheme://$host on entrypoint $entrypoint"
exec traefik --providers.file.filename=/etc/traefik/routes.yml "$@"
