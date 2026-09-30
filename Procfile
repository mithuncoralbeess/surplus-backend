web: python manage.py migrate --noinput && gunicorn config.wsgi:application --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
