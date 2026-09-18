import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


@dataclass
class FlowConfig:
    url: str = "https://flow.google.com"
    generation_timeout: int = 300
    download_timeout: int = 120
    polling_interval: float = 2.0
    delay_between_operations: float = 3.0
    max_retries: int = 3


@dataclass
class BrowserConfig:
    headless: bool = False
    user_data_dir: str = "browser_profile"
    channel: Optional[str] = "chrome"
    cdp_endpoint: Optional[str] = None


@dataclass
class FFmpegConfig:
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    force_reencode: bool = False
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 18
    preset: str = "medium"


@dataclass
class PathsConfig:
    output_dir: str = "output"
    data_dir: str = "data"
    logs_dir: str = "logs"
    db_file: str = "data/google_flow_auto.db"
    log_file: str = "logs/google_flow_auto.log"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    lan_access: bool = False


@dataclass
class WorkflowConfig:
    scenes_per_video: int = 6
    target_videos: int = 10
    target_prompts: int = 60
    test_mode: bool = False


@dataclass
class AppConfig:
    flow: FlowConfig = field(default_factory=FlowConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    ffmpeg: FFmpegConfig = field(default_factory=FFmpegConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        return cls(
            flow=FlowConfig(**data.get("flow", {})),
            browser=BrowserConfig(**data.get("browser", {})),
            ffmpeg=FFmpegConfig(**data.get("ffmpeg", {})),
            paths=PathsConfig(**data.get("paths", {})),
            server=ServerConfig(**data.get("server", {})),
            workflow=WorkflowConfig(**data.get("workflow", {})),
        )

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        for p in [self.paths.output_dir, self.paths.data_dir, self.paths.logs_dir]:
            Path(p).mkdir(parents=True, exist_ok=True)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from file or return defaults."""
    candidates = [
        config_path,
        "config/config.yaml",
        "config/config.json",
        "config/default_config.yaml",
    ]

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    if candidate.endswith(".json"):
                        data = json.load(f)
                    else:
                        data = yaml.safe_load(f) or {}
                config = AppConfig.from_dict(data)
                config.ensure_directories()
                return config
            except Exception as e:
                print(f"Warning: Failed to parse config file {candidate}: {e}")

    default = AppConfig()
    default.ensure_directories()
    return default
