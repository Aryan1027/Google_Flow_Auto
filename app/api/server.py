import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import AppConfig
from app.controller import AutomationController
from app.queue.parser import PromptParseError
from app.utils.logger import add_log_listener, get_recent_logs, remove_log_listener


class PromptsPayload(BaseModel):
    prompts_text: str
    overwrite: bool = True


def create_app(controller: AutomationController, config: AppConfig) -> FastAPI:
    app = FastAPI(title="Google Flow Auto API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    active_websockets: List[WebSocket] = []

    async def broadcast_ws_json(message: Dict[str, Any]) -> None:
        for ws in list(active_websockets):
            try:
                await ws.send_json(message)
            except Exception:
                if ws in active_websockets:
                    active_websockets.remove(ws)

    # Attach log broadcast listener to WebSocket
    def on_new_log(log_line: str) -> None:
        if active_websockets:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        broadcast_ws_json({"type": "log", "data": log_line}), loop
                    )
            except Exception:
                pass

    add_log_listener(on_new_log)

    @app.get("/api/status")
    async def get_status() -> Dict[str, Any]:
        return controller.get_status_payload()

    @app.post("/api/start")
    async def start_automation() -> Dict[str, str]:
        await controller.start()
        return {"status": "started", "state": controller.state.value}

    @app.post("/api/pause")
    async def pause_automation() -> Dict[str, str]:
        await controller.pause()
        return {"status": "pause_requested", "state": controller.state.value}

    @app.post("/api/resume")
    async def resume_automation() -> Dict[str, str]:
        await controller.resume()
        return {"status": "resumed", "state": controller.state.value}

    @app.post("/api/stop")
    async def stop_automation() -> Dict[str, str]:
        await controller.stop()
        return {"status": "stopped", "state": controller.state.value}

    @app.post("/api/retry/{scene_id}")
    async def retry_scene(scene_id: int) -> Dict[str, Any]:
        success = controller.retry_scene(scene_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found.")
        return {"status": "reset", "scene_id": scene_id}

    @app.post("/api/prompts")
    async def upload_prompts(payload: PromptsPayload) -> Dict[str, Any]:
        try:
            scenes = controller.queue.load_prompts_from_text(
                payload.prompts_text, overwrite=payload.overwrite
            )
            return {
                "status": "loaded",
                "total_prompts": len(scenes),
                "total_videos": len(scenes) // config.workflow.scenes_per_video,
            }
        except PromptParseError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/logs")
    async def get_logs() -> Dict[str, List[str]]:
        return {"logs": get_recent_logs()}

    @app.get("/api/videos/{video_number}")
    async def get_merged_video(video_number: int) -> FileResponse:
        file_path = (
            Path(config.paths.output_dir)
            / f"Video_{video_number:02d}"
            / f"Video_{video_number:02d}.mp4"
        )
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Merged video file not found.")
        return FileResponse(str(file_path), media_type="video/mp4")

    @app.get("/api/clips/{video_number}/{scene_number}")
    async def get_scene_clip(video_number: int, scene_number: int) -> FileResponse:
        file_path = (
            Path(config.paths.output_dir)
            / f"Video_{video_number:02d}"
            / f"scene_{scene_number:02d}.mp4"
        )
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Clip file not found.")
        return FileResponse(str(file_path), media_type="video/mp4")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        active_websockets.append(websocket)
        try:
            # Send initial status
            await websocket.send_json({"type": "status", "data": controller.get_status_payload()})
            while True:
                # Poll loop pushing state every second
                await asyncio.sleep(1.0)
                await websocket.send_json(
                    {"type": "status", "data": controller.get_status_payload()}
                )
        except (WebSocketDisconnect, asyncio.CancelledError):
            if websocket in active_websockets:
                active_websockets.remove(websocket)
        except Exception:
            if websocket in active_websockets:
                active_websockets.remove(websocket)

    # Mount UI static files
    static_dir = Path(__file__).parent.parent / "ui" / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
