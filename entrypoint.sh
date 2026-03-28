#!/bin/sh
set -e

echo "Checking database..."

if [ ! -f /app/data/resorts.db ]; then
    echo "No DB found in volume — copying seed database..."
    cp /app/data-seed/resorts.db /app/data/resorts.db
    echo "Seed database copied."
else
    echo "Existing database found, skipping copy."
fi

echo "Starting server..."
exec python server.py