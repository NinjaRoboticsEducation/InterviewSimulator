from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .files import private_database
from .questions import Question


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        private_database(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, opportunity TEXT NOT NULL, locale TEXT NOT NULL,
                    mode TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL, questions_json TEXT NOT NULL,
                    flow_mode TEXT NOT NULL DEFAULT 'fixed');
                CREATE TABLE IF NOT EXISTS question_versions (
                    version_id TEXT PRIMARY KEY, scope TEXT NOT NULL, locale TEXT NOT NULL,
                    normalized_hash TEXT NOT NULL, wording TEXT NOT NULL, category TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL, UNIQUE(scope, locale, normalized_hash, evidence_hash));
                CREATE TABLE IF NOT EXISTS question_concepts (
                    concept_id TEXT PRIMARY KEY, scope TEXT NOT NULL, category TEXT NOT NULL,
                    source_question_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS concept_versions (
                    concept_id TEXT NOT NULL REFERENCES question_concepts(concept_id),
                    version_id TEXT NOT NULL REFERENCES question_versions(version_id),
                    PRIMARY KEY(concept_id, version_id));
                CREATE TABLE IF NOT EXISTS presentations (
                    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, version_id TEXT NOT NULL REFERENCES question_versions(version_id),
                    status TEXT NOT NULL, presented_at TEXT NOT NULL, UNIQUE(run_id, ordinal));
                CREATE TABLE IF NOT EXISTS answers (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, submission_id TEXT NOT NULL, text TEXT NOT NULL,
                    input_mode TEXT NOT NULL, skipped INTEGER NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, ordinal), UNIQUE(run_id, submission_id));
                CREATE TABLE IF NOT EXISTS recognitions (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, raw_text TEXT NOT NULL,
                    PRIMARY KEY(run_id, ordinal));
                CREATE TABLE IF NOT EXISTS selection_decisions (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, ordinal));
                CREATE TABLE IF NOT EXISTS evaluations (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, ordinal));
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            if "flow_mode" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN flow_mode TEXT NOT NULL DEFAULT 'fixed'")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        private_database(self.path)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create_run(
        self,
        opportunity: str,
        locale: str,
        snapshot: dict[str, Any],
        questions: list[Question],
        mode: str = "exam",
        flow_mode: str = "fixed",
    ) -> str:
        if flow_mode not in {"fixed", "adaptive"}:
            raise ValueError("Unknown interview flow mode")
        if mode != "exam":
            raise ValueError("Only exam mode is ready; report coaching is provided afterward")
        run_id = "run-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs (run_id, opportunity, locale, mode, status, created_at, snapshot_json, questions_json, flow_mode) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    opportunity,
                    locale,
                    mode,
                    "active",
                    _now(),
                    json.dumps(snapshot, ensure_ascii=False),
                    json.dumps([q.to_dict() for q in questions], ensure_ascii=False),
                    flow_mode,
                ),
            )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            answers = db.execute(
                "SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (run_id,)
            ).fetchall()
            recognitions = db.execute(
                "SELECT ordinal, raw_text FROM recognitions WHERE run_id=?", (run_id,)
            ).fetchall()
            decisions = db.execute(
                "SELECT ordinal, payload_json FROM selection_decisions WHERE run_id=? ORDER BY ordinal",
                (run_id,),
            ).fetchall()
            evaluations = db.execute(
                "SELECT * FROM evaluations WHERE run_id=? ORDER BY ordinal", (run_id,)
            ).fetchall()
        result = dict(row)
        result["selection_decisions"] = {
            int(row["ordinal"]): json.loads(row["payload_json"]) for row in decisions
        }
        result["snapshot"] = json.loads(result.pop("snapshot_json"))
        result["questions"] = json.loads(result.pop("questions_json"))
        result["answers"] = [dict(item) for item in answers]
        raw_by_ordinal = {item["ordinal"]: item["raw_text"] for item in recognitions}
        for answer in result["answers"]:
            answer["raw_transcript"] = raw_by_ordinal.get(answer["ordinal"])
        result["evaluations"] = {item["ordinal"]: json.loads(item["payload_json"]) for item in evaluations}
        return result

    def recent_run(self) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT run_id FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
            ).fetchone()
        return str(row[0]) if row else None

    def active_run(self) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT run_id FROM runs WHERE status='active' ORDER BY created_at LIMIT 1"
            ).fetchone()
        return str(row[0]) if row else None

    def present(self, run_id: str, ordinal: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] != "active" or ordinal != len(run["answers"]) + 1 or not 1 <= ordinal <= 10:
            raise ValueError("Question is not the next active turn")
        q = run["questions"][ordinal - 1]
        normalized = unicodedata.normalize("NFC", " ".join(q["text"].split()))
        wording_hash = hashlib.sha256(normalized.encode()).hexdigest()
        evidence = json.dumps(
            [
                q["category"],
                q["fact_ids"],
                q["requirement_ids"],
                q.get("source_ids", []),
                q.get("source_question_id"),
                run["snapshot"]["hashes"],
            ],
            sort_keys=True,
        )
        evidence_hash = hashlib.sha256(evidence.encode()).hexdigest()
        concept_source = q.get("source_question_id") or q["question_id"]
        concept_id = hashlib.sha256(
            f"{run['opportunity']}:{q['category']}:{concept_source}".encode()
        ).hexdigest()
        version = hashlib.sha256(
            (run["opportunity"] + q["locale"] + wording_hash + evidence_hash).encode()
        ).hexdigest()
        event_id = f"{run_id}-q{ordinal:02d}"
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO question_versions VALUES (?,?,?,?,?,?,?)",
                (
                    version,
                    run["opportunity"],
                    q["locale"],
                    wording_hash,
                    q["text"],
                    q["category"],
                    evidence_hash,
                ),
            )
            db.execute(
                "INSERT OR IGNORE INTO question_concepts VALUES (?,?,?,?)",
                (concept_id, run["opportunity"], q["category"], concept_source),
            )
            db.execute("INSERT OR IGNORE INTO concept_versions VALUES (?,?)", (concept_id, version))
            db.execute(
                "INSERT OR IGNORE INTO presentations VALUES (?,?,?,?,?,?)",
                (event_id, run_id, ordinal, version, "issued", _now()),
            )
        return {**q, "ordinal": ordinal, "event_id": event_id}

    def acknowledge_presentation(self, run_id: str, ordinal: int, event_id: str) -> None:
        with self.connect() as db:
            updated = db.execute(
                "UPDATE presentations SET status='displayed' WHERE run_id=? AND ordinal=? AND event_id=?",
                (run_id, ordinal, event_id),
            )
            if updated.rowcount != 1:
                raise ValueError("Presentation event does not match this turn")

    def submit(
        self,
        run_id: str,
        ordinal: int,
        submission_id: str,
        text: str,
        input_mode: str = "text",
        skipped: bool = False,
        raw_transcript: str | None = None,
    ) -> dict[str, Any]:
        if len(text) > 6000 or (raw_transcript is not None and len(raw_transcript) > 6000):
            raise ValueError("Answers must be no more than 6000 characters")
        if skipped and raw_transcript is not None:
            raise ValueError("A skipped answer cannot have recognition text")
        if not submission_id or len(submission_id) > 128 or input_mode not in {"text", "voice"}:
            raise ValueError("Invalid submission")
        if skipped and text:
            raise ValueError("A skipped answer must not contain transcript text")
        if input_mode == "voice" and not skipped and not raw_transcript:
            raise ValueError("Voice submissions require the original recognition text")
        if not skipped and not text.strip():
            raise ValueError("Confirm a non-empty transcript or explicitly skip")
        with self.connect() as db:
            existing = db.execute(
                "SELECT * FROM answers WHERE run_id=? AND submission_id=?", (run_id, submission_id)
            ).fetchone()
            if existing:
                previous_raw = db.execute(
                    "SELECT raw_text FROM recognitions WHERE run_id=? AND ordinal=?", (run_id, ordinal)
                ).fetchone()
                if (
                    existing["ordinal"] != ordinal
                    or existing["text"] != text
                    or bool(existing["skipped"]) != skipped
                    or existing["input_mode"] != input_mode
                    or (previous_raw[0] if previous_raw else None) != raw_transcript
                ):
                    raise ValueError("Submission ID reused with different content")
                return dict(existing)
            count = db.execute("SELECT COUNT(*) FROM answers WHERE run_id=?", (run_id,)).fetchone()[0]
            presented = db.execute(
                "SELECT 1 FROM presentations WHERE run_id=? AND ordinal=? AND status='displayed'",
                (run_id, ordinal),
            ).fetchone()
            status = db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if (
                status is None
                or status[0] != "active"
                or ordinal != count + 1
                or not 1 <= ordinal <= 10
                or not presented
            ):
                raise ValueError("Answer does not match the presented active question")
            db.execute(
                "INSERT INTO answers VALUES (?,?,?,?,?,?,?)",
                (run_id, ordinal, submission_id, text, input_mode, int(skipped), _now()),
            )
            if raw_transcript is not None:
                db.execute("INSERT INTO recognitions VALUES (?,?,?)", (run_id, ordinal, raw_transcript))
            if ordinal == 10:
                db.execute("UPDATE runs SET status='answered' WHERE run_id=?", (run_id,))
        return {
            "run_id": run_id,
            "ordinal": ordinal,
            "submission_id": submission_id,
            "text": text,
            "input_mode": input_mode,
            "skipped": int(skipped),
            "raw_transcript": raw_transcript,
        }

    def save_evaluation(self, run_id: str, ordinal: int, payload: dict[str, Any]) -> None:
        with self.connect() as db:
            if not db.execute(
                "SELECT 1 FROM answers WHERE run_id=? AND ordinal=?", (run_id, ordinal)
            ).fetchone():
                raise ValueError("Cannot evaluate an unanswered question")
            existing = db.execute(
                "SELECT payload_json FROM evaluations WHERE run_id=? AND ordinal=?", (run_id, ordinal)
            ).fetchone()
            if existing:
                previous = json.loads(existing[0])
                if "score" in previous:
                    original = {k: v for k, v in previous.items() if k not in {"coaching", "coaching_error"}}
                    proposed = {k: v for k, v in payload.items() if k not in {"coaching", "coaching_error"}}
                    if original != proposed:
                        raise ValueError("A saved assessment cannot be revised")
                    if "coaching" in previous:
                        return
            db.execute(
                "INSERT INTO evaluations VALUES (?,?,?) ON CONFLICT(run_id, ordinal) DO UPDATE SET payload_json=excluded.payload_json",
                (run_id, ordinal, json.dumps(payload, ensure_ascii=False)),
            )

    def eligible_bank_questions(
        self, opportunity: str, locale: str, hashes: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Only actually presented historical questions bound to exactly the current preparation."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT r.snapshot_json, r.questions_json, p.ordinal FROM presentations p "
                "JOIN runs r ON r.run_id=p.run_id WHERE r.opportunity=? AND r.locale=? "
                "ORDER BY r.created_at DESC, p.ordinal LIMIT 200",
                (opportunity, locale),
            ).fetchall()
        seen: set[str] = set()
        result = []
        for row in rows:
            if json.loads(row["snapshot_json"]).get("hashes") != hashes:
                continue
            q = json.loads(row["questions_json"])[row["ordinal"] - 1]
            if q["text"] not in seen:
                result.append(q)
                seen.add(q["text"])
            if len(result) >= 20:
                break
        return result

    def commit_selection(
        self, run_id: str, ordinal: int, chosen: dict[str, Any], decision: dict[str, Any]
    ) -> None:
        with self.connect() as db:
            if db.execute(
                "SELECT 1 FROM selection_decisions WHERE run_id=? AND ordinal=?", (run_id, ordinal)
            ).fetchone():
                return
            row = db.execute("SELECT questions_json, status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row["status"] != "active":
                raise ValueError("Selection requires an active run")
            questions = json.loads(row["questions_json"])
            if questions[ordinal - 1]["category"] != chosen["category"]:
                raise ValueError("Selection cannot change topic coverage")
            questions[ordinal - 1] = chosen
            db.execute(
                "UPDATE runs SET questions_json=? WHERE run_id=?",
                (json.dumps(questions, ensure_ascii=False), run_id),
            )
            db.execute(
                "INSERT INTO selection_decisions VALUES (?,?,?)", (run_id, ordinal, json.dumps(decision))
            )

    def practice_profile(self, opportunity: str, locale: str) -> dict[str, Any]:
        """Rebuildable observations; history never changes the scoring rubric."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT run_id FROM runs WHERE opportunity=? AND locale=? ORDER BY created_at, run_id",
                (opportunity, locale),
            ).fetchall()
        categories: dict[str, dict[str, Any]] = {}
        for row in rows:
            run = self.get_run(row["run_id"])
            answers = {item["ordinal"]: item for item in run["answers"]}
            for ordinal, evaluation in run["evaluations"].items():
                if "score" not in evaluation:
                    continue
                category = run["questions"][ordinal - 1]["category"]
                item = categories.setdefault(category, {"assessed": 0, "skipped": 0, "scores": []})
                item["assessed"] += 1
                item["skipped"] += int(answers[ordinal]["skipped"])
                item["scores"].append(float(evaluation["score"]))
        summary = {}
        for category, item in categories.items():
            summary[category] = {
                "assessed": item["assessed"],
                "skipped": item["skipped"],
                "average": round(sum(item["scores"]) / len(item["scores"]), 1),
                "latest": item["scores"][-1],
            }
        return {"opportunity": opportunity, "locale": locale, "runs": len(rows), "categories": summary}
