#!/bin/sh
set -e

alembic -c db/alembic.ini upgrade head
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
