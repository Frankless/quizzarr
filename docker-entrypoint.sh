#!/bin/sh
# Quizzarr starts as root only to hand the /config folder over to the
# PUID:PGID user (1000:1000 by default), then drops root privileges.
set -e
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
mkdir -p "${CONFIG_DIR:-/config}"

if [ "$(id -u)" = "0" ]; then
  chown -R "$PUID:$PGID" "${CONFIG_DIR:-/config}" 2>/dev/null \
    || echo "Attention : impossible de donner ${CONFIG_DIR:-/config} à $PUID:$PGID"
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
  fi
  echo "Attention : setpriv introuvable, Quizzarr tourne en root"
fi
exec "$@"
