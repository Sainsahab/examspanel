import os
from datetime import date, datetime

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 3306)),
    )


def get_user_by_email(email):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM loginregister WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        cur.close()
        con.close()


def create_user(name, email, password):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute(
            "INSERT INTO loginregister (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password),
        )
        con.commit()
    finally:
        cur.close()
        con.close()


def get_user_by_id(user_id):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id, name, email, contact, image FROM loginregister WHERE id = %s",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        con.close()


def update_user_profile(user_id, full_name, email, contact, password):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE loginregister
            SET name=%s, email=%s, contact=%s, password=%s
            WHERE id=%s
            """,
            (full_name, email, contact, password, user_id),
        )
        con.commit()
    finally:
        cur.close()
        con.close()


def update_user_image(user_id, filename):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute(
            "UPDATE loginregister SET image = %s WHERE id = %s",
            (filename, user_id),
        )
        con.commit()
    finally:
        cur.close()
        con.close()


def create_note(user_id, title, subject, description, due_text, reminder, priority):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute(
            """
            INSERT INTO notes (id, title, subject, description, due_text, reminder, priority)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, title, subject, description, due_text, reminder, priority),
        )
        con.commit()
    finally:
        cur.close()
        con.close()


def get_notes(user_id, search="", subject_filter=""):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        sql = "SELECT * FROM notes WHERE id=%s"
        params = [user_id]

        if search:
            sql += " AND (title LIKE %s OR description LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like])

        if subject_filter:
            sql += " AND subject=%s"
            params.append(subject_filter)

        sql += " ORDER BY note_id DESC"

        cur.execute(sql, tuple(params))
        return cur.fetchall() or []
    finally:
        cur.close()
        con.close()


def get_note_subjects(user_id):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        cur.execute("SELECT DISTINCT subject FROM notes WHERE id=%s", (user_id,))
        return [row["subject"] for row in cur.fetchall() if row.get("subject")]
    finally:
        cur.close()
        con.close()


def delete_note(note_id, user_id):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute("DELETE FROM notes WHERE note_id=%s AND id=%s", (note_id, user_id))
        con.commit()
    finally:
        cur.close()
        con.close()


def get_notes_api_rows(user_id, search="", subject=""):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        sql = "SELECT note_id, title, subject, description, due_text FROM notes WHERE id = %s"
        params = [user_id]

        if search:
            sql += " AND (title LIKE %s OR description LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like])

        if subject:
            sql += " AND subject = %s"
            params.append(subject)

        sql += " ORDER BY note_id DESC"

        cur.execute(sql, tuple(params))
        return cur.fetchall() or []
    finally:
        cur.close()
        con.close()


