#!/usr/bin/env bash
# Останавливаем выполнение при ошибке
set -o errexit

# Устанавливаем зависимости
pip install -r requirements.txt

# Собираем статические файлы
python manage.py collectstatic --no-input

# Применяем миграции базы данных
python manage.py migrate