from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
import asyncio
from .db import SessionLocal, engine
from .models import Base, RecordingSession, MqttMessage
from .schemas import SessionCreate, SessionOut, MessageOut
from .services import RecorderService, PlaybackService

router = APIRouter()
recorder = RecorderService()
player = PlaybackService()

@router.post("/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate):
    s = RecordingSession(node=payload.node, topic_filters=payload.topic_filters)
    with SessionLocal() as db:
        db.add(s)
        db.commit()
        db.refresh(s)
    return SessionOut(id=str(s.id), state=s.state)

@router.get("/sessions", response_model=list[SessionOut])
def list_sessions():
    with SessionLocal() as db:
        rows = db.execute(select(RecordingSession).order_by(RecordingSession.created_at.desc())).scalars().all()
    return [SessionOut(id=str(r.id), state=r.state) for r in rows]

@router.post("/sessions/{session_id}/record/start")
async def start_record(session_id: str):
    with SessionLocal() as db:
        s = db.get(RecordingSession, session_id)
        if not s:
            raise HTTPException(404, "Session not found")
        s.state = "RECORDING"
        s.started_at = datetime.now(timezone.utc)
        db.commit()

    try:
        recorder.start(session_id)  # now runs in request loop context
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return {"ok": True}

@router.post("/sessions/{session_id}/record/stop")
async def stop_record(session_id: str):
    await recorder.stop()
    with SessionLocal() as db:
        s = db.get(RecordingSession, session_id)
        if s:
            s.state = "STOPPED"
            s.stopped_at = datetime.now(timezone.utc)
            db.commit()
    return {"ok": True}

@router.post("/sessions/{session_id}/play/start")
def start_play(session_id: str, speed: float = 1.0, topic_prefix: str | None = "replay/"):
    try:
        player.start(session_id, speed=speed, topic_prefix=topic_prefix)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}

@router.post("/sessions/{session_id}/play/stop")
async def stop_play(session_id: str):
    await player.stop()
    return {"ok": True}

@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: str, limit: int = 200, topic_prefix: str | None = None):
    if limit < 1 or limit > 5000:
        raise HTTPException(400, "limit must be between 1 and 5000")
    with SessionLocal() as db:
        q = select(MqttMessage).where(MqttMessage.session_id == session_id)
        if topic_prefix:
            q = q.where(MqttMessage.topic.like(f"{topic_prefix}%"))
        q = q.order_by(MqttMessage.ts.asc()).limit(limit)
        rows = db.execute(q).scalars().all()

    return [
        MessageOut(
            ts=r.ts.isoformat(),
            topic=r.topic,
            payload=r.payload_json,
            qos=r.qos,
            retained=r.retained,
        )
        for r in rows
    ]
