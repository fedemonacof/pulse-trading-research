# PULSE: dashboard Next.js compilata + bot Python in un'unica immagine.
#   docker build -t pulse .
#   docker run --env-file .env -p 127.0.0.1:8000:8000 -v pulse-data:/data pulse app       # command center
#   docker run --env-file .env -v pulse-data:/data pulse backtest yahoo 2                   # backtest
#   docker run --env-file .env -v pulse-data:/data pulse run                                # bot 24/7 (SCHEDULER_ENABLED=true)

FROM node:24-slim AS ui
WORKDIR /ui
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/journal.db REPORTS_DIR=/data/reports
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY desk/ desk/
COPY main.py .
COPY --from=ui /ui/out dashboard/out
RUN useradd -m pulse && mkdir -p /data && chown pulse /data
USER pulse
VOLUME /data
EXPOSE 8000
# Nel container il server deve ascoltare su tutte le interfacce: pubblica la porta solo su 127.0.0.1 (vedi sopra)
ENV PULSE_HOST=0.0.0.0
ENTRYPOINT ["python", "main.py"]
CMD ["app"]
