#!/bin/sh

if [ ! -f "$DB_PATH" ]; then
    echo "Инициализация базы данных"
    cp /app/data-seed/resorts.db "$DB_PATH"
fi

python server.py
