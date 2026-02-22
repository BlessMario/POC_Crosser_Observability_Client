# MQTT Recorder + Playback (FastAPI) with optional HiveMQ broker (Docker)

This project records MQTT messages into Postgres and can replay them with original timing.
It supports:
- JSON payload storage (Postgres JSONB)
- Time-based playback with speed factor and topic rewrite
- Configurable MQTT TLS + client certificates (enabled in prod, disabled in dev by default)
- Local dev broker container (HiveMQ CE) for debug/testing

## Quick start (DEV: includes HiveMQ, no TLS)
1) Put passwords into:
- `secrets/postgres_password.txt`
- `secrets/mqtt_password.txt` (for dev broker, optional — HiveMQ CE default allows anonymous unless configured)

2) Run:
```bash
docker compose -f docker-compose.dev.yml up --build
```

3) Open API docs:
- http://localhost:8000/docs

4) Open local recorder logs (host):
- `logs/otel.log`

## Production-like run (PROD: external broker + TLS)
- Provide broker endpoint and mount certs (see `docker-compose.prod.yml` and `.env.prod.example`).
```bash
docker compose -f docker-compose.prod.yml up --build
```

## Endpoints (examples)
Create a session:
```bash
curl -X POST "http://localhost:8000/v1/sessions" \
  -H "Content-Type: application/json" \
  -d '{"node":"node1","topic_filters":["telemetry/#","plant/+/status/#"]}'
```

Start recording:
```bash
curl -X POST "http://localhost:8000/v1/sessions/<SESSION_ID>/record/start"
```

Stop recording:
```bash
curl -X POST "http://localhost:8000/v1/sessions/<SESSION_ID>/record/stop"
```

List messages:
```bash
curl "http://localhost:8000/v1/sessions/<SESSION_ID>/messages?limit=50"
```

Start playback (replay/ prefix, 2x speed):
```bash
curl -X POST "http://localhost:8000/v1/sessions/<SESSION_ID>/play/start?speed=2.0&topic_prefix=replay/"
```

Stop playback:
```bash
curl -X POST "http://localhost:8000/v1/sessions/<SESSION_ID>/play/stop"
```

## Notes
- DEV defaults to **no MQTT TLS** (MQTT_TLS=false).
- PROD defaults to **MQTT TLS enabled** (MQTT_TLS=true) with CA + client cert/key files.
- For simplicity, DB tables are created automatically on startup (no migrations required).

## OpenTelemetry local log file
- The API now writes OpenTelemetry-based logs to `OTEL_LOG_FILE` (default `/app/logs/otel.log`).
- In dev compose, `./logs` on host is mounted to `/app/logs` in the API container.
- Use this file to debug recorder flow (`Recorder starting`, `Subscribed topic filter`, `Persisted MQTT batch`, DB errors).

## Troubleshooting: session is created but no messages in DB
If `/v1/sessions/{id}` exists but `/v1/sessions/{id}/messages` is empty:

1) Verify recorder is running:
```bash
curl -X POST "http://localhost:8000/v1/sessions/<SESSION_ID>/record/start"
```

2) Publish a test message to a subscribed topic filter.

3) Stop recorder and query messages:
```bash
curl -X POST "http://localhost:8000/v1/sessions/<SESSION_ID>/record/stop"
curl "http://localhost:8000/v1/sessions/<SESSION_ID>/messages?limit=50"
```

4) Check `logs/otel.log` for these events:
- `Connected to MQTT broker`
- `Subscribed topic filter`
- `Persisted MQTT batch`

5) If `Persisted MQTT batch` is missing, inspect nearby `ERROR` records in `logs/otel.log`.
