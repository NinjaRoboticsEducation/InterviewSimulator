from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .errors import InterviewWikiError
from .util import ensure_within, reject_symlink_path, sha256_file


DEFAULT_PROFILE_FILENAMES = ("Profile.png", "Profile.jpg", "Profile.jpeg")


def accepted_profile_filenames(config: Config) -> tuple[str, ...]:
    configured = (config.settings.get("resume") or {}).get("profile_photo_filenames")
    values = tuple(str(value) for value in configured) if isinstance(configured, list) else DEFAULT_PROFILE_FILENAMES
    if not values or any(Path(value).name != value or Path(value).suffix.lower() not in {".png", ".jpg", ".jpeg"} for value in values):
        raise InterviewWikiError("resume.profile_photo_filenames must contain PNG/JPEG filenames only")
    return values


def profile_media_root(config: Config) -> Path:
    return config.personal_wiki / "raw/media"


def _validate_image_signature(path: Path) -> None:
    header = path.read_bytes()[:12]
    suffix = path.suffix.lower()
    if suffix == ".png" and header[:8] != b"\x89PNG\r\n\x1a\n":
        raise InterviewWikiError(f"Profile photo extension/content mismatch: {path.name}")
    if suffix in {".jpg", ".jpeg"} and header[:3] != b"\xff\xd8\xff":
        raise InterviewWikiError(f"Profile photo extension/content mismatch: {path.name}")


def resolve_profile_photo(config: Config) -> Path | None:
    media = profile_media_root(config)
    if not media.is_dir():
        return None
    matches = [media / name for name in accepted_profile_filenames(config) if (media / name).is_file()]
    if len(matches) > 1:
        raise InterviewWikiError(
            "Multiple canonical profile photos found; keep exactly one of " + ", ".join(accepted_profile_filenames(config))
        )
    if not matches:
        return None
    photo = ensure_within(matches[0], media, must_exist=True)
    reject_symlink_path(photo, media)
    _validate_image_signature(photo)
    return photo


def profile_photo_status(config: Config) -> dict[str, Any]:
    try:
        photo = resolve_profile_photo(config)
    except InterviewWikiError as exc:
        return {
            "valid": False, "detected": False, "error": str(exc),
            "required_location": "PersonalWiki/raw/media",
            "accepted_filenames": list(accepted_profile_filenames(config)),
        }
    return {
        "valid": True, "detected": photo is not None,
        "required_location": "PersonalWiki/raw/media",
        "accepted_filenames": list(accepted_profile_filenames(config)),
        "path": photo.relative_to(config.root).as_posix() if photo else None,
        "content_hash": sha256_file(photo) if photo else "absent",
    }
