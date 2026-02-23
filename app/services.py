from __future__ import annotations
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from asyncio_mqtt import Client, MqttError
from sqlalchemy import insert, select
from .config import settings
from .db import SessionLocal
from .models import RecordingSession, MqttMessage

logger = logging.getLogger(__name__)

class RecorderService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._session_id: str | None = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()
    
    def start(self, session_id: str):
        if self.is_running():
            raise RuntimeError("Recorder already running")
        self._stop.clear()
        self._session_id = session_id
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run(session_id))


    # def start(self, session_id: str):
    #     if self.is_running():
    #         raise RuntimeError("Recorder already running")
    #     self._stop.clear()
    #     self._session_id = session_id
    #     self._task = asyncio.create_task(self._run(session_id))

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.info("Recorder task cancelled", extra={"session_id": self._session_id})
            except Exception:
                logger.exception("Recorder task failed while stopping", extra={"session_id": self._session_id})
        self._task = None
        self._session_id = None

    async def _run(self, session_id: str):
        logger.info("Recorder starting", extra={"session_id": session_id})
        # load topic filters from DB
        with SessionLocal() as db:
            sess = db.get(RecordingSession, session_id)
            if not sess:
                raise RuntimeError("Session not found")
            topic_filters = sess.topic_filters
            if not isinstance(topic_filters, list) or not topic_filters:
                raise RuntimeError("topic_filters must be a non-empty JSON list")

        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=5000)
        writer = asyncio.create_task(self._db_writer(queue))

        try:
            ssl_ctx = settings.mqtt_ssl_context()
            async with Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password,
                client_id=settings.mqtt_client_id,
                tls_context=ssl_ctx,
            ) as client:
                logger.info(
                    "Connected to MQTT broker",
                    extra={"session_id": session_id, "mqtt_host": settings.mqtt_host, "mqtt_port": settings.mqtt_port},
                )

                async with client.messages() as messages:
                    for t in topic_filters:
                        await client.subscribe(t)
                        logger.info("Subscribed topic filter", extra={"session_id": session_id, "topic_filter": t})

                    async for msg in messages:
                        if self._stop.is_set():
                            break

                        raw_payload = bytes(msg.payload)

                        # Enforce JSON storage. For binary/non-JSON payloads (including NUL bytes),
                        # store as base64 to avoid Postgres JSONB text constraints.
                        try:
                            text_payload = raw_payload.decode("utf-8")
                            if "\x00" in text_payload:
                                raise ValueError("NUL byte in UTF-8 payload")
                            payload_obj = json.loads(text_payload)
                            if not isinstance(payload_obj, (dict, list, str, int, float, bool, type(None))):
                                payload_obj = {
                                    "_raw_b64": base64.b64encode(raw_payload).decode("ascii"),
                                    "_encoding": "base64",
                                }
                        except Exception:
                            payload_obj = {
                                "_raw_b64": base64.b64encode(raw_payload).decode("ascii"),
                                "_encoding": "base64",
                            }

                        item = {
                            "session_id": session_id,
                            "ts": datetime.now(timezone.utc),
                            "topic": str(msg.topic),
                            "payload_json": payload_obj if isinstance(payload_obj, dict) else {"value": payload_obj},
                            "qos": int(msg.qos),
                            "retained": bool(getattr(msg, "retain", False)),
                        }
                        await queue.put(item)

        except MqttError as e:
            logger.exception("MQTT error in recorder", extra={"session_id": session_id, "error": str(e)})
            raise
        except asyncio.CancelledError:
            logger.info("Recorder receive loop cancelled", extra={"session_id": session_id})
            raise
        except Exception:
            logger.exception("Unexpected recorder failure", extra={"session_id": session_id})
            raise
        finally:
            await queue.put({"_flush": True})
            await writer
            logger.info("Recorder stopped", extra={"session_id": session_id})

    async def _db_writer(self, queue: asyncio.Queue[dict]):
        batch: list[dict] = []
        BATCH_SIZE = 500
        FLUSH_INTERVAL = 0.2
        loop = asyncio.get_event_loop()
        last_flush = loop.time()

        async def flush():
            nonlocal batch
            if not batch:
                return
            try:
                with SessionLocal() as db:
                    db.execute(insert(MqttMessage), batch)
                    db.commit()
                logger.info("Persisted MQTT batch", extra={"rows": len(batch)})
            except Exception:
                logger.exception("Failed to persist MQTT batch", extra={"rows": len(batch)})
                raise
            batch = []

        while True:
            item = await queue.get()
            if item.get("_flush"):
                await flush()
                return
            batch.append(item)
            now = loop.time()
            if len(batch) >= BATCH_SIZE or (now - last_flush) >= FLUSH_INTERVAL:
                await flush()
                last_flush = now


class PlaybackService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, session_id: str, speed: float = 1.0, topic_prefix: str | None = "replay/"):
        if self.is_running():
            raise RuntimeError("Playback already running")
        self._stop.clear()
        self._task = asyncio.create_task(self._run(session_id, speed, topic_prefix))

    async def stop(self):
        self._stop.set()
        if self._task:
            await self._task
        self._task = None

    async def _run(self, session_id: str, speed: float, topic_prefix: str | None):
        if speed <= 0:
            speed = 1.0

        with SessionLocal() as db:
            rows = db.execute(
                select(MqttMessage.ts, MqttMessage.topic, MqttMessage.payload_json)
                .where(MqttMessage.session_id == session_id)
                .order_by(MqttMessage.ts.asc())
            ).all()

        if not rows:
            return

        ssl_ctx = settings.mqtt_ssl_context()
        async with Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username or None,
            password=settings.mqtt_password,
            client_id=f"{settings.mqtt_client_id}-player",
            tls_context=ssl_ctx,
        ) as client:
            prev_ts = None
            for ts, topic, payload in rows:
                if self._stop.is_set():
                    return

                if prev_ts is not None:
                    delta = (ts - prev_ts).total_seconds() / speed
                    if delta > 0:
                        await asyncio.sleep(delta)

                out_topic = f"{topic_prefix}{topic}" if topic_prefix else topic
                await client.publish(out_topic, payload=json.dumps(payload).encode("utf-8"))
                prev_ts = ts
