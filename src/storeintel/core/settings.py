from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    sqlite_path: str = "./data/storeintel.db"

    log_level: str = "INFO"
    log_json: bool = True

    # Processor
    processor_batch_size: int = 200
    processor_frame_stride: int = 3
    processor_position_event_every_n_frames: int = 5
    processor_track_buffer_frames: int = 30

    yolo_model: str = "yolov8n.pt"
    yolo_conf: float = 0.25


def get_settings() -> Settings:
    return Settings()
