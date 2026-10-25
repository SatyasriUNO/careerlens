"""
db.py  —  Member 5. Saves finished interview reports in SQLite (data/careerlens.db).

Functions:
    init_db()
    save_report(session_id, role, report)
    list_history(limit=50)  -> [{session_id, date, role, scores}]
    get_report(session_id)  -> full report dict or None

Test:  python db.py
"""

import json
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "careerlens.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                session_id  TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                role        TEXT,
                scores_json TEXT,
                report_json TEXT NOT NULL
            )
            """
        )


def save_report(session_id, role, report):
    scores = report.get("scores", {}) if isinstance(report, dict) else {}
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reports (session_id, created_at, role, scores_json, report_json) VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                role,
                json.dumps(scores),
                json.dumps(report),
            ),
        )


def list_history(limit=50):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session_id, created_at, role, scores_json FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    history = []
    for row in rows:
        try:
            scores = json.loads(row["scores_json"] or "{}")
        except json.JSONDecodeError:
            scores = {}
        history.append({"session_id": row["session_id"], "date": row["created_at"], "role": row["role"], "scores": scores})
    return history


def get_report(session_id):
    with _connect() as conn:
        row = conn.execute("SELECT report_json FROM reports WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["report_json"])
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    init_db()
    save_report("s_test", "SDE", {"scores": {"communication": 70, "confidence": None, "technical": 65, "resume": 72}})
    print(list_history())
    print(get_report("s_test"))
    with _connect() as conn:
        conn.execute("DELETE FROM reports WHERE session_id = 's_test'")
    print("Test row removed. db.py works.")
