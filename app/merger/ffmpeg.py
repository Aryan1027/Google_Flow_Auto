import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from app.config import FFmpegConfig
from app.utils.logger import logger


class FFmpegError(Exception):
    """Raised when an FFmpeg or FFprobe operation fails."""
    pass


def probe_media(file_path: str, ffprobe_path: str = "ffprobe") -> Dict[str, Any]:
    """Inspects a media file using ffprobe and returns technical metadata."""
    if not os.path.isfile(file_path):
        raise FFmpegError(f"Media file does not exist: {file_path}")

    cmd = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,pix_fmt",
        "-show_entries", "format=duration,format_name,size",
        "-of", "json",
        file_path,
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        
        streams = data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fmt = data.get("format", {})

        return {
            "file_path": file_path,
            "duration": float(fmt.get("duration", 0.0) or 0.0),
            "video": {
                "codec": v_stream.get("codec_name") if v_stream else None,
                "width": v_stream.get("width") if v_stream else None,
                "height": v_stream.get("height") if v_stream else None,
                "fps": v_stream.get("r_frame_rate") if v_stream else None,
                "pix_fmt": v_stream.get("pix_fmt") if v_stream else None,
            },
            "audio": {
                "codec": a_stream.get("codec_name") if a_stream else None,
                "sample_rate": a_stream.get("sample_rate") if a_stream else None,
                "channels": a_stream.get("channels") if a_stream else None,
            },
        }
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"ffprobe failed for {file_path}: {e.stderr.strip()}")
    except Exception as e:
        raise FFmpegError(f"Error parsing ffprobe output for {file_path}: {str(e)}")


def are_clips_compatible_for_stream_copy(probes: List[Dict[str, Any]]) -> bool:
    """Check if all video clips share compatible codecs, resolution, and audio parameters."""
    if len(probes) <= 1:
        return True

    base_v = probes[0]["video"]
    base_a = probes[0]["audio"]

    for p in probes[1:]:
        v = p["video"]
        a = p["audio"]

        # Check video stream compatibility
        if v["codec"] != base_v["codec"]:
            return False
        if v["width"] != base_v["width"] or v["height"] != base_v["height"]:
            return False
        if v["fps"] != base_v["fps"] or v["pix_fmt"] != base_v["pix_fmt"]:
            return False

        # Check audio stream presence and compatibility
        has_a1 = base_a["codec"] is not None
        has_a2 = a["codec"] is not None
        if has_a1 != has_a2:
            return False
        if has_a1:
            if a["codec"] != base_a["codec"] or a["sample_rate"] != base_a["sample_rate"] or a["channels"] != base_a["channels"]:
                return False

    return True


class FFmpegMerger:
    """Reliable multi-clip merger using FFmpeg with stream copy and re-encode fallback."""

    def __init__(self, config: Optional[FFmpegConfig] = None):
        self.config = config or FFmpegConfig()

    def merge_video_scenes(self, clip_paths: List[str], output_path: str) -> str:
        """
        Merge a list of clip files in exact sequence into output_path.
        Maintains order: scene 1 -> scene 2 -> ... -> scene N.
        """
        if not clip_paths:
            raise FFmpegError("No clip paths provided to merge.")

        # Ensure all clips exist and have non-zero size
        probes = []
        for p in clip_paths:
            if not os.path.isfile(p):
                raise FFmpegError(f"Source clip does not exist: {p}")
            if os.path.getsize(p) == 0:
                raise FFmpegError(f"Source clip is empty (0 bytes): {p}")
            probes.append(probe_media(p, self.config.ffprobe_path))

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary concat demuxer text file
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as concat_file:
            concat_path = concat_file.name
            for p in clip_paths:
                abs_p = Path(p).resolve().as_posix()
                # Escape single quotes in concat file syntax
                safe_path = abs_p.replace("'", "'\\''")
                concat_file.write(f"file '{safe_path}'\n")

        try:
            can_stream_copy = not self.config.force_reencode and are_clips_compatible_for_stream_copy(probes)
            merge_success = False

            if can_stream_copy:
                logger.info(f"Clips are compatible. Attempting fast stream-copy merge into {out_path.name}...")
                copy_cmd = [
                    self.config.ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_path,
                    "-c", "copy",
                    str(out_path),
                ]
                res = subprocess.run(copy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                    merge_success = True
                    logger.info(f"Stream-copy merge completed successfully: {out_path.name}")
                else:
                    logger.warning(f"Stream-copy merge returned code {res.returncode}. Falling back to re-encoding...")

            if not merge_success:
                logger.info(f"Re-encoding clips for seamless concatenation into {out_path.name}...")
                # Re-encode using x264 and aac
                reencode_cmd = [
                    self.config.ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_path,
                    "-c:v", self.config.video_codec,
                    "-preset", self.config.preset,
                    "-crf", str(self.config.crf),
                    "-pix_fmt", "yuv420p",
                    "-c:a", self.config.audio_codec,
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(out_path),
                ]
                res = subprocess.run(reencode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    raise FFmpegError(f"FFmpeg re-encode merge failed: {res.stderr.strip()}")
                logger.info(f"Re-encode merge completed: {out_path.name}")

            # Verify the resulting merged file
            merged_probe = probe_media(output_path, self.config.ffprobe_path)
            total_expected_duration = sum(p["duration"] for p in probes)
            actual_duration = merged_probe["duration"]
            logger.info(
                f"Merged output verified: {output_path} (Duration: ~{actual_duration:.1f}s, "
                f"Expected: ~{total_expected_duration:.1f}s, Size: {os.path.getsize(output_path)} bytes)"
            )
            return output_path

        finally:
            if os.path.exists(concat_path):
                os.remove(concat_path)
