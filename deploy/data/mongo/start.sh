#!/bin/bash
set -euo pipefail
: "${MONGO_KEYFILE:?Missing internal authentication key}"
umask 077
mkdir -p /run/oldshop-mongo
chmod 755 /run/oldshop-mongo
printf '%s\n' "$MONGO_KEYFILE" > /run/oldshop-mongo/keyfile
chown mongodb:mongodb /run/oldshop-mongo/keyfile
chmod 400 /run/oldshop-mongo/keyfile
exec /usr/local/bin/docker-entrypoint.sh "$@"
