from __future__ import annotations

import ssl
from pathlib import Path
from pydantic_settings import BaseSettings

def _read_secret(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").strip()

class Settings(BaseSettings):
    # DB
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "mqtt"
    db_user: str = "mqtt"
    db_password_file: str | None = None

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password_file: str | None = None
    mqtt_client_id: str = "mqtt-recorder"

    mqtt_tls: bool = False
    mqtt_tls_insecure: bool = False  # if True, skip hostname verification (NOT recommended)
    mqtt_tls_ca_file: str | None = None
    mqtt_tls_cert_file: str | None = None
    mqtt_tls_key_file: str | None = None

    log_level: str = "INFO"

    @property
    def db_password(self) -> str:
        v = _read_secret(self.db_password_file)
        if not v:
            raise RuntimeError("DB password missing (set DB_PASSWORD_FILE to a mounted secret).")
        return v

    @property
    def mqtt_password(self) -> str | None:
        return _read_secret(self.mqtt_password_file)

    @property
    def db_url(self) -> str:
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    def mqtt_ssl_context(self) -> ssl.SSLContext | None:
        if not self.mqtt_tls:
            return None

        if not self.mqtt_tls_ca_file:
            raise RuntimeError("MQTT_TLS_CA_FILE must be set when MQTT_TLS=true")

        ctx = ssl.create_default_context(cafile=self.mqtt_tls_ca_file)

        # Optional client cert auth
        if self.mqtt_tls_cert_file and self.mqtt_tls_key_file:
            ctx.load_cert_chain(certfile=self.mqtt_tls_cert_file, keyfile=self.mqtt_tls_key_file)

        if self.mqtt_tls_insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED  # still require cert, just skip hostname check

        return ctx

settings = Settings()
