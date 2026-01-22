#!/bin/bash
set -e
echo "Starting Horilla HR..."
# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
# Parse DATABASE_URL using Python (same logic as Django settings)
if [ -n "$DATABASE_URL" ]; then
    DB_HOST=$(python -c "from urllib.parse import urlparse; print(urlparse('$DATABASE_URL').hostname)")
    DB_PORT=$(python -c "from urllib.parse import urlparse; p=urlparse('$DATABASE_URL'); print(p.port if p.port else 5432)")
    echo "Connecting to database at $DB_HOST:$DB_PORT"
    while ! nc -z "$DB_HOST" "$DB_PORT"; do
        sleep 0.1
    done
else
    # Fallback to individual environment variables (for local development)
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    echo "Connecting to database at $DB_HOST:$DB_PORT"
    while ! nc -z "$DB_HOST" "$DB_PORT"; do
        sleep 0.1
    done
fi
echo "PostgreSQL is ready!"
# Run migrations
python manage.py makemigrations
python manage.py migrate --noinput
# Collect static files
python manage.py collectstatic --noinput
echo "Starting server..."
exec "$@"