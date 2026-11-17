#!/bin/sh
set -eu
role="${1:-web}"
shift || true

if [ "$role" = "web" ]; then
  case "${MIGRATE_ON_STARTUP:-false}" in
    1|true|yes)
      flask --app app:create_app db upgrade
      ;;
  esac
  exec gunicorn --bind "0.0.0.0:${PORT:-5000}" --workers "${WEB_WORKERS:-3}" --logger-class app.gunicorn_logging.JsonGunicornLogger 'app:create_app()'
fi

exec "$role" "$@"
