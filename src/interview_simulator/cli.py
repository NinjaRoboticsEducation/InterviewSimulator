from __future__ import annotations

import argparse
import json
import shutil
import wave
from pathlib import Path
from urllib.parse import urlsplit

from filelock import FileLock

from .config import Settings
from .doctor import diagnostics
from .files import private_directory, reject_links
from .portability import clear_history, delete_run, export_state, import_state, recover_report, verify_run
from .wiki import WikiAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Private local interview practice")
    parser.add_argument(
        "command",
        choices=[
            "serve",
            "serve-adk",
            "local-server",
            "voice-test",
            "transcribe",
            "doctor",
            "jobs",
            "backup",
            "restore",
            "delete-run",
            "clear-history",
            "verify-run",
            "report-allowance",
            "report-revision",
        ],
    )
    parser.add_argument(
        "target", nargs="?", help="Archive path, audio file, or run ID for the selected command"
    )
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm the selected history removal or report recovery operation",
    )
    parser.add_argument("--locale", choices=["en", "ja", "zh-Hant"], default="en")
    parser.add_argument(
        "--context-tokens", type=int, default=4096, help="local-server: explicit context size, 4096–16384"
    )
    parser.add_argument(
        "--gpu-layers",
        type=int,
        default=0,
        help="local-server: CPU by default; use a supported GPU deliberately",
    )
    parser.add_argument(
        "--allow-cloud-text",
        action="store_true",
        help="Permit configured cloud text tasks for ADK Web or report revision; audio stays local",
    )
    args = parser.parse_args()
    settings = Settings.load()
    if args.command == "local-server":
        binary = shutil.which("llama-server")
        if not binary or not settings.model_path or not settings.model_path.is_file():
            parser.error("Install llama-server and configure INTERVIEW_SIMULATOR_GGUF in this copy's .env")
        endpoint = urlsplit(settings.model_url)
        port = args.port if args.port is not None else endpoint.port
        assert port is not None
        if not 1 <= port <= 65535:
            parser.error("Port must be 1–65535")
        if not 4096 <= args.context_tokens <= 16384:
            parser.error("Context size must be 4096–16384 tokens")
        from .processes import serve_native

        serve_native(
            [
                binary,
                "-m",
                str(settings.model_path),
                "-c",
                str(args.context_tokens),
                "--host",
                endpoint.hostname or "127.0.0.1",
                "--port",
                str(port),
                "-ngl",
                str(args.gpu_layers),
                "-t",
                "6",
                "--alias",
                settings.model_name,
                "--api-key",
                settings.model_api_key,
            ],
        )
    elif args.command in {"voice-test", "transcribe"}:
        from .speech import Speech

        if not args.target:
            parser.error("Provide an output WAV path for voice-test or input audio path for transcribe")
        path = Path(args.target).expanduser().resolve()
        reject_links(path)
        if args.command == "transcribe":
            if path.stat().st_size > 20_000_000:
                parser.error("Audio is limited to 20 MB")
            print(Speech().transcribe(path.read_bytes(), args.locale))
        else:
            if path.exists():
                parser.error("Choose a new output file; existing audio is never overwritten")
            text = {
                "en": "Welcome. Please introduce yourself.",
                "ja": "ようこそ。自己紹介をお願いします。",
                "zh-Hant": "歡迎，請先自我介紹。",
            }[args.locale]
            data = Speech().speak(text, args.locale)
            with path.open("xb") as file:
                file.write(data)
            with wave.open(str(path), "rb") as audio:
                print(f"Local voice sample: {path}; {audio.getnframes() / audio.getframerate():.1f} seconds")
    elif args.command == "doctor":
        print(json.dumps(diagnostics(settings), indent=2))
    elif args.command == "jobs":
        for job in WikiAdapter(settings.wiki_root).list_opportunities():
            print(f"{job.reference}: {'ready' if job.ready else '; '.join(job.reasons)}")
    elif args.command in {"report-allowance", "report-revision"}:
        if not args.target or not args.confirm:
            parser.error("Specify a run ID and --confirm; stop simulator servers first")
        print(
            json.dumps(
                recover_report(
                    settings,
                    args.target,
                    revise=args.command == "report-revision",
                    cloud_consent=args.allow_cloud_text,
                )
            )
        )
    elif args.command == "clear-history":
        if not args.confirm:
            parser.error(
                "clear-history removes interviews, reports, learned questions and history backups. Stop the server and add --confirm."
            )
        print(json.dumps(clear_history(settings)))
    elif args.command in {"backup", "restore", "delete-run", "verify-run"}:
        if not args.target:
            parser.error(f"{args.command} requires a target")
        if args.command == "backup":
            print(export_state(settings, Path(args.target).expanduser()))
        elif args.command == "restore":
            import_state(settings, Path(args.target).expanduser())
            print("Restored simulator state")
        elif args.command == "delete-run":
            delete_run(settings, args.target)
            print(f"Deleted {args.target}")
        else:
            print(json.dumps(verify_run(settings, args.target), indent=2))
    else:
        args.port = args.port if args.port is not None else 8765
        if not 1 <= args.port <= 65535:
            parser.error("Port must be 1–65535")
        if args.command == "serve-adk":
            private_directory(settings.state_root)
            lease_path = settings.state_root / "server.lock"
            reject_links(lease_path)
            with FileLock(lease_path, timeout=0):
                from .adk_server import serve
                from .storage import Store

                Store(settings.state_root / "question-bank.sqlite").recover_interrupted()
                serve(settings, args.port, args.allow_cloud_text)
        else:
            import uvicorn

            uvicorn.run(
                "interview_simulator.webapp:app",
                host="127.0.0.1",
                port=args.port,
                timeout_graceful_shutdown=5,
            )


if __name__ == "__main__":
    main()
