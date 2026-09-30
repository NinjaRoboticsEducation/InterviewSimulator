from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from filelock import FileLock

from .config import Settings
from .doctor import diagnostics
from .files import private_directory, reject_links
from .portability import delete_run, export_state, import_state, verify_run
from .wiki import WikiAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Private local interview practice")
    parser.add_argument(
        "command",
        choices=["serve", "serve-adk", "doctor", "jobs", "backup", "restore", "delete-run", "verify-run"],
    )
    parser.add_argument("target", nargs="?", help="Archive path or run ID for backup, restore, or delete-run")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    settings = Settings.load()
    if args.command == "doctor":
        print(json.dumps(diagnostics(settings), indent=2))
    elif args.command == "jobs":
        for job in WikiAdapter(settings.wiki_root).list_opportunities():
            print(f"{job.reference}: {'ready' if job.ready else '; '.join(job.reasons)}")
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
        if not 1 <= args.port <= 65535:
            parser.error("Port must be 1–65535")
        if args.command == "serve-adk":
            private_directory(settings.state_root)
            lease_path = settings.state_root / "server.lock"
            reject_links(lease_path)
            with FileLock(lease_path, timeout=0):
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "google.adk.cli",
                        "web",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.port),
                        "--no-reload",
                        "--no_use_local_storage",
                        str(settings.root / "agents"),
                    ],
                    check=True,
                )
        else:
            import uvicorn

            uvicorn.run("interview_simulator.webapp:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