def create_exam(user_id, title, subject, description, due_text, reminder, priority):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute(
            """
            INSERT INTO exams (id, title, subject, description, due_text, reminder, priority)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, title, subject, description, due_text, reminder, priority),
        )
        con.commit()
    finally:
        cur.close()
        con.close()


def get_exams(user_id, search="", subject_filter=""):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        sql = """
            SELECT exam_id, title, subject, description, due_text, reminder, priority
            FROM exams
            WHERE id=%s
        """
        params = [user_id]

        if search:
            sql += " AND (title LIKE %s OR description LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like])

        if subject_filter:
            sql += " AND subject=%s"
            params.append(subject_filter)

        sql += " ORDER BY exam_id DESC"

        cur.execute(sql, tuple(params))
        return cur.fetchall() or []
    finally:
        cur.close()
        con.close()


def get_exam_subjects(user_id):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        cur.execute("SELECT DISTINCT subject FROM exams WHERE id=%s", (user_id,))
        return [row["subject"] for row in cur.fetchall() if row.get("subject")]
    finally:
        cur.close()
        con.close()


def delete_exam(exam_id, user_id):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute("DELETE FROM exams WHERE exam_id=%s AND id=%s", (exam_id, user_id))
        con.commit()
    finally:
        cur.close()
        con.close()


def get_dashboard_data(user_id, search="", subject=""):
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        notes_sql = "SELECT * FROM notes WHERE id = %s"
        exams_sql = "SELECT * FROM exams WHERE id = %s"
        params_notes = [user_id]
        params_exams = [user_id]

        if search:
            like = f"%{search}%"
            notes_sql += " AND (title LIKE %s OR description LIKE %s)"
            exams_sql += " AND (title LIKE %s OR description LIKE %s)"
            params_notes.extend([like, like])
            params_exams.extend([like, like])

        if subject:
            notes_sql += " AND subject = %s"
            exams_sql += " AND subject = %s"
            params_notes.append(subject)
            params_exams.append(subject)

        notes_sql += " ORDER BY note_id DESC"
        exams_sql += " ORDER BY exam_id DESC"

        cur.execute(notes_sql, tuple(params_notes))
        notes_rows = cur.fetchall() or []

        cur.execute(exams_sql, tuple(params_exams))
        exams_rows = cur.fetchall() or []

        subjects = {row["subject"] for row in notes_rows + exams_rows if row.get("subject")}
        return notes_rows, exams_rows, subjects
    finally:
        cur.close()
        con.close()


def parse_due_date_from_text(text):
    if not text:
        return None

    clean_text = text.strip()
    for prefix in ("Due:", "Due -", "Due", "due:", "due -"):
        if clean_text.startswith(prefix):
            clean_text = clean_text[len(prefix):].strip()
            break

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(clean_text, fmt).date()
        except ValueError:
            continue

    return None


def generate_todays_reminders_for_user(user_id):
    today = date.today()
    con = get_connection()
    cur = con.cursor(dictionary=True)
    try:
        cur.execute(
            "DELETE FROM reminders WHERE user_id = %s AND reminder_date < %s",
            (user_id, today),
        )
        con.commit()

        cur.execute(
            """
            SELECT note_id AS id, title, subject, description, due_text, 'notes' AS src
            FROM notes
            WHERE id = %s
            """,
            (user_id,),
        )
        notes = cur.fetchall() or []

        cur.execute(
            """
            SELECT exam_id AS id, title, subject, description, due_text, 'exams' AS src
            FROM exams
            WHERE id = %s
            """,
            (user_id,),
        )
        exams = cur.fetchall() or []

        for item in notes + exams:
            due_dt = parse_due_date_from_text(item.get("due_text") or "")
            if not due_dt:
                continue

            days_left = (due_dt - today).days
            if 1 <= days_left <= 7:
                try:
                    cur.execute(
                        """
                        INSERT INTO reminders (user_id, source_table, source_id, reminder_date)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (user_id, item["src"], item["id"], today),
                    )
                    con.commit()
                except mysql.connector.Error:
                    con.rollback()

        cur.execute(
            """
            SELECT r.reminder_id, r.source_table, r.source_id, r.reminder_date, r.dismissed,
                   COALESCE(n.title, e.title) AS title,
                   COALESCE(n.subject, e.subject) AS subject,
                   COALESCE(n.description, e.description) AS description,
                   COALESCE(n.due_text, e.due_text) AS due_text
            FROM reminders r
            LEFT JOIN notes n ON (r.source_table='notes' AND r.source_id = n.note_id)
            LEFT JOIN exams e ON (r.source_table='exams' AND r.source_id = e.exam_id)
            WHERE r.user_id = %s
              AND r.reminder_date = %s
              AND (r.dismissed = FALSE OR r.dismissed IS NULL)
            ORDER BY r.created_at ASC
            """,
            (user_id, today),
        )

        rows = cur.fetchall() or []
        reminders = []
        for row in rows:
            due_dt = parse_due_date_from_text(row.get("due_text") or "")
            reminders.append(
                {
                    "reminder_id": row.get("reminder_id"),
                    "source_table": row.get("source_table"),
                    "source_id": row.get("source_id"),
                    "title": row.get("title") or "(no title)",
                    "subject": row.get("subject") or "",
                    "description": row.get("description") or "",
                    "due_text": row.get("due_text") or "",
                    "days_left": (due_dt - today).days if due_dt else None,
                }
            )

        return reminders
    finally:
        cur.close()
        con.close()


def dismiss_reminder(reminder_id, user_id, reminder_date):
    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT reminder_id
            FROM reminders
            WHERE reminder_id=%s AND user_id=%s AND reminder_date=%s
            """,
            (reminder_id, user_id, reminder_date),
        )
        if not cur.fetchone():
            return False

        cur.execute(
            "UPDATE reminders SET dismissed = TRUE WHERE reminder_id = %s",
            (reminder_id,),
        )
        con.commit()
        return True
    finally:
        cur.close()
        con.close()
