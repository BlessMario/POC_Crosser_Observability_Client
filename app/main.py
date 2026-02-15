from fastapi import FastAPI
from .api import router
from .db import engine
from .models import Base
from .telemetry import setup_observability

app = FastAPI(title="MQTT Recorder/Playback")
app.include_router(router, prefix="/v1")

@app.on_event("startup")
def on_startup():
    setup_observability()
    # Simple bootstrap: create tables if they do not exist
    Base.metadata.create_all(bind=engine)
