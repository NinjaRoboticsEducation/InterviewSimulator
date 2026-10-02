"""Guided setup. Standard library only; model downloads are pinned and checked."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def safe_path(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Setup does not overwrite or follow symbolic links")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def permitted_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.port in {None, 443}
        and (host == "huggingface.co" or host.endswith((".huggingface.co", ".hf.co")))
    )


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not permitted_url(newurl):
            raise ValueError("Download redirected to an unapproved host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(root: Path, asset: dict) -> Path:
    target = root / asset["path"]
    if not target.resolve().is_relative_to(root.resolve()) or not permitted_url(asset["url"]):
        raise ValueError("Unsafe download manifest")
    safe_path(target)
    if target.exists():
        if digest(target) != asset["sha256"]:
            raise ValueError(
                f"Existing {target.name} does not match the manifest. Move it aside; setup will not overwrite it."
            )
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    safe_path(partial)
    if partial.is_file() and digest(partial) == asset["sha256"]:
        partial.replace(target)
        return target
    offset = partial.stat().st_size if partial.exists() else 0
    if offset >= asset["maximum_bytes"]:
        raise ValueError("Partial download exceeds its expected maximum; move it aside and retry")
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    request = Request(asset["url"], headers=headers)
    opener = build_opener(ProxyHandler({}), SafeRedirect())
    with opener.open(request, timeout=60) as response:
        resumed = response.status == 206 and offset > 0
        if resumed and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise ValueError("Download server returned the wrong resume position")
        total = offset if resumed else 0
        with partial.open("ab" if resumed else "wb") as file:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > asset["maximum_bytes"]:
                    raise ValueError("Download exceeds its expected maximum")
                file.write(block)
            file.flush()
            os.fsync(file.fileno())
    if digest(partial) != asset["sha256"]:
        partial.unlink()
        raise ValueError("Model checksum failed. The invalid download was discarded; retry.")
    partial.replace(target)
    return target


def commands(profile: str, system: str, root: Path = ROOT) -> tuple[list[str], list[list[str]]]:
    tools = ["llama-server"] if profile.startswith("local") else []
    if "voice" in profile:
        tools += ["ffmpeg", "whisper-cli"]
    installs = []
    if system == "Darwin":
        formulas = [
            name
            for tool, name in [
                ("llama-server", "llama.cpp"),
                ("ffmpeg", "ffmpeg"),
                ("whisper-cli", "whisper.cpp"),
            ]
            if tool in tools and not shutil.which(tool)
        ]
        if formulas:
            installs.append(["brew", "install", *formulas])
    elif system == "Linux" and "ffmpeg" in tools and not shutil.which("ffmpeg"):
        installs.append(["sudo", "apt-get", "install", "ffmpeg", "git", "cmake", "build-essential"])
    return tools, installs


def run(command: list[str], root: Path) -> None:
    environment = dict(os.environ)
    environment.pop("VIRTUAL_ENV", None)  # nested projects must use their own environment
    subprocess.run(command, cwd=root, env=environment, check=True)  # no shell interpolation


def build_native(root: Path, tool: str, source: dict) -> None:
    if not all(shutil.which(program) for program in ["git", "cmake"]):
        raise ValueError("Install Git, CMake, and a C++ compiler before building local inference tools")
    folder = root / ".native" / tool
    safe_path(folder)
    if not folder.exists():
        run(
            ["git", "clone", "--depth", "1", "--branch", source["ref"], source["repository"], str(folder)],
            root,
        )
    # Fail if an earlier/user-provided source checkout disagrees with the requested pin.
    actual = subprocess.check_output(
        ["git", "describe", "--tags", "--exact-match"], cwd=folder, text=True
    ).strip()
    if actual != source["ref"]:
        raise ValueError("Native source checkout does not match the pinned release")
    run(["cmake", "-S", str(folder), "-B", str(folder / "build"), "-DCMAKE_BUILD_TYPE=Release"], root)
    run(
        [
            "cmake",
            "--build",
            str(folder / "build"),
            "--config",
            "Release",
            "--parallel",
            "2",
            "--target",
            source["target"],
        ],
        root,
    )
    bins = [folder / "build/bin", folder / "build/bin/Release"]
    os.environ["PATH"] = os.pathsep.join(str(p) for p in bins) + os.pathsep + os.environ.get("PATH", "")


def prepare_environment(project: Path, backup_root: Path) -> Path | None:
    """Copied environments have absolute entry-point paths; retain and replace them."""
    environment = project / ".venv"
    safe_path(environment)
    if not environment.exists():
        return None
    marker = environment / ".interview-project.json"
    safe_path(marker)
    expected = {"project": str(project.resolve()), "system": platform.system(), "machine": platform.machine()}
    if marker.exists():
        matches = json.loads(marker.read_text()) == expected
    else:
        matches = False
        for activation in (environment / "bin/activate", environment / "Scripts/activate"):
            if not activation.is_file():
                continue
            safe_path(activation)
            match = re.search(r"^VIRTUAL_ENV=(.+)$", activation.read_text(encoding="utf-8"), re.MULTILINE)
            if match:
                value = shlex.split(match[1])
                matches = len(value) == 1 and Path(value[0]).resolve() == environment.resolve()
            break
    if matches:
        return None
    safe_path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = backup_root / (project.name + "-" + uuid.uuid4().hex)
    environment.rename(destination)
    print("Retained copied environment at " + str(destination))
    return destination


def stamp_environment(project: Path) -> None:
    marker = project / ".venv/.interview-project.json"
    safe_path(marker)
    marker.write_text(
        json.dumps(
            {"project": str(project.resolve()), "system": platform.system(), "machine": platform.machine()},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install a selected InterviewSimulator profile")
    parser.add_argument(
        "--profile",
        choices=["cloud-text", "cloud-local-voice", "local-text", "local-voice"],
        default="local-voice",
    )
    parser.add_argument("--model", choices=["9b", "4b"], default="9b")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--install-native", action="store_true")
    parser.add_argument("--skip-models", action="store_true")
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT / "config/download-manifest.json").read_text())
    selected = ([args.model] if args.profile.startswith("local") else []) + (
        ["whisper-small"] if "voice" in args.profile else []
    )
    tools, installs = commands(args.profile, platform.system())
    print(f"Profile: {args.profile}; device: {platform.system()} {platform.machine()}")
    for key in selected:
        asset = manifest["models"][key]
        print(f"Model: {asset['path']} — {asset['license']}; up to {asset['maximum_bytes'] / 1e9:.2f} GB")
    print("Required native tools: " + (", ".join(tools) or "none"))
    if platform.system() == "Darwin" and platform.machine() == "x86_64":
        print(
            "Intel Mac Python builds: install Apple command-line tools and `brew install openssl@3 rust pkgconf` if missing."
        )
    if args.dry_run:
        for command in installs:
            print("Optional native install: " + " ".join(command))
        print("Dry run: no files, packages, keys, or models changed.")
        return 0
    if not shutil.which("uv"):
        raise ValueError("Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    required = (
        sum(
            manifest["models"][key]["maximum_bytes"]
            for key in selected
            if not (ROOT / manifest["models"][key]["path"]).exists()
        )
        + 2_000_000_000
    )
    if not args.skip_models and shutil.disk_usage(ROOT).free < required:
        raise ValueError(f"Free at least {required / 1e9:.1f} GB for this installation")
    run(["uv", "python", "install", "3.13"], ROOT)
    for project in [ROOT, ROOT / "InterviewWiki", ROOT / "InterviewWiki/PersonalWiki"]:
        prepare_environment(project, ROOT / ".simulator/environment-backups")
        run(["uv", "sync", "--locked", "--no-dev"], project)
        stamp_environment(project)
    if args.install_native:
        for command in installs:
            if not shutil.which(command[0]):
                raise ValueError(f"Install {command[0]} first, or use the manual native-tool guide")
            run(command, ROOT)
        for tool in tools:
            if not shutil.which(tool) and tool in manifest["native_sources"]:
                build_native(ROOT, tool, manifest["native_sources"][tool])
    if not args.skip_models:
        for key in selected:
            print("Verifying/downloading " + key)
            download(ROOT, manifest["models"][key])
    env_path = ROOT / ".env"
    safe_path(env_path)
    if not env_path.exists():
        lines = []
        if args.profile.startswith("local"):
            lines.append("INTERVIEW_SIMULATOR_GGUF=" + manifest["models"][args.model]["path"])
        if "voice" in args.profile:
            lines.append("INTERVIEW_SIMULATOR_WHISPER_MODEL=" + manifest["models"]["whisper-small"]["path"])
        if (ROOT / ".native").exists():
            paths = [str(p) for p in (ROOT / ".native").glob("*/build/bin*") if p.is_dir()]
            # Dedicated tool paths are discovered by Settings.load, not persisted into a shell PATH.
            print("Local native binaries: " + os.pathsep.join(paths))
        descriptor = os.open(env_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as file:
            file.write("\n".join(lines) + "\n")
    receipt = ROOT / ".simulator/setup-receipt.json"
    safe_path(receipt)
    receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=receipt.parent, prefix=".setup-")
    with os.fdopen(descriptor, "w") as file:
        json.dump(
            {
                "profile": args.profile,
                "device": platform.system(),
                "architecture": platform.machine(),
                "native": {tool: shutil.which(tool) for tool in tools},
                "selected_models": selected,
                "model_checksums_verified": not args.skip_models,
                "manifest_checked_at": manifest["checked_at"],
            },
            file,
            indent=2,
        )
    Path(name).replace(receipt)
    print("Python setup completed. Existing private settings were preserved.")
    missing = [tool for tool in tools if not shutil.which(tool)]
    if missing:
        print("Missing native tools: " + ", ".join(missing) + ". See doc/installation/LOCAL_VOICE_SETUP.md.")
    if "voice" in args.profile:
        print("Install/select an English, Japanese and Mandarin local voice; then run the speech tests.")
    return 2 if missing else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Setup stopped: " + str(error), file=sys.stderr)
        raise SystemExit(1) from None
