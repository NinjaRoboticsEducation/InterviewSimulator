from __future__ import annotations

import html
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from .config import Config
from .errors import InterviewWikiError
from .opportunity import load_opportunity
from .profile import resolve_profile_photo
from .schemas import validate_data
from .util import operation_lock, read_json, write_text


def _text(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _facts(value: dict[str, Any]) -> str:
    return _text(" ".join(str(item) for item in value.get("fact_ids", [])))


def _links(item: dict[str, Any]) -> str:
    rendered = []
    for link in item.get("links", []):
        url = str(link.get("url", ""))
        if not url.startswith("https://"):
            continue
        rendered.append(
            f'<a href="{_text(url)}" target="_blank" rel="noopener noreferrer">{_text(link.get("label"))}</a>'
        )
    return f'<span class="claim-links">({"; ".join(rendered)})</span>' if rendered else ""


def _claim_li(item: dict[str, Any]) -> str:
    return (
        f'<li data-block-id="{_text(item.get("block_id"))}" data-fact-ids="{_facts(item)}">'
        f'{_text(item.get("text"))}{_links(item)}</li>'
    )


def _contact(candidate: dict[str, Any], locale: str, title: str) -> str:
    labels = {
        "en": {"email": "Email", "phone": "Phone", "website": "Website", "linkedin": "LinkedIn", "youtube": "YouTube", "location": "Location"},
        "ja": {"email": "メール", "phone": "電話", "website": "Webサイト", "linkedin": "LinkedIn", "youtube": "YouTube", "location": "所在地"},
    }[locale]
    icons = {"email": "@", "phone": "T", "website": "W", "linkedin": "in", "youtube": ">", "location": "L"}
    rows = []
    for key in ("email", "phone", "website", "linkedin", "youtube", "location"):
        value = str(candidate.get(key, "")).strip()
        if not value:
            continue
        rendered = _text(value)
        if key == "email":
            rendered = f'<a href="mailto:{_text(value)}">{_text(value)}</a>'
        elif key == "phone":
            tel = re.sub(r"[^+0-9]", "", value)
            rendered = f'<a href="tel:{_text(tel)}">{_text(value)}</a>'
        elif key in {"website", "linkedin", "youtube"} and value.startswith("https://"):
            label = re.sub(r"^https://", "", value).rstrip("/")
            rendered = f'<a href="{_text(value)}" target="_blank" rel="noopener noreferrer">{_text(label)}</a>'
        rows.append(
            f'<li><span class="contact-icon" aria-hidden="true">{icons[key]}</span>'
            f'<span><span class="sr-only">{_text(labels[key])}: </span>{rendered}</span></li>'
        )
    return f'<section class="sidebar-section"><h2 class="sidebar-title">{_text(title)}</h2><ul class="contact-list">{"".join(rows)}</ul></section>'


def _sidebar(content: dict[str, Any], candidate: dict[str, Any], locale: str, photo_name: str | None) -> str:
    sidebar = content["sidebar"]
    labels = sidebar["labels"]
    if photo_name:
        portrait = f'<img src="assets/{_text(photo_name)}" alt="{_text(content["name"])}" class="profile-photo">'
    else:
        initial = str(content["name"]).strip()[:1] or "?"
        portrait = f'<div class="profile-placeholder" role="img" aria-label="{_text(content["name"])}">{_text(initial)}</div>'
    languages = "".join(
        f'<div class="lang-row" data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}"><strong>{_text(item["language"])}</strong><span>{_text(item["level"])}</span></div>'
        for item in sidebar["languages"]
    )
    skills = "".join(
        f'<li data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}">{_text(item["text"])}</li>'
        for item in sidebar["skills"]
    )
    tools = "".join(
        f'<li data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}">{_text(item["text"])}</li>'
        for item in sidebar["tools"]
    )
    education = "".join(
        f'<li data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}"><strong>{_text(item["institution"])}</strong></li>'
        f'<li class="detail">{_text(item["detail"])}</li><li class="detail">{_text(item["period"])}</li>'
        for item in sidebar["education"]
    )
    awards = "".join(
        f'<li data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}"><span>{_text(item["year"] or "-")}</span>{_text(item["text"])}</li>'
        for item in sidebar["awards"]
    )
    awards_section = (
        f'<section class="sidebar-section"><h2 class="sidebar-title">{_text(labels["awards"])}</h2><ul class="award-list">{awards}</ul></section>'
        if awards else ""
    )
    return (
        f'<aside class="sidebar">{portrait}<h1 class="name">{_text(content["name"])}</h1>'
        f'{_contact(candidate, locale, labels["contact"])}'
        f'<section class="sidebar-section"><h2 class="sidebar-title">{_text(labels["languages"])}</h2>{languages}</section>'
        f'<section class="sidebar-section"><h2 class="sidebar-title">{_text(labels["skills"])}</h2><ul class="tag-list">{skills}</ul></section>'
        f'<section class="sidebar-section"><h2 class="sidebar-title">{_text(labels["tools"])}</h2><ul class="tag-list">{tools}</ul></section>'
        f'<section class="sidebar-section"><h2 class="sidebar-title">{_text(labels["education"])}</h2><ul class="plain-list">{education}</ul></section>'
        f'{awards_section}</aside>'
    )


def _main(content: dict[str, Any]) -> str:
    labels = content["section_labels"]
    introductions = "".join(
        f'<p data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}">{_text(item["text"])}</p>'
        for item in content["self_introduction"]
    )
    signals = "".join(
        f'<div class="signal" data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}"><strong>{_text(item["label"])}</strong><span>{_text(item["text"])}</span></div>'
        for item in content["signals"]
    )
    experiences = []
    for item in content["professional_experience"]:
        metadata = " | ".join(value for value in (str(item["period"]), str(item["location"])) if value)
        responsibilities = "".join(_claim_li(claim) for claim in item["responsibilities"])
        achievements = "".join(_claim_li(claim) for claim in item["achievements"])
        responsibility_section = f'<h4>{_text(labels["responsibilities"])}</h4><ul>{responsibilities}</ul>' if responsibilities else ""
        achievement_section = f'<h4>{_text(labels["achievements"])}</h4><ul>{achievements}</ul>' if achievements else ""
        experiences.append(
            f'<article class="experience" data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}">'
            f'<div class="experience-header"><div><h3>{_text(item["company"])}</h3><p>{_text(item["role"])}</p></div><span>{_text(metadata)}</span></div>'
            f'{responsibility_section}{achievement_section}</article>'
        )
    earlier = ""
    if content["earlier_career"]:
        headers = labels["earlier_headers"]
        rows = "".join(
            f'<tr data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}"><td>{_text(item["period"])}</td><td>{_text(item["title"])}</td><td>{_text(item["company"])}</td><td>{_text(item["location"])}</td></tr>'
            for item in content["earlier_career"]
        )
        earlier = (
            f'<div class="earlier-career"><h3>{_text(labels["earlier_career"])}</h3><table><thead><tr>'
            f'{"".join(f"<th>{_text(header)}</th>" for header in headers)}</tr></thead><tbody>{rows}</tbody></table></div>'
        )
    expertise = "".join(
        f'<article class="expertise-block" data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}"><h3>{_text(item["title"])}</h3><ul>{"".join(_claim_li(claim) for claim in item["bullets"])}</ul></article>'
        for item in content["expertise"]
    )
    self_pr = "".join(
        f'<p data-block-id="{_text(item["block_id"])}" data-fact-ids="{_facts(item)}">{_text(item["text"])}{_links(item)}</p>'
        for item in content["self_pr"]
    )
    heading = lambda title: f'<div class="section-heading"><h2>{_text(title)}</h2></div>'
    return (
        f'<main class="main"><header><h1 class="headline">{_text(content["headline"])}</h1></header>'
        f'<section class="section intro-section" data-section-id="self-introduction">{heading(labels["self_introduction"])}{introductions}</section>'
        f'<div class="signal-strip" data-section-id="signals">{signals}</div>'
        f'<section class="section" data-section-id="professional-experience">{heading(labels["professional_experience"])}{"".join(experiences)}{earlier}</section>'
        f'<section class="section" data-section-id="personal-expertise">{heading(labels["expertise"])}<div class="expertise-grid">{expertise}</div></section>'
        f'<section class="section" data-section-id="self-pr">{heading(labels["self_pr"])}<div class="self-pr">{self_pr}</div></section>'
        '</main>'
    )


def _locale_page(locale: str, content: dict[str, Any], candidate: dict[str, Any], photo_name: str | None) -> str:
    active = " active" if locale == "en" else ""
    return (
        f'<article class="resume-page{active}" id="resume-{locale}" data-language="{locale}" lang="{locale}">'
        f'{_sidebar(content, candidate, locale, photo_name)}{_main(content)}</article>'
    )


def render_resume(config: Config, reference: str, *, create_pdf: bool | str = False) -> dict[str, str]:
    parsed, metadata = load_opportunity(config, reference)
    output = config.opportunity_output(parsed)
    data = read_json(output / "Evidence/resume-content.json")
    errors = validate_data(config, "resume-content", data)
    if errors:
        raise InterviewWikiError("Resume content is invalid: " + "; ".join(errors))
    resume_root = output / "Resume"
    assets_root = resume_root / "assets"
    lock = config.runtime / "locks" / f"resume-{'-'.join(parsed)}.lock"
    with operation_lock(lock):
        assets_root.mkdir(parents=True, exist_ok=True)
        candidate = data["candidate"]
        photo_name: str | None = None
        photo = resolve_profile_photo(config)
        photo_value = str(candidate.get("photo", "")).strip()
        if photo is None and photo_value:
            raise InterviewWikiError(
                "Resume candidate.photo is set, but no canonical photo exists under PersonalWiki/raw/media"
            )
        for stale in assets_root.glob("profile.*"):
            if stale.is_file():
                stale.unlink()
        if photo is not None:
            photo_name = "profile" + photo.suffix.lower()
            shutil.copy2(photo, assets_root / photo_name)

        template = (config.resume_template / "index.html.tpl").read_text(encoding="utf-8")
        rendered = (
            template.replace("{{TITLE}}", _text(f"{metadata['company']} - {metadata['role']} - Resume"))
            .replace("{{RESUME_EN}}", _locale_page("en", data["locales"]["en"], candidate, photo_name))
            .replace("{{RESUME_JA}}", _locale_page("ja", data["locales"]["ja"], candidate, photo_name))
        )
        html_path = resume_root / "index.html"
        write_text(html_path, rendered)

        palette = (config.settings.get("resume") or {}).get("palette") or {}
        css = (config.resume_template / "styles.css.tpl").read_text(encoding="utf-8")
        for key in ("paper", "sheet", "ink", "muted", "line", "panel", "deep", "accent", "accent_secondary", "gold"):
            if key not in palette:
                raise InterviewWikiError(f"Missing resume palette color: {key}")
            css = css.replace("{{" + key + "}}", str(palette[key]))
        write_text(resume_root / "styles.css", css)
        write_text(resume_root / "script.js", (config.resume_template / "script.js").read_text(encoding="utf-8"))

        result = {"html": html_path.relative_to(config.root).as_posix()}
        if create_pdf:
            mode = "bilingual" if create_pdf is True else str(create_pdf)
            result.update(
                {key: Path(value).relative_to(config.root).as_posix() for key, value in _render_pdfs(html_path, resume_root, mode).items()}
            )
        return result


def _browser_executable() -> str:
    configured = os.environ.get("INTERVIEWWIKI_BROWSER")
    browser = Path(configured).expanduser() if configured else None
    if browser is not None:
        if not browser.is_file():
            raise InterviewWikiError("INTERVIEWWIKI_BROWSER does not point to an executable file")
        return str(browser)
    executable = next(
        (value for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge") if (value := shutil.which(name))),
        None,
    )
    if executable:
        return executable
    if platform.system() == "Darwin":
        applications = Path(Path.home().anchor) / "Applications"
        for relative in (
            "Google Chrome.app/Contents/MacOS/Google Chrome",
            "Chromium.app/Contents/MacOS/Chromium",
            "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ):
            candidate = applications / relative
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    raise InterviewWikiError("No supported browser found; set INTERVIEWWIKI_BROWSER or omit --pdf")


def _render_single_pdf(html_path: Path, pdf_path: Path, locale: str) -> None:
    command = [
        _browser_executable(), "--headless", "--disable-gpu", "--disable-extensions",
        "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1000",
        f"--print-to-pdf={pdf_path}", f"{html_path.resolve().as_uri()}?lang={locale}",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    if completed.returncode != 0 or not pdf_path.is_file():
        detail = (completed.stderr or completed.stdout or "browser did not create a PDF").strip()
        raise InterviewWikiError(f"PDF rendering failed: {detail}")
    _validate_pdf_privacy(pdf_path)


def _validate_pdf_privacy(pdf_path: Path) -> None:
    reader = PdfReader(str(pdf_path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if "file://" in text or re.search(r"/(?:Users|Volumes)/", text) or re.search(r"[A-Za-z]:\\\\Users\\\\", text):
        raise InterviewWikiError(f"Generated PDF contains a local filesystem path: {pdf_path.name}")


def _merge_pdfs(inputs: list[Path], output: Path) -> None:
    writer = PdfWriter()
    for path in inputs:
        writer.append(str(path))
    with output.open("wb") as handle:
        writer.write(handle)
    _validate_pdf_privacy(output)


def _render_pdfs(html_path: Path, resume_root: Path, mode: str) -> dict[str, str]:
    if mode not in {"en", "ja", "bilingual", "all"}:
        raise InterviewWikiError("PDF mode must be en, ja, bilingual, or all")
    result: dict[str, str] = {}
    temporary: list[Path] = []
    en_path = resume_root / ("resume-en.pdf" if mode in {"en", "all"} else ".resume-en.tmp.pdf")
    ja_path = resume_root / ("resume-ja.pdf" if mode in {"ja", "all"} else ".resume-ja.tmp.pdf")
    if mode in {"en", "bilingual", "all"}:
        _render_single_pdf(html_path, en_path, "en")
        if en_path.name.startswith("."):
            temporary.append(en_path)
        else:
            result["pdf_en"] = en_path.as_posix()
    if mode in {"ja", "bilingual", "all"}:
        _render_single_pdf(html_path, ja_path, "ja")
        if ja_path.name.startswith("."):
            temporary.append(ja_path)
        else:
            result["pdf_ja"] = ja_path.as_posix()
    if mode in {"bilingual", "all"}:
        bilingual = resume_root / "resume-bilingual.pdf"
        _merge_pdfs([en_path, ja_path], bilingual)
        result["pdf_bilingual"] = bilingual.as_posix()
    for path in temporary:
        path.unlink(missing_ok=True)
    return result
