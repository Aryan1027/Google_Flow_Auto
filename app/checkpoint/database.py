import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from app.queue.models import SceneItem, SceneStatus, VideoGroup, VideoStatus, get_utc_now_iso
from app.utils.logger import logger


class CheckpointDatabase:
    """SQLite-backed persistent queue and checkpoint store."""

    def __init__(self, db_path: str = "data/google_flow_auto.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency and crash resilience
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS scenes (
                    scene_id INTEGER PRIMARY KEY,
                    video_number INTEGER NOT NULL,
                    scene_number INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    file_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS videos (
                    video_number INTEGER PRIMARY KEY,
                    merged_file_path TEXT,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def save_scenes(self, scenes: List[SceneItem], overwrite: bool = False) -> None:
        """Save a batch of scenes into the queue."""
        with self._get_connection() as conn:
            if overwrite:
                conn.execute("DELETE FROM scenes")
                conn.execute("DELETE FROM videos")

            for scene in scenes:
                conn.execute(
                    """
                    INSERT INTO scenes (scene_id, video_number, scene_number, prompt, status, file_path, created_at, updated_at, retry_count, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scene_id) DO UPDATE SET
                        prompt = excluded.prompt,
                        video_number = excluded.video_number,
                        scene_number = excluded.scene_number,
                        updated_at = excluded.updated_at
                    """,
                    (
                        scene.scene_id,
                        scene.video_number,
                        scene.scene_number,
                        scene.prompt,
                        scene.status.value,
                        scene.file_path,
                        scene.created_at,
                        scene.updated_at,
                        scene.retry_count,
                        scene.error,
                    ),
                )
            conn.commit()

    def get_scene(self, scene_id: int) -> Optional[SceneItem]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)).fetchone()
            if not row:
                return None
            return SceneItem(
                scene_id=row["scene_id"],
                video_number=row["video_number"],
                scene_number=row["scene_number"],
                prompt=row["prompt"],
                status=SceneStatus(row["status"]),
                file_path=row["file_path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                retry_count=row["retry_count"],
                error=row["error"],
            )

    def get_all_scenes(self) -> List[SceneItem]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM scenes ORDER BY scene_id ASC").fetchall()
            return [
                SceneItem(
                    scene_id=row["scene_id"],
                    video_number=row["video_number"],
                    scene_number=row["scene_number"],
                    prompt=row["prompt"],
                    status=SceneStatus(row["status"]),
                    file_path=row["file_path"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    retry_count=row["retry_count"],
                    error=row["error"],
                )
                for row in rows
            ]

    def update_scene_status(
        self,
        scene_id: int,
        status: SceneStatus,
        file_path: Optional[str] = None,
        error: Optional[str] = None,
        increment_retry: bool = False,
    ) -> None:
        now = get_utc_now_iso()
        with self._get_connection() as conn:
            if increment_retry:
                conn.execute(
                    """
                    UPDATE scenes
                    SET status = ?,
                        file_path = COALESCE(?, file_path),
                        error = ?,
                        retry_count = retry_count + 1,
                        updated_at = ?
                    WHERE scene_id = ?
                    """,
                    (status.value, file_path, error, now, scene_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE scenes
                    SET status = ?,
                        file_path = COALESCE(?, file_path),
                        error = ?,
                        updated_at = ?
                    WHERE scene_id = ?
                    """,
                    (status.value, file_path, error, now, scene_id),
                )
            conn.commit()

    def reset_scene_for_retry(self, scene_id: int) -> None:
        """Reset a failed or stuck scene back to PENDING."""
        now = get_utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE scenes
                SET status = ?,
                    error = NULL,
                    updated_at = ?
                WHERE scene_id = ?
                """,
                (SceneStatus.PENDING.value, now, scene_id),
            )
            conn.commit()

    def save_video_merged(self, video_number: int, merged_file_path: str) -> None:
        now = get_utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO videos (video_number, merged_file_path, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(video_number) DO UPDATE SET
                    merged_file_path = excluded.merged_file_path,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (video_number, merged_file_path, VideoStatus.COMPLETED.value, now),
            )
            conn.commit()

    def get_video_groups(self, scenes_per_video: int = 6) -> List[VideoGroup]:
        all_scenes = self.get_all_scenes()
        if not all_scenes:
            return []

        # Load video merge records
        merged_paths: Dict[int, str] = {}
        with self._get_connection() as conn:
            rows = conn.execute("SELECT video_number, merged_file_path FROM videos").fetchall()
            for r in rows:
                merged_paths[r["video_number"]] = r["merged_file_path"]

        # Group by video_number
        groups_dict: Dict[int, List[SceneItem]] = {}
        for s in all_scenes:
            groups_dict.setdefault(s.video_number, []).append(s)

        groups = []
        for v_num in sorted(groups_dict.keys()):
            scenes = sorted(groups_dict[v_num], key=lambda x: x.scene_number)
            group = VideoGroup(
                video_number=v_num,
                scenes=scenes,
                merged_file_path=merged_paths.get(v_num),
            )
            groups.append(group)
        return groups

    def get_first_incomplete_scene(self) -> Optional[SceneItem]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM scenes
                WHERE status != ?
                ORDER BY scene_id ASC
                LIMIT 1
                """,
                (SceneStatus.COMPLETED.value,),
            ).fetchone()
            if not row:
                return None
            return SceneItem(
                scene_id=row["scene_id"],
                video_number=row["video_number"],
                scene_number=row["scene_number"],
                prompt=row["prompt"],
                status=SceneStatus(row["status"]),
                file_path=row["file_path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                retry_count=row["retry_count"],
                error=row["error"],
            )

    def perform_crash_recovery(self) -> Tuple[int, int]:
        """
        Inspects state after restart or crash:
        - Completed scenes: verifies file exists and is non-empty. If missing, reverts to PENDING.
        - In-progress scenes (GENERATING, DOWNLOADING): reverts to PENDING for safe retry.
        Returns (reverted_incomplete_count, missing_completed_count).
        """
        reverted_incomplete = 0
        missing_completed = 0
        now = get_utc_now_iso()

        with self._get_connection() as conn:
            scenes = conn.execute("SELECT * FROM scenes").fetchall()
            for row in scenes:
                s_id = row["scene_id"]
                st = SceneStatus(row["status"])
                f_path = row["file_path"]

                if st in (SceneStatus.GENERATING, SceneStatus.DOWNLOADING):
                    # Check if file was actually downloaded before crash
                    if f_path and os.path.isfile(f_path) and os.path.getsize(f_path) > 0:
                        conn.execute(
                            "UPDATE scenes SET status = ?, updated_at = ? WHERE scene_id = ?",
                            (SceneStatus.COMPLETED.value, now, s_id),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE scenes
                            SET status = ?, error = 'Recovered from interrupted session', updated_at = ?
                            WHERE scene_id = ?
                            """,
                            (SceneStatus.PENDING.value, now, s_id),
                        )
                        reverted_incomplete += 1

                elif st == SceneStatus.COMPLETED:
                    if not f_path or not os.path.isfile(f_path) or os.path.getsize(f_path) == 0:
                        # File is missing on disk
                        conn.execute(
                            """
                            UPDATE scenes
                            SET status = ?, file_path = NULL, error = 'Target video file missing from disk', updated_at = ?
                            WHERE scene_id = ?
                            """,
                            (SceneStatus.PENDING.value, now, s_id),
                        )
                        missing_completed += 1

            conn.commit()

        if reverted_incomplete > 0 or missing_completed > 0:
            logger.info(
                f"Crash recovery completed: {reverted_incomplete} in-flight scenes reset to PENDING, "
                f"{missing_completed} missing completed scenes recovered."
            )
        return reverted_incomplete, missing_completed

    def get_progress_summary(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM scenes WHERE status = ?", (SceneStatus.COMPLETED.value,)
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM scenes WHERE status = ?", (SceneStatus.FAILED.value,)
            ).fetchone()[0]
            in_progress = total - completed - failed
            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "remaining": total - completed,
                "in_progress": in_progress,
            }
