#!/bin/sh
# Writes .env from .env.example for a deployment: asks for the public URL and
# the Let's Encrypt email, and generates new random passwords and keys for
# everything. Refuses to overwrite an existing .env: the database and MinIO
# keep the passwords they were first started with.
set -eu
cd "$(dirname "$0")"

if [ -e .env ]; then
  echo ".env already exists; remove it first to generate new keys" >&2
  exit 1
fi

while :; do
  printf "Public URL of the node (https://... for Let's Encrypt, http://... for plain HTTP): "
  read -r url
  case "$url" in
    http://?*|https://?*) break ;;
    *) echo "It must start with http:// or https://, e.g. https://node.example.org" ;;
  esac
done

email=""
case "$url" in
  https://*)
    printf "Email for Let's Encrypt notices (optional, Enter to skip): "
    read -r email
    ;;
esac

random() {
  if command -v openssl > /dev/null; then
    openssl rand -hex 24
  else
    head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# KEY=value in .env, replacing the example's line (commented out or not)
set_env() {
  sed -i "s|^#\? \?$1=.*|$1=$2|" .env
}

postgres_password=$(random)
minio_password=$(random)
mqtt_password=$(random)
mqtt_user=$(sed -n 's/^MQTT_USERNAME=//p' .env.example)

cp .env.example .env
set_env WIGOS_NODE_URL "${url%/}"
[ -n "$email" ] && set_env LETSENCRYPT_EMAIL "$email"
set_env POSTGRES_PASSWORD "$postgres_password"
set_env DJANGO_SECRET_KEY "$(random)$(random)"
set_env MINIO_ROOT_PASSWORD "$minio_password"
set_env WNM_STORAGE_SECRET_KEY "$minio_password"
set_env MQTT_PASSWORD "$mqtt_password"
set_env WIS2_BROKER_URL "mqtt://$mqtt_user:$mqtt_password@mosquitto:1883"
chmod 600 .env

echo "Wrote .env for ${url%/} with new passwords and keys."
echo "Still to do: change the passwords of the users the migrations create (admin, test_user1)."
