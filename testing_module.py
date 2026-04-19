from __future__ import annotations

import csv
import io
import random
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import qrcode
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for


testing_bp = Blueprint("testing", __name__, url_prefix="/tests")

TESTING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    subject TEXT NOT NULL,
    assigned_group TEXT,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    token TEXT NOT NULL UNIQUE,
    deadline TEXT,
    time_limit INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS test_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    source_bank_question_id INTEGER,
    question_text TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE,
    FOREIGN KEY (source_bank_question_id) REFERENCES question_bank (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS test_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (question_id) REFERENCES test_questions (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS test_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    user_id INTEGER,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    result_token TEXT NOT NULL UNIQUE,
    student_name TEXT NOT NULL,
    student_group TEXT NOT NULL,
    student_identifier TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    percentage REAL NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    total_possible_points INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS test_attempt_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    selected_option_id INTEGER,
    is_correct INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (attempt_id) REFERENCES test_attempts (id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES test_questions (id) ON DELETE CASCADE,
    FOREIGN KEY (selected_option_id) REFERENCES test_options (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (teacher_id, subject, topic_name),
    FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS question_bank (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    topic_id INTEGER,
    difficulty TEXT NOT NULL DEFAULT 'medium' CHECK(difficulty IN ('easy', 'medium', 'hard')),
    question_text TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES question_topics (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_bank_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_question_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (bank_question_id) REFERENCES question_bank (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tests_created_by ON tests (created_by);
CREATE INDEX IF NOT EXISTS idx_tests_subject ON tests (subject);
CREATE INDEX IF NOT EXISTS idx_test_questions_test_id ON test_questions (test_id);
CREATE INDEX IF NOT EXISTS idx_test_options_question_id ON test_options (question_id);
CREATE INDEX IF NOT EXISTS idx_test_attempts_test_id ON test_attempts (test_id);
CREATE INDEX IF NOT EXISTS idx_test_attempts_group ON test_attempts (student_group);
CREATE INDEX IF NOT EXISTS idx_test_attempt_answers_attempt_id ON test_attempt_answers (attempt_id);
CREATE INDEX IF NOT EXISTS idx_question_topics_teacher_subject ON question_topics (teacher_id, subject);
CREATE INDEX IF NOT EXISTS idx_question_bank_teacher_subject ON question_bank (teacher_id, subject);
CREATE INDEX IF NOT EXISTS idx_question_bank_topic ON question_bank (topic_id);
CREATE INDEX IF NOT EXISTS idx_question_bank_options_question ON question_bank_options (bank_question_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user_created_at ON activity_logs (user_id, created_at);
"""


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(item[1] == column for item in columns)


def init_testing_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(TESTING_SCHEMA_SQL)

    if not _column_exists(connection, "tests", "assigned_group"):
        connection.execute("ALTER TABLE tests ADD COLUMN assigned_group TEXT")
    if not _column_exists(connection, "tests", "max_attempts"):
        connection.execute("ALTER TABLE tests ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 1")
    if not _column_exists(connection, "test_attempts", "user_id"):
        connection.execute("ALTER TABLE test_attempts ADD COLUMN user_id INTEGER")
    if not _column_exists(connection, "test_attempts", "attempt_number"):
        connection.execute("ALTER TABLE test_attempts ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1")
    if not _column_exists(connection, "test_questions", "source_bank_question_id"):
        connection.execute("ALTER TABLE test_questions ADD COLUMN source_bank_question_id INTEGER")

    connection.execute("CREATE INDEX IF NOT EXISTS idx_tests_assigned_group ON tests (assigned_group)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_tests_max_attempts ON tests (max_attempts)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_test_attempts_user_id ON test_attempts (user_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_test_attempts_attempt_number ON test_attempts (test_id, user_id, attempt_number)")

    connection.commit()
    connection.close()


def _db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def _tr(key: str, **kwargs) -> str:
    translations = current_app.config["TRANSLATIONS"]
    default_language = current_app.config.get("DEFAULT_LANGUAGE", "ru")
    language = session.get("language", default_language)
    if language not in translations:
        language = default_language
    text = translations[language].get(key, translations[default_language].get(key, key))
    return text.format(**kwargs) if kwargs else text


def _csv_response(filename: str, rows: list[list[object]]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    response = current_app.response_class(output.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
    return response


def _log_activity(
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: str | None = None,
    user_id: int | None = None,
    role: str | None = None,
) -> None:
    actor_id = user_id if user_id is not None else session.get("user_id")
    actor_role = role if role is not None else session.get("role")
    try:
        _db().execute(
            """
            INSERT INTO activity_logs (user_id, role, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor_id,
                actor_role,
                action,
                entity_type,
                entity_id,
                details,
                _now_stamp(),
            ),
        )
        _db().commit()
    except sqlite3.Error:
        # Logging must not break user flows.
        return


def _login_redirect_response():
    target = request.full_path if request.query_string else request.path
    return redirect(url_for("login", next=target))


def auth_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            flash(_tr("please_login_continue"), "warning")
            return _login_redirect_response()
        return view(*args, **kwargs)

    return wrapped_view


def teacher_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            flash(_tr("please_login_continue"), "warning")
            return _login_redirect_response()
        if session.get("role") != "teacher":
            flash(_tr("teacher_only_access"), "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def student_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            flash(_tr("please_login_continue"), "warning")
            return _login_redirect_response()
        if session.get("role") != "student":
            flash(_tr("student_only_access"), "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_deadline_value() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _parse_deadline(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    datetime.strptime(value, "%Y-%m-%dT%H:%M")
    return value


def _parse_started_at(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    return datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")


def _parse_deadline_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")


def _deadline_passed(deadline_value: str | None) -> bool:
    return bool(deadline_value and deadline_value < _now_deadline_value())


def _test_session_key(token: str) -> str:
    return f"test_session_{token}"


def _get_test_session(token: str) -> dict[str, str] | None:
    value = session.get(_test_session_key(token))
    return value if isinstance(value, dict) else None


def _set_test_session(token: str, payload: dict[str, str]) -> None:
    session[_test_session_key(token)] = payload
    session.modified = True


def _clear_test_session(token: str) -> None:
    session.pop(_test_session_key(token), None)
    session.modified = True


def _generate_token() -> str:
    while True:
        token = secrets.token_urlsafe(9)
        exists = _db().execute("SELECT 1 FROM tests WHERE token = ?", (token,)).fetchone()
        if exists is None:
            return token


def _generate_result_token() -> str:
    while True:
        token = secrets.token_urlsafe(12)
        exists = _db().execute("SELECT 1 FROM test_attempts WHERE result_token = ?", (token,)).fetchone()
        if exists is None:
            return token


def _qr_directory() -> Path:
    qr_dir = Path(current_app.config["QR_CODE_DIR"])
    qr_dir.mkdir(parents=True, exist_ok=True)
    return qr_dir


def _write_qr_code(token: str) -> str:
    public_url = url_for("testing.public_test_start", token=token, _external=True)
    qr_path = _qr_directory() / f"{token}.png"
    qrcode.make(public_url).save(qr_path)
    return f"qr/{token}.png"


def _ensure_qr_code(token: str) -> str:
    qr_path = _qr_directory() / f"{token}.png"
    if not qr_path.exists():
        return _write_qr_code(token)
    return f"qr/{token}.png"


def _delete_qr_code(token: str) -> None:
    qr_path = _qr_directory() / f"{token}.png"
    if qr_path.exists():
        qr_path.unlink()


def _fetch_teacher_test(test_id: int) -> sqlite3.Row | None:
    return _db().execute(
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM test_questions q WHERE q.test_id = t.id) AS question_count,
               (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id) AS attempt_count,
               COALESCE((SELECT SUM(points) FROM test_questions q WHERE q.test_id = t.id), 0) AS total_points,
               ROUND((SELECT AVG(a.percentage) FROM test_attempts a WHERE a.test_id = t.id), 1) AS average_percentage,
               (SELECT MAX(a.percentage) FROM test_attempts a WHERE a.test_id = t.id) AS highest_percentage,
               (SELECT MIN(a.percentage) FROM test_attempts a WHERE a.test_id = t.id) AS lowest_percentage,
               (SELECT COUNT(DISTINCT a.user_id) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id IS NOT NULL) AS completed_students,
               (
                   SELECT COUNT(*)
                   FROM users u
                   WHERE u.role = 'student'
                     AND (
                         t.assigned_group IS NULL
                         OR t.assigned_group = ''
                         OR LOWER(u.group_name) = LOWER(t.assigned_group)
                     )
               ) AS assigned_students
        FROM tests t
        WHERE t.id = ? AND t.created_by = ?
        """,
        (test_id, session["user_id"]),
    ).fetchone()


def _fetch_public_test(token: str) -> sqlite3.Row | None:
    return _db().execute(
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM test_questions q WHERE q.test_id = t.id) AS question_count,
               COALESCE((SELECT SUM(points) FROM test_questions q WHERE q.test_id = t.id), 0) AS total_points
        FROM tests t
        WHERE t.token = ?
        """,
        (token,),
    ).fetchone()


def _fetch_question(question_id: int) -> sqlite3.Row | None:
    return _db().execute(
        """
        SELECT q.*, t.created_by
        FROM test_questions q
        JOIN tests t ON t.id = q.test_id
        WHERE q.id = ? AND t.created_by = ?
        """,
        (question_id, session["user_id"]),
    ).fetchone()


def _fetch_question_payload(question_id: int) -> dict[str, object] | None:
    question = _fetch_question(question_id)
    if question is None:
        return None
    options = _db().execute(
        "SELECT * FROM test_options WHERE question_id = ? ORDER BY sort_order ASC, id ASC",
        (question_id,),
    ).fetchall()
    return {
        "question": question,
        "options": [dict(option) for option in options],
        "correct_option": next((str(index) for index, option in enumerate(options, start=1) if option["is_correct"]), "1"),
    }


def _fetch_questions_with_options(test_id: int) -> list[dict[str, object]]:
    question_rows = _db().execute(
        "SELECT * FROM test_questions WHERE test_id = ? ORDER BY sort_order ASC, id ASC",
        (test_id,),
    ).fetchall()

    questions: list[dict[str, object]] = []
    for question in question_rows:
        option_rows = _db().execute(
            "SELECT * FROM test_options WHERE question_id = ? ORDER BY sort_order ASC, id ASC",
            (question["id"],),
        ).fetchall()
        payload = dict(question)
        payload["options"] = [dict(option) for option in option_rows]
        payload["correct_option_id"] = next(
            (option["id"] for option in option_rows if option["is_correct"]),
            None,
        )
        questions.append(payload)

    return questions


def _fetch_recent_attempts(test_id: int, limit: int = 10) -> list[sqlite3.Row]:
    return _db().execute(
        """
        SELECT *
        FROM test_attempts
        WHERE test_id = ?
        ORDER BY submitted_at DESC, id DESC
        LIMIT ?
        """,
        (test_id, limit),
    ).fetchall()


def _fetch_teacher_tests(subject_filter: str = "") -> list[sqlite3.Row]:
    query = [
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM test_questions q WHERE q.test_id = t.id) AS question_count,
               (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id) AS attempt_count,
               COALESCE((SELECT SUM(points) FROM test_questions q WHERE q.test_id = t.id), 0) AS total_points,
               ROUND((SELECT AVG(a.percentage) FROM test_attempts a WHERE a.test_id = t.id), 1) AS average_percentage,
               (SELECT MAX(a.percentage) FROM test_attempts a WHERE a.test_id = t.id) AS highest_percentage,
               (SELECT MIN(a.percentage) FROM test_attempts a WHERE a.test_id = t.id) AS lowest_percentage,
               (SELECT COUNT(DISTINCT a.user_id) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id IS NOT NULL) AS completed_students,
               (
                   SELECT COUNT(*)
                   FROM users u
                   WHERE u.role = 'student'
                     AND (
                         t.assigned_group IS NULL
                         OR t.assigned_group = ''
                         OR LOWER(u.group_name) = LOWER(t.assigned_group)
                     )
               ) AS assigned_students
        FROM tests t
        WHERE t.created_by = ?
        """
    ]
    params: list[object] = [session["user_id"]]
    if subject_filter:
        query.append("AND t.subject = ?")
        params.append(subject_filter)
    query.append("ORDER BY t.created_at DESC, t.id DESC")
    return _db().execute(" ".join(query), tuple(params)).fetchall()


def _fetch_teacher_subjects() -> list[str]:
    rows = _db().execute(
        "SELECT DISTINCT subject FROM tests WHERE created_by = ? ORDER BY subject COLLATE NOCASE ASC",
        (session["user_id"],),
    ).fetchall()
    return [row["subject"] for row in rows]


def _fetch_student_assigned_tests(user_id: int, group_name: str) -> list[sqlite3.Row]:
    return _db().execute(
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM test_questions q WHERE q.test_id = t.id) AS question_count,
               (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id = ?) AS attempt_count,
               (SELECT MAX(a.percentage) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id = ?) AS best_percentage,
               (SELECT MAX(a.submitted_at) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id = ?) AS last_submitted_at
        FROM tests t
        WHERE t.is_active = 1
          AND EXISTS (SELECT 1 FROM test_questions q WHERE q.test_id = t.id)
          AND (t.assigned_group IS NULL OR t.assigned_group = '' OR LOWER(t.assigned_group) = LOWER(?))
        ORDER BY
            CASE WHEN t.deadline IS NULL OR t.deadline = '' THEN 1 ELSE 0 END ASC,
            t.deadline ASC,
            t.created_at DESC,
            t.id DESC
        """,
        (user_id, user_id, user_id, group_name),
    ).fetchall()


def _fetch_student_results(user_id: int, limit: int = 40) -> list[sqlite3.Row]:
    return _db().execute(
        """
        SELECT a.*,
               t.title AS test_title,
               t.subject AS test_subject,
               t.token AS test_token
        FROM test_attempts a
        JOIN tests t ON t.id = a.test_id
        WHERE a.user_id = ?
        ORDER BY a.submitted_at DESC, a.id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def _fetch_results_data(test_id_filter: str = "", subject_filter: str = "") -> dict[str, object]:
    parsed_test_id = 0
    if test_id_filter:
        try:
            parsed_test_id = int(test_id_filter)
        except ValueError:
            parsed_test_id = 0
            test_id_filter = ""

    query = [
        """
        SELECT a.*,
               t.title AS test_title,
               t.subject AS test_subject,
               t.token AS test_token
        FROM test_attempts a
        JOIN tests t ON t.id = a.test_id
        WHERE t.created_by = ?
        """
    ]
    params: list[object] = [session["user_id"]]
    if test_id_filter:
        query.append("AND t.id = ?")
        params.append(parsed_test_id)
    if subject_filter:
        query.append("AND t.subject = ?")
        params.append(subject_filter)
    attempts = _db().execute(" ".join(query + ["ORDER BY a.submitted_at DESC, a.id DESC"]), tuple(params)).fetchall()

    summary_row = _db().execute(
        """
        SELECT COUNT(*) AS attempts_count,
               ROUND(AVG(a.score), 2) AS average_score,
               MAX(a.score) AS highest_score,
               MIN(a.score) AS lowest_score
        FROM test_attempts a
        JOIN tests t ON t.id = a.test_id
        WHERE t.created_by = ?
          AND (? = '' OR t.id = ?)
          AND (? = '' OR t.subject = ?)
        """,
        (
            session["user_id"],
            test_id_filter,
            parsed_test_id,
            subject_filter,
            subject_filter,
        ),
    ).fetchone()

    return {
        "attempts": attempts,
        "summary": {
            "attempts_count": summary_row["attempts_count"] or 0,
            "average_score": summary_row["average_score"] or 0,
            "highest_score": summary_row["highest_score"] or 0,
            "lowest_score": summary_row["lowest_score"] or 0,
        },
    }


def _fetch_attempt_review(token: str, result_token: str) -> dict[str, object] | None:
    attempt = _db().execute(
        """
        SELECT a.*,
               t.created_by AS teacher_id,
               t.token AS test_token,
               t.title AS test_title,
               t.description AS test_description,
               t.subject AS test_subject,
               t.time_limit AS test_time_limit,
               t.deadline AS test_deadline
        FROM test_attempts a
        JOIN tests t ON t.id = a.test_id
        WHERE t.token = ? AND a.result_token = ?
        """,
        (token, result_token),
    ).fetchone()
    if attempt is None:
        return None

    answer_rows = _db().execute(
        """
        SELECT aa.is_correct,
               aa.selected_option_id,
               q.id AS question_id,
               q.question_text,
               q.points,
               selected.option_text AS selected_option_text,
               correct.id AS correct_option_id,
               correct.option_text AS correct_option_text
        FROM test_attempt_answers aa
        JOIN test_questions q ON q.id = aa.question_id
        LEFT JOIN test_options selected ON selected.id = aa.selected_option_id
        LEFT JOIN test_options correct ON correct.question_id = q.id AND correct.is_correct = 1
        WHERE aa.attempt_id = ?
        ORDER BY q.sort_order ASC, q.id ASC
        """,
        (attempt["id"],),
    ).fetchall()

    return {"attempt": attempt, "answers": answer_rows}


def _completion_rate(assigned_students: int | None, completed_students: int | None) -> float:
    assigned = assigned_students or 0
    completed = completed_students or 0
    if assigned <= 0:
        return 0.0
    return round((completed / assigned) * 100, 1)


def _count_user_attempts(test_id: int, user_id: int) -> int:
    row = _db().execute(
        "SELECT COUNT(*) AS total FROM test_attempts WHERE test_id = ? AND user_id = ?",
        (test_id, user_id),
    ).fetchone()
    return int(row["total"] or 0)


def _attempt_limit_reached(test: sqlite3.Row, user_id: int) -> tuple[bool, int, int]:
    max_attempts = int(test["max_attempts"] or 1)
    attempts_used = _count_user_attempts(test["id"], user_id)
    return attempts_used >= max_attempts, attempts_used, max_attempts


def _shuffle_questions_for_session(token: str, questions: list[dict[str, object]]) -> list[dict[str, object]]:
    test_session = _get_test_session(token)
    if not test_session:
        return questions

    question_ids = [int(question["id"]) for question in questions]
    order_key = "question_order"
    option_key = "option_order"
    nonce_key = "session_nonce"

    if order_key not in test_session:
        shuffled = question_ids[:]
        random.shuffle(shuffled)
        test_session[order_key] = shuffled
    if option_key not in test_session:
        option_order: dict[str, list[int]] = {}
        for question in questions:
            option_ids = [int(option["id"]) for option in question["options"]]
            random.shuffle(option_ids)
            option_order[str(question["id"])] = option_ids
        test_session[option_key] = option_order
    if nonce_key not in test_session:
        test_session[nonce_key] = secrets.token_urlsafe(10)

    _set_test_session(token, test_session)

    order_list = [int(item) for item in test_session.get(order_key, []) if int(item) in question_ids]
    ordered_questions: list[dict[str, object]] = []
    question_map = {int(question["id"]): dict(question) for question in questions}

    for question_id in order_list:
        payload = question_map.pop(question_id, None)
        if payload is None:
            continue
        option_map = {int(option["id"]): dict(option) for option in payload["options"]}
        preferred_option_order = test_session.get(option_key, {}).get(str(question_id), [])
        ordered_options = [option_map.pop(int(option_id)) for option_id in preferred_option_order if int(option_id) in option_map]
        if option_map:
            ordered_options.extend(option_map.values())
        payload["options"] = ordered_options
        ordered_questions.append(payload)

    if question_map:
        ordered_questions.extend(question_map.values())
    return ordered_questions


def _fetch_question_performance(test_id: int) -> list[dict[str, object]]:
    rows = _db().execute(
        """
        SELECT q.id,
               q.question_text,
               q.points,
               COUNT(aa.id) AS answered_count,
               SUM(CASE WHEN aa.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
        FROM test_questions q
        LEFT JOIN test_attempt_answers aa ON aa.question_id = q.id
        WHERE q.test_id = ?
        GROUP BY q.id, q.question_text, q.points
        ORDER BY q.sort_order ASC, q.id ASC
        """,
        (test_id,),
    ).fetchall()

    performance: list[dict[str, object]] = []
    for row in rows:
        answered = int(row["answered_count"] or 0)
        correct = int(row["correct_count"] or 0)
        correct_rate = round((correct / answered) * 100, 1) if answered else 0.0
        if answered < 3:
            estimated = "insufficient data"
        elif correct_rate >= 80:
            estimated = "easy"
        elif correct_rate >= 50:
            estimated = "medium"
        else:
            estimated = "hard"
        performance.append(
            {
                "id": row["id"],
                "question_text": row["question_text"],
                "points": row["points"],
                "answered_count": answered,
                "correct_count": correct,
                "correct_rate": correct_rate,
                "estimated_difficulty": estimated,
            }
        )
    return performance


def _fetch_teacher_topics(subject_filter: str = "") -> list[sqlite3.Row]:
    query = [
        """
        SELECT qt.*,
               (SELECT COUNT(*) FROM question_bank qb WHERE qb.topic_id = qt.id) AS questions_count
        FROM question_topics qt
        WHERE qt.teacher_id = ?
        """
    ]
    params: list[object] = [session["user_id"]]
    if subject_filter:
        query.append("AND qt.subject = ?")
        params.append(subject_filter)
    query.append("ORDER BY qt.subject COLLATE NOCASE ASC, qt.topic_name COLLATE NOCASE ASC")
    return _db().execute(" ".join(query), tuple(params)).fetchall()


def _fetch_teacher_question_bank(
    subject_filter: str = "",
    topic_id_filter: str = "",
    difficulty_filter: str = "",
) -> list[sqlite3.Row]:
    parsed_topic_id = 0
    if topic_id_filter:
        try:
            parsed_topic_id = int(topic_id_filter)
        except ValueError:
            parsed_topic_id = 0

    query = [
        """
        SELECT qb.*,
               qt.topic_name,
               (SELECT COUNT(*) FROM question_bank_options qbo WHERE qbo.bank_question_id = qb.id) AS options_count
        FROM question_bank qb
        LEFT JOIN question_topics qt ON qt.id = qb.topic_id
        WHERE qb.teacher_id = ?
        """
    ]
    params: list[object] = [session["user_id"]]
    if subject_filter:
        query.append("AND qb.subject = ?")
        params.append(subject_filter)
    if parsed_topic_id > 0:
        query.append("AND qb.topic_id = ?")
        params.append(parsed_topic_id)
    if difficulty_filter in {"easy", "medium", "hard"}:
        query.append("AND qb.difficulty = ?")
        params.append(difficulty_filter)
    query.append("ORDER BY qb.created_at DESC, qb.id DESC")
    return _db().execute(" ".join(query), tuple(params)).fetchall()


def _fetch_bank_subjects() -> list[str]:
    rows = _db().execute(
        "SELECT DISTINCT subject FROM question_bank WHERE teacher_id = ? ORDER BY subject COLLATE NOCASE ASC",
        (session["user_id"],),
    ).fetchall()
    return [row["subject"] for row in rows]


def _fetch_bank_question(question_id: int) -> sqlite3.Row | None:
    return _db().execute(
        """
        SELECT qb.*, qt.topic_name
        FROM question_bank qb
        LEFT JOIN question_topics qt ON qt.id = qb.topic_id
        WHERE qb.id = ? AND qb.teacher_id = ?
        """,
        (question_id, session["user_id"]),
    ).fetchone()


def _fetch_bank_question_payload(question_id: int) -> dict[str, object] | None:
    question = _fetch_bank_question(question_id)
    if question is None:
        return None
    options = _db().execute(
        "SELECT * FROM question_bank_options WHERE bank_question_id = ? ORDER BY sort_order ASC, id ASC",
        (question_id,),
    ).fetchall()
    return {
        "question": question,
        "options": [dict(option) for option in options],
        "correct_option": next((str(index) for index, option in enumerate(options, start=1) if option["is_correct"]), "1"),
    }


def _validate_bank_question_form() -> tuple[dict[str, object], list[str]]:
    subject = request.form.get("subject", "").strip()
    topic_name = request.form.get("topic_name", "").strip()
    difficulty = request.form.get("difficulty", "medium").strip().lower()
    question_text = request.form.get("question_text", "").strip()
    points_raw = request.form.get("points", "").strip()
    options = [request.form.get(f"option_{index}", "").strip() for index in range(1, 5)]
    correct_option = request.form.get("correct_option", "").strip()

    errors: list[str] = []
    if not subject:
        errors.append("Предмет обязателен.")
    if not topic_name:
        errors.append("Тема обязательна.")
    if difficulty not in {"easy", "medium", "hard"}:
        errors.append("Сложность должна быть: легкая, средняя или сложная.")
    if not question_text:
        errors.append("Текст вопроса обязателен.")
    if not all(options):
        errors.append("Все четыре варианта ответа обязательны.")
    if not points_raw.isdigit() or int(points_raw) <= 0:
        errors.append("Баллы должны быть положительным целым числом.")
    if correct_option not in {"1", "2", "3", "4"}:
        errors.append("Выберите правильный вариант ответа.")

    return {
        "subject": subject,
        "topic_name": topic_name,
        "difficulty": difficulty if difficulty in {"easy", "medium", "hard"} else "medium",
        "question_text": question_text,
        "points": int(points_raw) if points_raw.isdigit() and int(points_raw) > 0 else 1,
        "options": options,
        "correct_option": int(correct_option) if correct_option in {"1", "2", "3", "4"} else 1,
    }, errors


def _upsert_topic(teacher_id: int, subject: str, topic_name: str) -> int:
    row = _db().execute(
        """
        SELECT id
        FROM question_topics
        WHERE teacher_id = ?
          AND LOWER(subject) = LOWER(?)
          AND LOWER(topic_name) = LOWER(?)
        """,
        (teacher_id, subject, topic_name),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = _db().execute(
        """
        INSERT INTO question_topics (teacher_id, subject, topic_name, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (teacher_id, subject, topic_name, _now_stamp()),
    )
    return int(cursor.lastrowid)


def _save_bank_options(bank_question_id: int, options: list[str], correct_option: int) -> None:
    _db().execute("DELETE FROM question_bank_options WHERE bank_question_id = ?", (bank_question_id,))
    for index, option_text in enumerate(options, start=1):
        _db().execute(
            """
            INSERT INTO question_bank_options (bank_question_id, option_text, is_correct, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (bank_question_id, option_text, 1 if index == correct_option else 0, index),
        )


def _add_random_questions_from_bank(
    test_id: int,
    subject: str,
    topic_id: int | None,
    difficulty: str,
    count: int,
) -> int:
    if count <= 0:
        return 0

    query = [
        """
        SELECT qb.id, qb.question_text, qb.points
        FROM question_bank qb
        WHERE qb.teacher_id = ?
          AND qb.subject = ?
        """
    ]
    params: list[object] = [session["user_id"], subject]
    if topic_id:
        query.append("AND qb.topic_id = ?")
        params.append(topic_id)
    if difficulty in {"easy", "medium", "hard"}:
        query.append("AND qb.difficulty = ?")
        params.append(difficulty)
    query.append("ORDER BY RANDOM() LIMIT ?")
    params.append(count)

    selected = _db().execute(" ".join(query), tuple(params)).fetchall()
    if not selected:
        return 0

    start_order_row = _db().execute(
        "SELECT COALESCE(MAX(sort_order), 0) AS max_order FROM test_questions WHERE test_id = ?",
        (test_id,),
    ).fetchone()
    sort_order = int(start_order_row["max_order"] or 0)

    for row in selected:
        sort_order += 1
        question_cursor = _db().execute(
            """
            INSERT INTO test_questions (test_id, source_bank_question_id, question_text, points, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (test_id, row["id"], row["question_text"], row["points"], sort_order),
        )
        new_question_id = int(question_cursor.lastrowid)
        bank_options = _db().execute(
            """
            SELECT option_text, is_correct, sort_order
            FROM question_bank_options
            WHERE bank_question_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (row["id"],),
        ).fetchall()
        for option in bank_options:
            _db().execute(
                """
                INSERT INTO test_options (question_id, option_text, is_correct, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (new_question_id, option["option_text"], option["is_correct"], option["sort_order"]),
            )

    return len(selected)


def _fetch_journal_rows(group_filter: str = "", test_id_filter: str = "") -> list[sqlite3.Row]:
    parsed_test_id = 0
    if test_id_filter:
        try:
            parsed_test_id = int(test_id_filter)
        except ValueError:
            parsed_test_id = 0

    query = [
        """
        SELECT u.id AS student_id,
               u.name AS student_name,
               u.group_name AS student_group,
               t.id AS test_id,
               t.title AS test_title,
               t.subject AS test_subject,
               COUNT(a.id) AS attempts_count,
               ROUND(AVG(a.percentage), 1) AS average_score,
               MAX(a.percentage) AS best_score,
               MAX(a.submitted_at) AS last_submitted_at
        FROM test_attempts a
        JOIN users u ON u.id = a.user_id
        JOIN tests t ON t.id = a.test_id
        WHERE t.created_by = ?
        """
    ]
    params: list[object] = [session["user_id"]]
    if group_filter:
        query.append("AND LOWER(COALESCE(u.group_name, '')) = LOWER(?)")
        params.append(group_filter)
    if parsed_test_id > 0:
        query.append("AND t.id = ?")
        params.append(parsed_test_id)
    query.append(
        """
        GROUP BY u.id, u.name, u.group_name, t.id, t.title, t.subject
        ORDER BY u.group_name COLLATE NOCASE ASC, u.name COLLATE NOCASE ASC, t.title COLLATE NOCASE ASC
        """
    )
    return _db().execute(" ".join(query), tuple(params)).fetchall()


def _fetch_activity_logs(action_filter: str = "") -> list[sqlite3.Row]:
    query = [
        """
        SELECT al.*, u.name AS user_name
        FROM activity_logs al
        LEFT JOIN users u ON u.id = al.user_id
        WHERE (
            al.user_id = ?
            OR (al.entity_type = 'test' AND al.entity_id IN (SELECT id FROM tests WHERE created_by = ?))
        )
        """
    ]
    params: list[object] = [session["user_id"], session["user_id"]]
    if action_filter:
        query.append("AND al.action = ?")
        params.append(action_filter)
    query.append("ORDER BY al.created_at DESC, al.id DESC LIMIT 300")
    return _db().execute(" ".join(query), tuple(params)).fetchall()


def _validate_test_form() -> tuple[dict[str, object], list[str]]:
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    subject = request.form.get("subject", "").strip()
    assigned_group = request.form.get("assigned_group", "").strip()
    deadline_raw = request.form.get("deadline", "")
    time_limit_raw = request.form.get("time_limit", "").strip()
    max_attempts_raw = request.form.get("max_attempts", "").strip()
    bank_count_raw = request.form.get("bank_question_count", "").strip()
    bank_topic_id_raw = request.form.get("bank_topic_id", "").strip()
    bank_difficulty = request.form.get("bank_difficulty", "").strip().lower()
    is_active = 1 if request.form.get("is_active", "1") == "1" else 0

    errors: list[str] = []
    if not title:
        errors.append(_tr("test_title_required"))
    if not subject:
        errors.append(_tr("test_subject_required"))

    deadline_value = None
    if deadline_raw.strip():
        try:
            deadline_value = _parse_deadline(deadline_raw)
        except ValueError:
            errors.append(_tr("test_deadline_invalid"))

    time_limit = None
    if time_limit_raw:
        if not time_limit_raw.isdigit() or int(time_limit_raw) <= 0:
            errors.append(_tr("test_time_limit_invalid"))
        else:
            time_limit = int(time_limit_raw)

    if not max_attempts_raw:
        max_attempts = 1
    elif not max_attempts_raw.isdigit() or int(max_attempts_raw) <= 0:
        errors.append("Максимум попыток должен быть положительным целым числом.")
        max_attempts = 1
    else:
        max_attempts = int(max_attempts_raw)

    if not bank_count_raw:
        bank_question_count = 0
    elif not bank_count_raw.isdigit() or int(bank_count_raw) < 0:
        errors.append("Количество автодобавления из банка вопросов должно быть нулем или положительным целым числом.")
        bank_question_count = 0
    else:
        bank_question_count = int(bank_count_raw)

    bank_topic_id: int | None = None
    if bank_topic_id_raw:
        if bank_topic_id_raw.isdigit() and int(bank_topic_id_raw) > 0:
            bank_topic_id = int(bank_topic_id_raw)
        else:
            errors.append("Выбранная тема некорректна.")

    if bank_difficulty and bank_difficulty not in {"easy", "medium", "hard", "any"}:
        errors.append("Фильтр сложности должен быть: легкая, средняя, сложная или любая.")
        bank_difficulty = "any"

    return {
        "title": title,
        "description": description,
        "subject": subject,
        "assigned_group": assigned_group,
        "deadline": deadline_value or "",
        "time_limit": time_limit if time_limit is not None else "",
        "max_attempts": max_attempts,
        "bank_question_count": bank_question_count,
        "bank_topic_id": bank_topic_id if bank_topic_id is not None else "",
        "bank_difficulty": bank_difficulty if bank_difficulty else "any",
        "is_active": is_active,
    }, errors


def _validate_question_form() -> tuple[dict[str, object], list[str]]:
    question_text = request.form.get("question_text", "").strip()
    points_raw = request.form.get("points", "").strip()
    options = [request.form.get(f"option_{index}", "").strip() for index in range(1, 5)]
    correct_option = request.form.get("correct_option", "").strip()

    errors: list[str] = []
    if not question_text:
        errors.append(_tr("question_text_required"))
    if not all(options):
        errors.append(_tr("question_options_required"))
    if not points_raw.isdigit() or int(points_raw) <= 0:
        errors.append(_tr("question_points_invalid"))
    if correct_option not in {"1", "2", "3", "4"}:
        errors.append(_tr("correct_option_required"))

    return {
        "question_text": question_text,
        "points": int(points_raw) if points_raw.isdigit() and int(points_raw) > 0 else 1,
        "options": options,
        "correct_option": int(correct_option) if correct_option in {"1", "2", "3", "4"} else 1,
    }, errors


def _validate_student_form() -> tuple[dict[str, str], list[str]]:
    student_name = request.form.get("student_name", "").strip()
    student_group = request.form.get("student_group", "").strip()
    student_identifier = request.form.get("student_identifier", "").strip()

    errors: list[str] = []
    if not student_name:
        errors.append(_tr("student_name_required"))
    if not student_group:
        errors.append(_tr("student_group_required"))

    return {
        "student_name": student_name,
        "student_group": student_group,
        "student_identifier": student_identifier,
    }, errors


def _public_access_reason(test: sqlite3.Row | None, test_session: dict[str, str] | None = None) -> str | None:
    if test is None:
        return "test_not_found"
    if not test["is_active"]:
        return "test_inactive_public"
    if test["question_count"] <= 0:
        return "test_not_ready"

    assigned_group = ""
    if "assigned_group" in test.keys():
        assigned_group = (test["assigned_group"] or "").strip()
    if assigned_group and session.get("role") == "student":
        user_group = ""
        if getattr(g, "user", None) is not None:
            user_group = (g.user["group_name"] or "").strip()
        if assigned_group.lower() != user_group.lower():
            return "test_not_assigned"

    deadline_dt = _parse_deadline_datetime(test["deadline"])
    if deadline_dt is None:
        return None

    if test_session and test_session.get("started_at"):
        started_at = _parse_started_at(test_session["started_at"])
        if started_at is not None and started_at <= deadline_dt:
            return None

    if datetime.now() > deadline_dt:
        return "test_deadline_passed"
    return None


def _remaining_seconds(test: sqlite3.Row, test_session: dict[str, str] | None) -> int | None:
    if not test_session or not test["time_limit"]:
        return None
    started_at = _parse_started_at(test_session.get("started_at"))
    if started_at is None:
        return None
    expires_at = started_at + timedelta(minutes=int(test["time_limit"]))
    return int((expires_at - datetime.now()).total_seconds())


def _save_question_options(question_id: int, options: list[str], correct_option: int) -> None:
    db = _db()
    db.execute("DELETE FROM test_options WHERE question_id = ?", (question_id,))
    for index, option_text in enumerate(options, start=1):
        db.execute(
            """
            INSERT INTO test_options (question_id, option_text, is_correct, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (question_id, option_text, 1 if index == correct_option else 0, index),
        )


def _evaluate_answers(questions: list[dict[str, object]], submitted_answers: dict[str, str]) -> dict[str, object]:
    score = 0
    correct_count = 0
    total_questions = len(questions)
    total_possible_points = sum(int(question["points"]) for question in questions)
    answer_rows: list[dict[str, object]] = []

    for question in questions:
        valid_option_ids = {str(option["id"]): option["id"] for option in question["options"]}
        selected_raw = submitted_answers.get(str(question["id"]), "").strip()
        selected_option_id = valid_option_ids.get(selected_raw)
        correct_option_id = question["correct_option_id"]
        is_correct = selected_option_id is not None and selected_option_id == correct_option_id
        if is_correct:
            correct_count += 1
            score += int(question["points"])
        answer_rows.append(
            {
                "question_id": question["id"],
                "selected_option_id": selected_option_id,
                "is_correct": 1 if is_correct else 0,
            }
        )

    wrong_count = total_questions - correct_count
    percentage = round((score / total_possible_points) * 100, 1) if total_possible_points else 0.0
    return {
        "score": score,
        "percentage": percentage,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total_questions": total_questions,
        "total_possible_points": total_possible_points,
        "answers": answer_rows,
    }


def _store_attempt(
    test: sqlite3.Row,
    student_data: dict[str, str],
    evaluation: dict[str, object],
    started_at: str | None,
    user_id: int | None,
) -> str:
    db = _db()
    result_token = _generate_result_token()
    attempt_number = _count_user_attempts(test["id"], user_id) + 1 if user_id is not None else 1
    cursor = db.execute(
        """
        INSERT INTO test_attempts (
            test_id, user_id, attempt_number, result_token, student_name, student_group, student_identifier,
            score, percentage, correct_count, wrong_count, total_questions,
            total_possible_points, started_at, submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            test["id"],
            user_id,
            attempt_number,
            result_token,
            student_data["student_name"],
            student_data["student_group"],
            student_data["student_identifier"],
            evaluation["score"],
            evaluation["percentage"],
            evaluation["correct_count"],
            evaluation["wrong_count"],
            evaluation["total_questions"],
            evaluation["total_possible_points"],
            started_at,
            _now_stamp(),
        ),
    )
    attempt_id = cursor.lastrowid

    for answer in evaluation["answers"]:
        db.execute(
            """
            INSERT INTO test_attempt_answers (attempt_id, question_id, selected_option_id, is_correct)
            VALUES (?, ?, ?, ?)
            """,
            (
                attempt_id,
                answer["question_id"],
                answer["selected_option_id"],
                answer["is_correct"],
            ),
        )

    db.commit()
    _log_activity(
        action="test_submit",
        entity_type="test",
        entity_id=test["id"],
        details=f"attempt={attempt_number};score={evaluation['score']};percentage={evaluation['percentage']}",
        user_id=user_id,
        role="student",
    )
    return result_token


@testing_bp.route("/")
@auth_required
def manage_tests():
    if session.get("role") == "student":
        return redirect(url_for("testing.assigned_tests"))
    if session.get("role") != "teacher":
        flash(_tr("teacher_only_access"), "danger")
        return redirect(url_for("dashboard"))

    subject_filter = request.args.get("subject", "").strip()
    tests = _fetch_teacher_tests(subject_filter)
    subjects = _fetch_teacher_subjects()
    completion_rates = [_completion_rate(test["assigned_students"], test["completed_students"]) for test in tests]
    average_scores = [float(test["average_percentage"]) for test in tests if test["average_percentage"] is not None]
    question_bank_total = _db().execute(
        "SELECT COUNT(*) AS total FROM question_bank WHERE teacher_id = ?",
        (session["user_id"],),
    ).fetchone()["total"]
    stats = {
        "total_tests": len(tests),
        "active_tests": sum(1 for test in tests if test["is_active"]),
        "inactive_tests": sum(1 for test in tests if not test["is_active"]),
        "total_attempts": sum(int(test["attempt_count"]) for test in tests),
        "average_score": round(sum(average_scores) / len(average_scores), 1) if average_scores else 0.0,
        "average_completion": round(sum(completion_rates) / len(completion_rates), 1) if completion_rates else 0.0,
        "question_bank_total": int(question_bank_total or 0),
    }
    return render_template(
        "tests/manage_tests.html",
        tests=tests,
        subjects=subjects,
        selected_subject=subject_filter,
        stats=stats,
    )


@testing_bp.route("/assigned")
@student_required
def assigned_tests():
    group_name = (g.user["group_name"] or "").strip() if getattr(g, "user", None) else ""
    tests = _fetch_student_assigned_tests(session["user_id"], group_name)
    tests_with_lock = []
    for test in tests:
        attempts_used = int(test["attempt_count"] or 0)
        max_attempts = int(test["max_attempts"] or 1)
        payload = dict(test)
        payload["attempts_used"] = attempts_used
        payload["max_attempts"] = max_attempts
        payload["attempts_left"] = max(max_attempts - attempts_used, 0)
        payload["attempt_locked"] = attempts_used >= max_attempts
        tests_with_lock.append(payload)
    attempts = _fetch_student_results(session["user_id"], limit=20)
    stats = {
        "assigned_tests": len(tests_with_lock),
        "completed_tests": sum(1 for test in tests_with_lock if (test["attempt_count"] or 0) > 0),
        "pending_tests": sum(1 for test in tests_with_lock if (test["attempt_count"] or 0) == 0),
        "average_score": round(
            sum(attempt["percentage"] for attempt in attempts) / len(attempts),
            1,
        )
        if attempts
        else 0.0,
    }
    return render_template(
        "tests/student_tests.html",
        tests=tests_with_lock,
        attempts=attempts,
        stats=stats,
        student_group=group_name,
    )


@testing_bp.route("/question-bank")
@teacher_required
def question_bank():
    subject_filter = request.args.get("subject", "").strip()
    topic_filter = request.args.get("topic_id", "").strip()
    difficulty_filter = request.args.get("difficulty", "").strip().lower()
    topics = _fetch_teacher_topics(subject_filter)
    questions = _fetch_teacher_question_bank(subject_filter, topic_filter, difficulty_filter)
    stats = {
        "total_questions": len(questions),
        "easy": sum(1 for row in questions if row["difficulty"] == "easy"),
        "medium": sum(1 for row in questions if row["difficulty"] == "medium"),
        "hard": sum(1 for row in questions if row["difficulty"] == "hard"),
    }
    return render_template(
        "tests/question_bank_list.html",
        questions=questions,
        topics=topics,
        subjects=_fetch_bank_subjects(),
        selected_subject=subject_filter,
        selected_topic_id=topic_filter,
        selected_difficulty=difficulty_filter,
        stats=stats,
    )


@testing_bp.route("/question-bank/create", methods=["GET", "POST"])
@teacher_required
def question_bank_create():
    if request.method == "POST":
        form_data, errors = _validate_bank_question_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "tests/question_bank_form.html",
                question=form_data,
                topics=_fetch_teacher_topics(form_data["subject"]),
                page_title="Создать вопрос в банке вопросов",
            )

        topic_id = _upsert_topic(session["user_id"], form_data["subject"], form_data["topic_name"])
        cursor = _db().execute(
            """
            INSERT INTO question_bank (teacher_id, subject, topic_id, difficulty, question_text, points, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                form_data["subject"],
                topic_id,
                form_data["difficulty"],
                form_data["question_text"],
                form_data["points"],
                _now_stamp(),
            ),
        )
        bank_question_id = int(cursor.lastrowid)
        _save_bank_options(bank_question_id, form_data["options"], form_data["correct_option"])
        _db().commit()
        _log_activity(
            action="question_bank_create",
            entity_type="question_bank",
            entity_id=bank_question_id,
            details=f"subject={form_data['subject']};difficulty={form_data['difficulty']}",
        )
        flash("Вопрос добавлен в банк вопросов.", "success")
        return redirect(url_for("testing.question_bank"))

    empty_question = {
        "subject": "",
        "topic_name": "",
        "difficulty": "medium",
        "question_text": "",
        "points": 1,
        "options": ["", "", "", ""],
        "correct_option": 1,
    }
    return render_template(
        "tests/question_bank_form.html",
        question=empty_question,
        topics=_fetch_teacher_topics(),
        page_title="Создать вопрос в банке вопросов",
    )


@testing_bp.route("/question-bank/<int:question_id>/edit", methods=["GET", "POST"])
@teacher_required
def question_bank_edit(question_id: int):
    payload = _fetch_bank_question_payload(question_id)
    if payload is None:
        flash("Элемент банка вопросов не найден.", "danger")
        return redirect(url_for("testing.question_bank"))

    question = payload["question"]
    if request.method == "POST":
        form_data, errors = _validate_bank_question_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "tests/question_bank_form.html",
                question=form_data,
                topics=_fetch_teacher_topics(form_data["subject"]),
                page_title="Редактировать вопрос в банке вопросов",
            )

        topic_id = _upsert_topic(session["user_id"], form_data["subject"], form_data["topic_name"])
        _db().execute(
            """
            UPDATE question_bank
            SET subject = ?, topic_id = ?, difficulty = ?, question_text = ?, points = ?
            WHERE id = ? AND teacher_id = ?
            """,
            (
                form_data["subject"],
                topic_id,
                form_data["difficulty"],
                form_data["question_text"],
                form_data["points"],
                question_id,
                session["user_id"],
            ),
        )
        _save_bank_options(question_id, form_data["options"], form_data["correct_option"])
        _db().commit()
        _log_activity(
            action="question_bank_update",
            entity_type="question_bank",
            entity_id=question_id,
            details=f"subject={form_data['subject']};difficulty={form_data['difficulty']}",
        )
        flash("Элемент банка вопросов обновлен.", "success")
        return redirect(url_for("testing.question_bank"))

    form_question = {
        "subject": question["subject"],
        "topic_name": question["topic_name"] or "",
        "difficulty": question["difficulty"],
        "question_text": question["question_text"],
        "points": question["points"],
        "options": [option["option_text"] for option in payload["options"]],
        "correct_option": int(payload["correct_option"]),
    }
    return render_template(
        "tests/question_bank_form.html",
        question=form_question,
        topics=_fetch_teacher_topics(question["subject"]),
        page_title="Редактировать вопрос в банке вопросов",
    )


@testing_bp.route("/question-bank/<int:question_id>/delete", methods=["POST"])
@teacher_required
def question_bank_delete(question_id: int):
    question = _fetch_bank_question(question_id)
    if question is None:
        flash("Элемент банка вопросов не найден.", "danger")
        return redirect(url_for("testing.question_bank"))
    _db().execute("DELETE FROM question_bank WHERE id = ? AND teacher_id = ?", (question_id, session["user_id"]))
    _db().commit()
    _log_activity(action="question_bank_delete", entity_type="question_bank", entity_id=question_id)
    flash("Элемент банка вопросов удален.", "info")
    return redirect(url_for("testing.question_bank"))


@testing_bp.route("/create", methods=["GET", "POST"])
@teacher_required
def create_test():
    topics = _fetch_teacher_topics()
    if request.method == "POST":
        form_data, errors = _validate_test_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "tests/test_form.html",
                test=form_data,
                topics=topics,
                page_title_key="create_test",
            )

        token = _generate_token()
        cursor = _db().execute(
            """
            INSERT INTO tests (
                created_by, title, description, subject, assigned_group, token,
                deadline, time_limit, max_attempts, is_active, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                form_data["title"],
                form_data["description"],
                form_data["subject"],
                form_data["assigned_group"] or None,
                token,
                form_data["deadline"] or None,
                form_data["time_limit"] or None,
                form_data["max_attempts"],
                form_data["is_active"],
                _now_stamp(),
            ),
        )
        test_id = int(cursor.lastrowid)
        auto_added = _add_random_questions_from_bank(
            test_id=test_id,
            subject=form_data["subject"],
            topic_id=form_data["bank_topic_id"] if form_data["bank_topic_id"] else None,
            difficulty=form_data["bank_difficulty"],
            count=int(form_data["bank_question_count"]),
        )
        _db().commit()
        _write_qr_code(token)
        _log_activity(
            action="test_create",
            entity_type="test",
            entity_id=test_id,
            details=f"title={form_data['title']};auto_questions={auto_added}",
        )
        flash(_tr("test_created_successfully"), "success")
        if int(form_data["bank_question_count"]) > 0 and auto_added == 0:
            flash("Подходящие элементы банка вопросов для автогенерации не найдены.", "warning")
        elif auto_added > 0:
            flash(f"Добавлено вопросов из банка: {auto_added}.", "info")
        return redirect(url_for("testing.manage_tests"))

    empty_test = {
        "title": "",
        "description": "",
        "subject": "",
        "assigned_group": "",
        "deadline": "",
        "time_limit": "",
        "max_attempts": 1,
        "bank_question_count": 0,
        "bank_topic_id": "",
        "bank_difficulty": "any",
        "is_active": 1,
    }
    return render_template("tests/test_form.html", test=empty_test, topics=topics, page_title_key="create_test")


@testing_bp.route("/<int:test_id>")
@teacher_required
def test_detail(test_id: int):
    test = _fetch_teacher_test(test_id)
    if test is None:
        flash(_tr("test_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))

    questions = _fetch_questions_with_options(test_id)
    recent_attempts = _fetch_recent_attempts(test_id)
    question_performance = _fetch_question_performance(test_id)
    completion_rate = _completion_rate(test["assigned_students"], test["completed_students"])
    qr_relative_path = _write_qr_code(test["token"])
    public_url = url_for("testing.public_test_start", token=test["token"], _external=True)
    return render_template(
        "tests/test_detail.html",
        test=test,
        questions=questions,
        recent_attempts=recent_attempts,
        question_performance=question_performance,
        completion_rate=completion_rate,
        qr_relative_path=qr_relative_path,
        public_url=public_url,
    )


@testing_bp.route("/<int:test_id>/edit", methods=["GET", "POST"])
@teacher_required
def edit_test(test_id: int):
    test = _fetch_teacher_test(test_id)
    if test is None:
        flash(_tr("test_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))
    topics = _fetch_teacher_topics()

    if request.method == "POST":
        form_data, errors = _validate_test_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "tests/test_form.html",
                test=form_data,
                topics=topics,
                page_title_key="edit_test",
            )

        _db().execute(
            """
            UPDATE tests
            SET title = ?, description = ?, subject = ?, assigned_group = ?, deadline = ?, time_limit = ?, max_attempts = ?, is_active = ?
            WHERE id = ? AND created_by = ?
            """,
            (
                form_data["title"],
                form_data["description"],
                form_data["subject"],
                form_data["assigned_group"] or None,
                form_data["deadline"] or None,
                form_data["time_limit"] or None,
                form_data["max_attempts"],
                form_data["is_active"],
                test_id,
                session["user_id"],
            ),
        )
        auto_added = _add_random_questions_from_bank(
            test_id=test_id,
            subject=form_data["subject"],
            topic_id=form_data["bank_topic_id"] if form_data["bank_topic_id"] else None,
            difficulty=form_data["bank_difficulty"],
            count=int(form_data["bank_question_count"]),
        )
        _db().commit()
        _write_qr_code(test["token"])
        _log_activity(
            action="test_update",
            entity_type="test",
            entity_id=test_id,
            details=f"title={form_data['title']};auto_questions={auto_added}",
        )
        flash(_tr("test_updated_successfully"), "success")
        if int(form_data["bank_question_count"]) > 0 and auto_added == 0:
            flash("Подходящие элементы банка вопросов для автогенерации не найдены.", "warning")
        elif auto_added > 0:
            flash(f"Добавлено вопросов из банка: {auto_added}.", "info")
        return redirect(url_for("testing.test_detail", test_id=test_id))

    test_payload = {
        "title": test["title"],
        "description": test["description"] or "",
        "subject": test["subject"],
        "assigned_group": test["assigned_group"] or "",
        "deadline": test["deadline"] or "",
        "time_limit": test["time_limit"] or "",
        "max_attempts": test["max_attempts"] or 1,
        "bank_question_count": 0,
        "bank_topic_id": "",
        "bank_difficulty": "any",
        "is_active": test["is_active"],
    }
    return render_template("tests/test_form.html", test=test_payload, topics=topics, page_title_key="edit_test")


@testing_bp.route("/<int:test_id>/delete", methods=["POST"])
@teacher_required
def delete_test(test_id: int):
    test = _fetch_teacher_test(test_id)
    if test is None:
        flash(_tr("test_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))

    _db().execute("DELETE FROM tests WHERE id = ? AND created_by = ?", (test_id, session["user_id"]))
    _db().commit()
    _delete_qr_code(test["token"])
    _log_activity(action="test_delete", entity_type="test", entity_id=test_id, details=f"title={test['title']}")
    flash(_tr("test_deleted_successfully"), "info")
    return redirect(url_for("testing.manage_tests"))


@testing_bp.route("/<int:test_id>/questions/create", methods=["GET", "POST"])
@teacher_required
def create_question(test_id: int):
    test = _fetch_teacher_test(test_id)
    if test is None:
        flash(_tr("test_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))

    if request.method == "POST":
        form_data, errors = _validate_question_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "tests/question_form.html",
                question=form_data,
                page_title_key="add_question",
                test=test,
            )

        sort_order = test["question_count"] + 1
        cursor = _db().execute(
            """
            INSERT INTO test_questions (test_id, question_text, points, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (test_id, form_data["question_text"], form_data["points"], sort_order),
        )
        question_id = cursor.lastrowid
        _save_question_options(question_id, form_data["options"], form_data["correct_option"])
        _db().commit()
        _log_activity(action="test_question_create", entity_type="test_question", entity_id=question_id, details=f"test_id={test_id}")
        flash(_tr("question_created_successfully"), "success")
        return redirect(url_for("testing.test_detail", test_id=test_id))

    empty_question = {
        "question_text": "",
        "points": 1,
        "options": ["", "", "", ""],
        "correct_option": 1,
    }
    return render_template(
        "tests/question_form.html",
        question=empty_question,
        page_title_key="add_question",
        test=test,
    )


@testing_bp.route("/questions/<int:question_id>/edit", methods=["GET", "POST"])
@teacher_required
def edit_question(question_id: int):
    question_payload = _fetch_question_payload(question_id)
    if question_payload is None:
        flash(_tr("question_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))

    question = question_payload["question"]
    test = _fetch_teacher_test(question["test_id"])
    if test is None:
        flash(_tr("test_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))

    if request.method == "POST":
        form_data, errors = _validate_question_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "tests/question_form.html",
                question=form_data,
                page_title_key="edit_question",
                test=test,
            )

        _db().execute(
            """
            UPDATE test_questions
            SET question_text = ?, points = ?
            WHERE id = ?
            """,
            (form_data["question_text"], form_data["points"], question_id),
        )
        _save_question_options(question_id, form_data["options"], form_data["correct_option"])
        _db().commit()
        _log_activity(
            action="test_question_update",
            entity_type="test_question",
            entity_id=question_id,
            details=f"test_id={question['test_id']}",
        )
        flash(_tr("question_updated_successfully"), "success")
        return redirect(url_for("testing.test_detail", test_id=question["test_id"]))

    question_form = {
        "question_text": question["question_text"],
        "points": question["points"],
        "options": [option["option_text"] for option in question_payload["options"]],
        "correct_option": int(question_payload["correct_option"]),
    }
    return render_template(
        "tests/question_form.html",
        question=question_form,
        page_title_key="edit_question",
        test=test,
    )


@testing_bp.route("/questions/<int:question_id>/delete", methods=["POST"])
@teacher_required
def delete_question(question_id: int):
    question = _fetch_question(question_id)
    if question is None:
        flash(_tr("question_not_found"), "danger")
        return redirect(url_for("testing.manage_tests"))

    _db().execute("DELETE FROM test_questions WHERE id = ?", (question_id,))
    _db().commit()
    _log_activity(
        action="test_question_delete",
        entity_type="test_question",
        entity_id=question_id,
        details=f"test_id={question['test_id']}",
    )
    flash(_tr("question_deleted_successfully"), "info")
    return redirect(url_for("testing.test_detail", test_id=question["test_id"]))


@testing_bp.route("/results")
@teacher_required
def results_dashboard():
    test_id_filter = request.args.get("test_id", "").strip()
    subject_filter = request.args.get("subject", "").strip()
    results_data = _fetch_results_data(test_id_filter, subject_filter)
    scoped_tests = _fetch_teacher_tests(subject_filter)
    if test_id_filter:
        scoped_tests = [test for test in scoped_tests if str(test["id"]) == test_id_filter]
    completion_values = [_completion_rate(test["assigned_students"], test["completed_students"]) for test in scoped_tests]
    results_data["summary"]["completion_rate"] = round(sum(completion_values) / len(completion_values), 1) if completion_values else 0.0
    return render_template(
        "tests/results_dashboard.html",
        attempts=results_data["attempts"],
        summary=results_data["summary"],
        tests=_fetch_teacher_tests(),
        subjects=_fetch_teacher_subjects(),
        selected_test_id=test_id_filter,
        selected_subject=subject_filter,
    )


@testing_bp.route("/results/export.csv")
@teacher_required
def export_results_csv():
    test_id_filter = request.args.get("test_id", "").strip()
    subject_filter = request.args.get("subject", "").strip()
    results_data = _fetch_results_data(test_id_filter, subject_filter)
    rows: list[list[object]] = [
        ["Student", "Group", "Test", "Subject", "Attempt #", "Score", "Percentage", "Submitted At"]
    ]
    for attempt in results_data["attempts"]:
        rows.append(
            [
                attempt["student_name"],
                attempt["student_group"],
                attempt["test_title"],
                attempt["test_subject"],
                attempt["attempt_number"] if "attempt_number" in attempt.keys() else "",
                attempt["score"],
                attempt["percentage"],
                attempt["submitted_at"],
            ]
        )
    return _csv_response(f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}", rows)


@testing_bp.route("/results/report")
@teacher_required
def results_report():
    test_id_filter = request.args.get("test_id", "").strip()
    subject_filter = request.args.get("subject", "").strip()
    results_data = _fetch_results_data(test_id_filter, subject_filter)
    return render_template(
        "tests/results_report.html",
        attempts=results_data["attempts"],
        summary=results_data["summary"],
        selected_test_id=test_id_filter,
        selected_subject=subject_filter,
    )


@testing_bp.route("/journal")
@teacher_required
def student_journal():
    group_filter = request.args.get("group", "").strip()
    test_id_filter = request.args.get("test_id", "").strip()
    rows = _fetch_journal_rows(group_filter, test_id_filter)
    groups = _db().execute(
        "SELECT DISTINCT group_name FROM users WHERE role = 'student' AND group_name IS NOT NULL AND group_name != '' ORDER BY group_name COLLATE NOCASE ASC"
    ).fetchall()
    return render_template(
        "tests/student_journal.html",
        rows=rows,
        groups=[row["group_name"] for row in groups],
        tests=_fetch_teacher_tests(),
        selected_group=group_filter,
        selected_test_id=test_id_filter,
    )


@testing_bp.route("/journal/export.csv")
@teacher_required
def export_student_journal_csv():
    group_filter = request.args.get("group", "").strip()
    test_id_filter = request.args.get("test_id", "").strip()
    rows = _fetch_journal_rows(group_filter, test_id_filter)
    csv_rows: list[list[object]] = [
        ["Student", "Group", "Test", "Subject", "Attempts", "Best Score (%)", "Average Score (%)", "Last Submission"]
    ]
    for row in rows:
        csv_rows.append(
            [
                row["student_name"],
                row["student_group"] or "",
                row["test_title"],
                row["test_subject"],
                row["attempts_count"],
                row["best_score"],
                row["average_score"],
                row["last_submitted_at"] or "",
            ]
        )
    return _csv_response(f"student_journal_{datetime.now().strftime('%Y%m%d_%H%M%S')}", csv_rows)


@testing_bp.route("/activity-logs")
@teacher_required
def activity_logs():
    action_filter = request.args.get("action", "").strip()
    rows = _fetch_activity_logs(action_filter)
    actions = sorted({row["action"] for row in rows if row["action"]})
    return render_template(
        "tests/activity_logs.html",
        rows=rows,
        actions=actions,
        selected_action=action_filter,
    )


@testing_bp.route("/access/<token>", methods=["GET", "POST"])
@student_required
def public_test_start(token: str):
    test = _fetch_public_test(token)
    test_session = _get_test_session(token)
    if test_session and test_session.get("user_id") != str(session["user_id"]):
        _clear_test_session(token)
        test_session = None
    access_reason = _public_access_reason(test, test_session)
    attempt_blocked = False
    attempts_used = 0
    max_attempts = 1
    if test is not None:
        attempt_blocked, attempts_used, max_attempts = _attempt_limit_reached(test, session["user_id"])

    student = {
        "student_name": g.user["name"],
        "student_group": (g.user["group_name"] or "").strip(),
        "student_identifier": g.user["email"],
        "user_id": str(g.user["id"]),
    }

    if request.method == "POST":
        if access_reason is not None:
            flash(_tr(access_reason), "danger")
            return redirect(url_for("testing.public_test_start", token=token))
        if attempt_blocked:
            flash(f"Достигнут лимит попыток ({attempts_used}/{max_attempts}).", "warning")
            return redirect(url_for("testing.assigned_tests"))
        student["started_at"] = _now_stamp()
        student["session_nonce"] = secrets.token_urlsafe(10)
        _set_test_session(token, student)
        _log_activity(
            action="test_start",
            entity_type="test",
            entity_id=test["id"] if test is not None else None,
            details=f"attempt={attempts_used + 1}/{max_attempts}",
            user_id=session["user_id"],
            role="student",
        )
        return redirect(url_for("testing.public_test_take", token=token))

    return render_template(
        "tests/student_start.html",
        test=test,
        student=student,
        access_reason=access_reason,
        attempt_blocked=attempt_blocked,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
        existing_session=test_session,
    )


@testing_bp.route("/access/<token>/take", methods=["GET", "POST"])
@student_required
def public_test_take(token: str):
    test = _fetch_public_test(token)
    test_session = _get_test_session(token)
    if test is None:
        flash(_tr("test_not_found"), "danger")
        return redirect(url_for("home"))
    if test_session and test_session.get("user_id") != str(session["user_id"]):
        _clear_test_session(token)
        test_session = None
    if test_session is None:
        flash(_tr("test_session_missing"), "warning")
        return redirect(url_for("testing.public_test_start", token=token))

    access_reason = _public_access_reason(test, test_session)
    if access_reason is not None:
        flash(_tr(access_reason), "danger")
        return redirect(url_for("testing.public_test_start", token=token))
    attempt_blocked, attempts_used, max_attempts = _attempt_limit_reached(test, session["user_id"])
    if attempt_blocked:
        _clear_test_session(token)
        flash(f"Достигнут лимит попыток ({attempts_used}/{max_attempts}).", "warning")
        return redirect(url_for("testing.assigned_tests"))

    questions = _shuffle_questions_for_session(token, _fetch_questions_with_options(test["id"]))
    remaining_seconds = _remaining_seconds(test, test_session)

    if request.method == "POST":
        session_nonce = request.form.get("session_nonce", "").strip()
        if session_nonce != (test_session.get("session_nonce") or ""):
            flash("Ваша тестовая сессия изменилась. Пожалуйста, начните тест заново.", "warning")
            _clear_test_session(token)
            return redirect(url_for("testing.public_test_start", token=token))

        submitted_answers = {
            str(question["id"]): request.form.get(f"question_{question['id']}", "")
            for question in questions
        }
        evaluation = _evaluate_answers(questions, submitted_answers)
        result_token = _store_attempt(
            test,
            test_session,
            evaluation,
            test_session.get("started_at"),
            session["user_id"],
        )
        _clear_test_session(token)
        if remaining_seconds is not None and remaining_seconds <= 0:
            flash(_tr("test_time_expired_auto"), "warning")
        else:
            flash(_tr("test_submission_successful"), "success")
        return redirect(url_for("testing.public_test_result", token=token, result_token=result_token))

    if remaining_seconds is not None and remaining_seconds <= 0:
        evaluation = _evaluate_answers(questions, {})
        result_token = _store_attempt(
            test,
            test_session,
            evaluation,
            test_session.get("started_at"),
            session["user_id"],
        )
        _clear_test_session(token)
        flash(_tr("test_time_expired_auto"), "warning")
        return redirect(url_for("testing.public_test_result", token=token, result_token=result_token))

    return render_template(
        "tests/student_take.html",
        test=test,
        questions=questions,
        student=test_session,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
        remaining_seconds=remaining_seconds,
    )


@testing_bp.route("/access/<token>/result/<result_token>")
@auth_required
def public_test_result(token: str, result_token: str):
    payload = _fetch_attempt_review(token, result_token)
    if payload is None:
        flash(_tr("result_not_found"), "danger")
        return redirect(url_for("home"))

    attempt = payload["attempt"]
    current_role = session.get("role")
    if current_role == "teacher" and attempt["teacher_id"] != session["user_id"]:
        flash(_tr("teacher_only_access"), "danger")
        return redirect(url_for("dashboard"))
    if current_role == "student" and attempt["user_id"] != session["user_id"]:
        flash(_tr("student_only_access"), "danger")
        return redirect(url_for("dashboard"))

    can_retake = False
    if current_role == "student":
        test_row = _fetch_public_test(token)
        if test_row is not None:
            blocked, _, _ = _attempt_limit_reached(test_row, session["user_id"])
            can_retake = not blocked

    return render_template(
        "tests/student_result.html",
        attempt=attempt,
        answers=payload["answers"],
        test_token=token,
        can_retake=can_retake,
    )
