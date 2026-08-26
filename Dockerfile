# One image, used by both the web service and the SLA ticker.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite lives on a mounted volume; the app user must own it.
RUN useradd --create-home --uid 10001 relief \
    && mkdir -p /app/data /app/staticfiles \
    && chown -R relief:relief /app
USER relief

RUN python manage.py collectstatic --noinput

EXPOSE 8000

# One worker, four threads. SQLite serialises writes; more workers only buy
# "database is locked". Move to Postgres before adding workers.
CMD ["sh", "-c", "python manage.py migrate --noinput && \
     gunicorn config.wsgi:application \
     --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 60 --access-logfile -"]
