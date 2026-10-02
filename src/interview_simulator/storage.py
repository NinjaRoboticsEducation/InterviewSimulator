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

from filelock import FileLock

from .files import private_database, reject_links
from .questions import Question


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        private_database(path)
        migration_lock = path.with_suffix(".migration.lock")
        reject_links(migration_lock)
        with FileLock(migration_lock, timeout=15):
            with sqlite3.connect(path) as db:
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'"
                ).fetchone()
                columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
                if exists and db.execute("PRAGMA user_version").fetchone()[0] < 3:
                    backup = path.with_name(path.stem + ".pre-v3.sqlite")
                    reject_links(backup)
                    if not backup.exists():
                        private_database(backup)
                        with sqlite3.connect(backup) as target:
                            db.backup(target)
                            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                                raise ValueError("Pre-migration backup failed integrity validation")
                if exists and "revision" not in columns:
                    backup = path.with_name(path.stem + ".pre-v2.sqlite")
                    reject_links(backup)
                    if not backup.exists():
                        private_database(backup)
                        with sqlite3.connect(backup) as target:
                            db.backup(target)
                            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                                raise ValueError("Pre-migration backup failed integrity validation")
            with self.connect() as db:
                db.executescript(
                    "BEGIN IMMEDIATE;"
                    + """
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
                    CREATE TABLE IF NOT EXISTS answer_versions (
                        run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL, version INTEGER NOT NULL, submission_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        PRIMARY KEY(run_id, ordinal, version), UNIQUE(run_id, submission_id));
                    CREATE TABLE IF NOT EXISTS model_attempts (
                        invocation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                        task TEXT NOT NULL, ordinal INTEGER, status TEXT NOT NULL, metadata_json TEXT NOT NULL,
                        created_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS assessment_revisions (
                        run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                        version INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        PRIMARY KEY(run_id, version));
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                        version INTEGER NOT NULL, kind TEXT NOT NULL, ordinal INTEGER NOT NULL,
                        input_hash TEXT NOT NULL, status TEXT NOT NULL, diagnostics_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS recovery_grants (
                        request_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                        created_at TEXT NOT NULL);
                """
                )
                grant_columns = {row[1] for row in db.execute("PRAGMA table_info(recovery_grants)")}
                for name in ("kind", "payload_hash"):
                    if name not in grant_columns:
                        db.execute(f"ALTER TABLE recovery_grants ADD COLUMN {name} TEXT")
                columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
                if "flow_mode" not in columns:
                    db.execute("ALTER TABLE runs ADD COLUMN flow_mode TEXT NOT NULL DEFAULT 'fixed'")
                for name, definition in {
                    "revision": "INTEGER NOT NULL DEFAULT 0",
                    "scoring_json": "TEXT",
                    "summary_json": "TEXT",
                    "report_state": "TEXT NOT NULL DEFAULT 'idle'",
                    "preparation_error": "TEXT",
                    "request_id": "TEXT",
                    "assessment_version": "INTEGER NOT NULL DEFAULT 0",
                    "report_options": "TEXT",
                    "report_error": "TEXT",
                    "extra_calls": "INTEGER NOT NULL DEFAULT 0",
                }.items():
                    if name not in columns:
                        db.execute(
                            f"ALTER TABLE runs ADD COLUMN {name} {definition}"
                        )  # fixed identifiers only
                # A legacy graded run must never become editable through the new UI.
                db.execute(
                    "UPDATE runs SET report_state='incomplete' WHERE report_state='idle' AND "
                    "EXISTS(SELECT 1 FROM evaluations WHERE evaluations.run_id=runs.run_id)"
                )
                db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS preparation_request ON runs(request_id) WHERE request_id IS NOT NULL"
                )
                db.execute("PRAGMA user_version=3")

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
        *,
        status: str = "active",
        request_id: str | None = None,
    ) -> str:
        if flow_mode not in {"fixed", "adaptive"}:
            raise ValueError("Unknown interview flow mode")
        if mode != "exam":
            raise ValueError("Only exam mode is ready; report coaching is provided afterward")
        run_id = "run-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs (run_id, opportunity, locale, mode, status, created_at, snapshot_json, questions_json, flow_mode,request_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    opportunity,
                    locale,
                    mode,
                    status,
                    _now(),
                    json.dumps(snapshot, ensure_ascii=False),
                    json.dumps([q.to_dict() for q in questions], ensure_ascii=False),
                    flow_mode,
                    request_id,
                ),
            )
        return run_id

    def replace_preparation(self, run_id: str, snapshot: dict, questions: list[Question]) -> None:
        with self.connect() as db:
            if db.execute("SELECT 1 FROM presentations WHERE run_id=?", (run_id,)).fetchone():
                raise ValueError("Prepared questions cannot change after delivery")
            db.execute(
                "UPDATE runs SET snapshot_json=?,questions_json=? WHERE run_id=? AND status IN ('active','preparing','ready','preparation_failed')",
                (
                    json.dumps(snapshot, ensure_ascii=False),
                    json.dumps([q.to_dict() for q in questions], ensure_ascii=False),
                    run_id,
                ),
            )

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
            attempts = db.execute(
                "SELECT task,ordinal,status,metadata_json,created_at FROM model_attempts WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        result = dict(row)
        for key in ("preparation_error", "report_options", "report_error"):
            result[key] = json.loads(result[key]) if result[key] else None
        result["model_attempts"] = [
            {**dict(attempt), "metadata": json.loads(attempt["metadata_json"])} for attempt in attempts
        ]
        for attempt in result["model_attempts"]:
            attempt.pop("metadata_json")
        result["selection_decisions"] = {
            int(row["ordinal"]): json.loads(row["payload_json"]) for row in decisions
        }
        result["snapshot"] = json.loads(result.pop("snapshot_json"))
        summary = result.pop("summary_json", None)
        if summary:
            result["summary_result"] = json.loads(summary)
            result["summary"] = result["summary_result"]["text"]
        result["questions"] = json.loads(result.pop("questions_json"))
        result["answers"] = [dict(item) for item in answers]
        raw_by_ordinal = {item["ordinal"]: item["raw_text"] for item in recognitions}
        for answer in result["answers"]:
            answer["raw_transcript"] = raw_by_ordinal.get(answer["ordinal"])
        result["evaluations"] = {item["ordinal"]: json.loads(item["payload_json"]) for item in evaluations}
        return result

    def list_runs(self) -> list[dict]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT run_id,opportunity,locale,status,report_state,created_at,revision FROM runs ORDER BY created_at DESC LIMIT 100"
                )
            ]

    def recent_run(self) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT run_id FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
            ).fetchone()
        return str(row[0]) if row else None

    def active_run(self) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT run_id FROM runs WHERE status IN ('active','paused','preparing','ready') ORDER BY created_at LIMIT 1"
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
        expected_revision: int | None = None,
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
            current = db.execute("SELECT revision FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if expected_revision is not None and (current is None or current[0] != expected_revision):
                raise ValueError("This interview changed in another tab. Reload before saving.")
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
            db.execute("UPDATE runs SET revision=revision+1 WHERE run_id=?", (run_id,))
        return {
            "run_id": run_id,
            "ordinal": ordinal,
            "submission_id": submission_id,
            "text": text,
            "input_mode": input_mode,
            "skipped": int(skipped),
            "raw_transcript": raw_transcript,
        }

    def edit(
        self,
        run_id: str,
        ordinal: int,
        text: str,
        submission_id: str,
        expected_revision: int,
        skipped: bool = False,
    ) -> dict[str, Any]:
        if (
            not 1 <= ordinal <= 10
            or not submission_id
            or len(submission_id) > 128
            or len(text) > 6000
            or (skipped and text)
            or (not skipped and not text.strip())
        ):
            raise ValueError("Confirm a non-empty answer or explicitly skip")
        payload = {"text": text, "skipped": skipped}
        with self.connect() as db:
            repeated = db.execute(
                "SELECT payload_json FROM answer_versions WHERE run_id=? AND submission_id=?",
                (run_id, submission_id),
            ).fetchone()
            if repeated:
                if json.loads(repeated[0]) != {**payload, "ordinal": ordinal}:
                    raise ValueError("Submission ID reused with different content")
                return payload
            row = db.execute(
                "SELECT revision,status,report_state FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None or row[0] != expected_revision:
                raise ValueError("This interview changed in another tab. Reload before saving.")
            if row[1] not in {"active", "answered", "paused"} or row[2] != "idle":
                raise ValueError("Answers are locked once scoring starts. Start a new practice run.")
            original = db.execute(
                "SELECT * FROM answers WHERE run_id=? AND ordinal=?", (run_id, ordinal)
            ).fetchone()
            if not original:
                raise ValueError("Only a confirmed earlier answer can be edited")
            version = db.execute(
                "SELECT COALESCE(MAX(version),0) FROM answer_versions WHERE run_id=? AND ordinal=?",
                (run_id, ordinal),
            ).fetchone()[0]
            if not version:
                db.execute(
                    "INSERT INTO answer_versions VALUES (?,?,?,?,?,?)",
                    (run_id, ordinal, 1, original["submission_id"], json.dumps(dict(original)), _now()),
                )
                version = 1
            db.execute(
                "INSERT INTO answer_versions VALUES (?,?,?,?,?,?)",
                (
                    run_id,
                    ordinal,
                    version + 1,
                    submission_id,
                    json.dumps({**payload, "ordinal": ordinal}),
                    _now(),
                ),
            )
            # Keep the original submission ID for audit history; final text is canonical in answers.
            db.execute(
                "UPDATE answers SET text=?,skipped=?,input_mode='text' WHERE run_id=? AND ordinal=?",
                (text, int(skipped), run_id, ordinal),
            )
            db.execute("UPDATE runs SET revision=revision+1 WHERE run_id=?", (run_id,))
        return payload

    def transition(self, run_id: str, action: str, expected_revision: int) -> None:
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError("Unknown interview action")
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise ValueError("This interview changed in another tab. Reload before continuing.")
            if row["report_state"] != "idle":
                raise ValueError("Scoring has started. Stop or resume the report instead.")
            allowed = {
                "pause": {"active"},
                "resume": {"paused"},
                "cancel": {"active", "paused", "answered", "preparation_failed", "ready"},
            }
            if row["status"] not in allowed[action]:
                raise ValueError("This action is not available in the current interview state")
            status = {"pause": "paused", "resume": "active", "cancel": "cancelled"}[action]
            db.execute("UPDATE runs SET status=?,revision=revision+1 WHERE run_id=?", (status, run_id))

    def lock_scoring(self, run_id: str, expected_revision: int | None = None) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["scoring_json"]:
                return json.loads(row["scoring_json"])
            if expected_revision is not None and row["revision"] != expected_revision:
                raise ValueError("This interview changed in another tab. Review again before scoring.")
            answers = [
                dict(a)
                for a in db.execute("SELECT * FROM answers WHERE run_id=? ORDER BY ordinal", (run_id,))
            ]
            if len(answers) != 10 or row["status"] != "answered":
                raise ValueError("Complete or explicitly skip all ten questions before final evaluation")
            snapshot = {
                "answers": answers,
                "questions": json.loads(row["questions_json"]),
                "answer_snapshot_id": uuid.uuid4().hex,
                "revision": row["revision"],
            }
            db.execute(
                "UPDATE runs SET scoring_json=?,report_state='running',revision=revision+1 WHERE run_id=?",
                (json.dumps(snapshot, ensure_ascii=False), run_id),
            )
        return snapshot

    def report_state(self, run_id: str, state: str) -> None:
        if state not in {"running", "interrupted", "complete", "incomplete", "retry_wait"}:
            raise ValueError("Unknown report state")
        with self.connect() as db:
            updated = db.execute("UPDATE runs SET report_state=? WHERE run_id=?", (state, run_id))
            if updated.rowcount != 1:
                raise KeyError(run_id)

    def save_summary(self, run_id: str, summary: dict) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET summary_json=? WHERE run_id=? AND summary_json IS NULL",
                (json.dumps(summary, ensure_ascii=False), run_id),
            )

    def recover_interrupted(self) -> None:
        """Called only after acquiring the exclusive server lease."""
        with self.connect() as db:
            db.execute("UPDATE runs SET report_state='interrupted' WHERE report_state='running'")
            db.execute("UPDATE model_attempts SET status='unknown' WHERE status='pending'")
            db.execute("UPDATE tasks SET status='interrupted' WHERE status IN ('running','received')")
            db.execute(
                "UPDATE runs SET status='preparation_failed',preparation_error=? WHERE status IN ('preparing','ready')",
                (
                    json.dumps(
                        {
                            "code": "INTERRUPTED",
                            "message": "Preparation interrupted. Retry or use the fixed deck.",
                        }
                    ),
                ),
            )

    def begin_attempt(self, run_id: str, task: str, ordinal: int, maximum: int) -> str:
        invocation_id = uuid.uuid4().hex
        with self.connect() as db:
            run = db.execute(
                "SELECT assessment_version,extra_calls FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError("Interview not found")
            count = sum(
                json.loads(r[0]).get("assessment_version", 0) == run[0]
                and json.loads(r[0]).get("dispatch_state") != "not_sent"
                for r in db.execute("SELECT metadata_json FROM model_attempts WHERE run_id=?", (run_id,))
            )
            if count >= maximum + run[1]:
                from .providers import ProviderError

                raise ProviderError(
                    "This run reached its model-call budget. Review the report before granting 12 more attempts.",
                    code="CALL_BUDGET",
                    dispatch="not_sent",
                )
            db.execute(
                "INSERT INTO model_attempts VALUES (?,?,?,?,?,?,?)",
                (
                    invocation_id,
                    run_id,
                    task,
                    ordinal,
                    "pending",
                    json.dumps({"assessment_version": run[0]}),
                    _now(),
                ),
            )
        return invocation_id

    def finish_attempt(self, invocation_id: str, status: str, metadata: dict) -> None:
        with self.connect() as db:
            prior = db.execute(
                "SELECT metadata_json FROM model_attempts WHERE invocation_id=?", (invocation_id,)
            ).fetchone()
            metadata = {**(json.loads(prior[0]) if prior else {}), **metadata}
            db.execute(
                "UPDATE model_attempts SET status=?,metadata_json=? WHERE invocation_id=?",
                (status, json.dumps(metadata), invocation_id),
            )

    def request_run(self, request_id: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT run_id FROM runs WHERE request_id=?", (request_id,)).fetchone()
        return row[0] if row else None

    def preparation_state(self, run_id: str, status: str, error: dict | None = None) -> None:
        if status not in {"preparing", "ready", "preparation_failed", "active"}:
            raise ValueError("Invalid preparation state")
        with self.connect() as db:
            row = db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row[0] not in {"preparing", "ready", "preparation_failed"}:
                raise ValueError("Preparation can only change an undelivered interview")
            db.execute(
                "UPDATE runs SET status=?,preparation_error=? WHERE run_id=?",
                (status, json.dumps(error) if error else None, run_id),
            )

    def report_failure(self, run_id: str, error: dict | None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET report_error=? WHERE run_id=?",
                (json.dumps(error) if error else None, run_id),
            )

    def checkpoint(
        self,
        run_id: str,
        kind: str,
        ordinal: int,
        input_hash: str,
        status: str,
        diagnostic: dict | None = None,
    ) -> str:
        with self.connect() as db:
            version = db.execute("SELECT assessment_version FROM runs WHERE run_id=?", (run_id,)).fetchone()[
                0
            ]
            task_id = hashlib.sha256(f"{run_id}:{version}:{kind}:{ordinal}:{input_hash}".encode()).hexdigest()
            db.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET status=excluded.status,diagnostics_json=excluded.diagnostics_json,updated_at=excluded.updated_at",
                (
                    task_id,
                    run_id,
                    version,
                    kind,
                    ordinal,
                    input_hash,
                    status,
                    json.dumps(diagnostic or {}),
                    _now(),
                ),
            )
        return task_id

    def grant_recovery(self, run_id: str, request_id: str, expected_revision: int) -> None:
        with self.connect() as db:
            prior = db.execute(
                "SELECT run_id,kind,payload_hash FROM recovery_grants WHERE request_id=?", (request_id,)
            ).fetchone()
            if prior:
                if prior[0] != run_id or prior[1] != "allowance":
                    raise ValueError("Recovery request ID was reused for a different action")
                return
            row = db.execute(
                "SELECT revision,extra_calls,report_state FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if (
                row is None
                or row[0] != expected_revision
                or row[1] >= 120
                or row[2] not in {"incomplete", "interrupted", "retry_wait"}
            ):
                raise ValueError("Review the interrupted report before adding a recovery allowance")
            db.execute(
                "INSERT INTO recovery_grants(request_id,run_id,created_at,kind) VALUES (?,?,?,?)",
                (request_id, run_id, _now(), "allowance"),
            )
            db.execute(
                "UPDATE runs SET extra_calls=extra_calls+12,revision=revision+1 WHERE run_id=?", (run_id,)
            )

    def new_assessment_revision(
        self, run_id: str, plan: dict, expected_revision: int, request_id: str
    ) -> None:
        with self.connect() as db:
            payload_hash = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
            prior = db.execute(
                "SELECT run_id,kind,payload_hash FROM recovery_grants WHERE request_id=?", (request_id,)
            ).fetchone()
            if prior:
                if (prior[0], prior[1], prior[2]) != (run_id, "revision", payload_hash):
                    raise ValueError("Recovery request ID was reused for a different configuration")
                return
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if (
                row is None
                or row["revision"] != expected_revision
                or row["status"] != "answered"
                or row["report_state"] in {"running", "idle"}
            ):
                raise ValueError(
                    "Stop and review the existing report before changing its assessment configuration"
                )
            previous = {
                "evaluations": {
                    r[0]: json.loads(r[1])
                    for r in db.execute(
                        "SELECT ordinal,payload_json FROM evaluations WHERE run_id=?", (run_id,)
                    )
                },
                "summary": row["summary_json"],
                "options": row["report_options"],
                "state": row["report_state"],
            }
            db.execute(
                "INSERT INTO assessment_revisions VALUES (?,?,?,?)",
                (run_id, row["assessment_version"], json.dumps(previous), _now()),
            )
            db.execute("DELETE FROM evaluations WHERE run_id=?", (run_id,))
            db.execute(
                "UPDATE runs SET assessment_version=assessment_version+1,report_options=?,summary_json=NULL,report_error=NULL,report_state='incomplete',extra_calls=0,revision=revision+1 WHERE run_id=?",
                (json.dumps(plan), run_id),
            )
            db.execute(
                "INSERT INTO recovery_grants(request_id,run_id,created_at,kind,payload_hash) VALUES (?,?,?,?,?)",
                (request_id, run_id, _now(), "revision", payload_hash),
            )

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
                "JOIN runs r ON r.run_id=p.run_id WHERE r.opportunity=? AND r.locale=? AND p.status='displayed' "
                "ORDER BY r.created_at DESC, p.ordinal LIMIT 200",
                (opportunity, locale),
            ).fetchall()
        seen: set[str] = set()
        result = []
        for row in rows:
            if json.loads(row["snapshot_json"]).get("hashes") != hashes:
                continue
            q = json.loads(row["questions_json"])[row["ordinal"] - 1]
            if not q.get("localization_version"):
                continue
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
