#!/bin/sh
set -eu
mkdir -p /data/chroma
chown -R app:app /data
exec runuser -u app -- uvicorn booking_agent.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}"
