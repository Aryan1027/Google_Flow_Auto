import argparse
import asyncio
import os
from pathlib import Path
import sys
import uvicorn

from app.api.server import create_app
from app.config import load_config
from app.controller import AutomationController
from app.queue.parser import PromptParseError
from app.utils.logger import logger, setup_logger


def render_cli_status(controller: AutomationController) -> None:
    """Print clean terminal status summary matching the prompt requirements."""
    payload = controller.get_status_payload()
    summary = payload["summary"]
    state = payload["state"]
    curr = payload["current_scene"]

    print("\nGoogle Flow Auto")
    print("=" * 35)
    print("Overall Progress")
    print("━" * 35)
    print(f"{summary['completed']} / {summary['total']} scenes completed")
    print()

    print("Current")
    if curr:
        print(f"Video {curr['video_number']:02d}")
        print(f"Scene {curr['scene_number']:02d} / 06")
        print(f"Status: {curr['status']} (Retries: {curr['retry_count']})")
        print(f"Prompt: {curr['prompt']}")
    else:
        print(f"Status: {state}")
    print()

    print("Videos")
    print("─" * 35)
    groups = payload["video_groups"]
    if not groups:
        print("  (No queue loaded)")
    else:
        for g in groups:
            v_num = f"Video {g['video_number']:02d}"
            if g["is_complete"] and g["merged_file_path"]:
                status_str = "✓ Completed"
            elif g["has_failure"]:
                status_str = f"❌ Failed"
            elif g["completed_count"] > 0:
                status_str = f"⏳ {g['completed_count']}/6"
            else:
                status_str = "○ Waiting"
            print(f"{v_num:<12} {status_str}")
    print("=" * 35 + "\n")


async def run_start_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    setup_logger(config.paths.log_file)

    if args.mock:
        config.workflow.test_mode = True

    controller = AutomationController(config)

    # Optional prompt file loading
    if getattr(args, "prompts", None):
        prompt_file = Path(args.prompts)
        if not prompt_file.is_file():
            print(f"Error: Prompt file does not exist: {prompt_file}", file=sys.stderr)
            sys.exit(1)
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            controller.queue.load_prompts_from_text(content, overwrite=args.overwrite)
        except PromptParseError as e:
            print(f"Validation error loading prompts:\n{e}", file=sys.stderr)
            sys.exit(1)

    print(f"Starting Google Flow Auto in {'TEST/MOCK' if config.workflow.test_mode else 'DESKTOP'} mode...")
    await controller.start()

    # Wait for completion or interrupt
    try:
        while controller.state.value in ("RUNNING", "IDLE"):
            await asyncio.sleep(1.0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nInterrupt received. Stopping cleanly...")
        await controller.stop()

    render_cli_status(controller)


def cli() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Google Flow Auto: Reliable local video generation and concatenation utility.",
    )
    parser.add_argument("--config", "-c", type=str, default=None, help="Path to config file")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # status
    subparsers.add_parser("status", help="Show current queue and video completion status")

    # start
    start_parser = subparsers.add_parser("start", help="Start or resume video generation")
    start_parser.add_argument("--mock", action="store_true", help="Run in test/mock mode using synthetic clips")
    start_parser.add_argument("--prompts", "-p", type=str, help="Load prompt file before starting")
    start_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing queue with new prompts")

    # load-prompts
    load_parser = subparsers.add_parser("load-prompts", help="Parse and validate prompts into queue database")
    load_parser.add_argument("file", type=str, help="Text file containing 60 prompts")
    load_parser.add_argument("--overwrite", action="store_true", default=True, help="Overwrite existing queue")

    # retry
    retry_parser = subparsers.add_parser("retry", help="Reset a failed scene back to PENDING")
    retry_parser.add_argument("scene_id", type=int, help="Scene ID (1-60) to retry")

    # serve (Web UI)
    serve_parser = subparsers.add_parser("serve", help="Launch local Web UI & API server")
    serve_parser.add_argument("--host", type=str, default=None, help="Server bind host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=None, help="Server port (default: 8080)")
    serve_parser.add_argument("--lan", action="store_true", help="Bind to 0.0.0.0 for phone/LAN access")
    serve_parser.add_argument("--mock", action="store_true", help="Run web controller in test/mock mode")

    args = parser.parse_args()

    if not args.command or args.command == "status":
        config = load_config(args.config)
        controller = AutomationController(config)
        render_cli_status(controller)
        return

    if args.command == "load-prompts":
        config = load_config(args.config)
        controller = AutomationController(config)
        file_path = Path(args.file)
        if not file_path.is_file():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            scenes = controller.queue.load_prompts_from_text(content, overwrite=args.overwrite)
            print(f"Success: Loaded {len(scenes)} prompts ({len(scenes) // config.workflow.scenes_per_video} complete videos).")
            render_cli_status(controller)
        except PromptParseError as e:
            print(f"Validation Error:\n{e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.command == "retry":
        config = load_config(args.config)
        controller = AutomationController(config)
        success = controller.retry_scene(args.scene_id)
        if success:
            print(f"Scene {args.scene_id} has been reset to PENDING.")
        else:
            print(f"Error: Scene {args.scene_id} not found in queue.", file=sys.stderr)
        return

    if args.command == "start":
        asyncio.run(run_start_command(args))
        return

    if args.command == "serve":
        config = load_config(args.config)
        setup_logger(config.paths.log_file)

        if args.mock:
            config.workflow.test_mode = True

        host = args.host or ("0.0.0.0" if args.lan else config.server.host)
        port = args.port or config.server.port

        if args.lan or host == "0.0.0.0":
            print("\n" + "!" * 60)
            print("SECURITY WARNING: LAN access is enabled (0.0.0.0).")
            print("Anyone on your local Wi-Fi network can view and control this server.")
            print("Only use on trusted, password-protected private networks.")
            print("!" * 60 + "\n")

        controller = AutomationController(config)
        app = create_app(controller, config)

        print(f"Starting Google Flow Auto Web UI at http://{host}:{port}")
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli()
