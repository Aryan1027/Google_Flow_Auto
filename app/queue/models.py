from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SceneStatus(str, Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    DOWNLOADING = "DOWNLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VideoStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SceneItem:
    scene_id: int
    video_number: int
    scene_number: int
    prompt: str
    status: SceneStatus = SceneStatus.PENDING
    file_path: Optional[str] = None
    created_at: str = field(default_factory=get_utc_now_iso)
    updated_at: str = field(default_factory=get_utc_now_iso)
    retry_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneItem":
        data_copy = dict(data)
        if isinstance(data_copy.get("status"), str):
            data_copy["status"] = SceneStatus(data_copy["status"])
        return cls(**data_copy)


@dataclass
class VideoGroup:
    video_number: int
    scenes: List[SceneItem] = field(default_factory=list)
    merged_file_path: Optional[str] = None

    @property
    def total_scenes(self) -> int:
        return len(self.scenes)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.COMPLETED)

    @property
    def is_complete(self) -> bool:
        return len(self.scenes) > 0 and all(s.status == SceneStatus.COMPLETED for s in self.scenes)

    @property
    def has_failure(self) -> bool:
        return any(s.status == SceneStatus.FAILED for s in self.scenes)

    @property
    def status(self) -> VideoStatus:
        if self.is_complete and self.merged_file_path:
            return VideoStatus.COMPLETED
        if self.has_failure:
            return VideoStatus.FAILED
        if any(s.status != SceneStatus.PENDING for s in self.scenes):
            return VideoStatus.IN_PROGRESS
        return VideoStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_number": self.video_number,
            "status": self.status.value,
            "total_scenes": self.total_scenes,
            "completed_count": self.completed_count,
            "is_complete": self.is_complete,
            "has_failure": self.has_failure,
            "merged_file_path": self.merged_file_path,
            "scenes": [s.to_dict() for s in self.scenes],
        }
