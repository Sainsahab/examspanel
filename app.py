import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from db import (
    create_exam as db_create_exam,
    create_note,
    create_user,
    delete_exam as db_delete_exam,
    delete_note,
    dismiss_reminder,
    generate_todays_reminders_for_user,
    get_dashboard_data,
    get_exam_subjects,
    get_exams,
    get_note_subjects,
    get_notes_api_rows,
    get_notes,
    get_user_by_email,
    get_user_by_id,
    update_user_image,
    update_user_profile,
)
from google_calendar import add_event_to_calendar

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_PRIORITIES = {"low", "medium", "high"}


def format_due_text(due):
    if not due:
        return ""

    try:
        return datetime.strptime(due, "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return due


def attach_and_filter_rows(rows, due_field="due_text"):
    filtered_rows = []
    today = date.today()

    for row in rows:
        due_dt = None
        due_text = (row.get(due_field) or "").strip()

        for prefix in ("Due:", "Due -", "Due", "due:", "due -"):
            if due_text.startswith(prefix):
                due_text = due_text[len(prefix):].strip()
                break

        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                due_dt = datetime.strptime(due_text, fmt).date()
                break
            except ValueError:
                continue

        if due_dt is None:
            row["days_left"] = None
            filtered_rows.append(row)
            continue

        days_left = (due_dt - today).days
        if days_left >= 1:
            row["days_left"] = days_left
            filtered_rows.append(row)

    return filtered_rows


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/loginregister")
def loginregister():
    return render_template("LoginRegister.html")


@app.route("/register", methods=["POST"])
def register():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    try:
        existing = get_user_by_email(email)
        if existing:
            flash("Email already exists!", "warning")
            return redirect("/")

        create_user(name, email, password)
    except Exception as e:
        print("DB register error:", e)
        flash("Registration failed. Please try again.", "danger")
        return redirect("/")

    flash("Registration successful! You can now login.", "success")
    return redirect("/")


@app.route("/login_page", methods=["GET"])
def login_page():
    return render_template("Login.html")


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template("Login.html", message=("error", "Please provide email and password."))

    try:
        user = get_user_by_email(email)
    except Exception as e:
        print("DB login error:", e)
        return render_template("Login.html", message=("error", "Unable to login right now."))

    if user and user["password"] == password:
        session["user"] = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
        }
        return render_template("Dashboard.html", name=user["name"])

    return render_template("Login.html", message=("error", "Invalid email or password."))


@app.route("/profile", methods=["GET"])
def profile():
    if "user" not in session:
        flash("Please log in to access your profile.", "warning")
        return redirect(url_for("login_page"))

    try:
        user = get_user_by_id(session["user"]["id"])
    except Exception as e:
        print("Profile DB error:", e)
        flash("Unable to load profile.", "danger")
        return redirect(url_for("login_page"))

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login_page"))

    return render_template("Profile.html", user=user)


@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login_page"))

    user_id = session["user"]["id"]
    full_name = request.form.get("fullName")
    email = request.form.get("email")
    contact = request.form.get("contact")
    password = request.form.get("newPassword")

    try:
        update_user_profile(user_id, full_name, email, contact, password)
    except Exception as e:
        print("Update profile DB error:", e)
        flash("Profile update failed.", "danger")
        return redirect(url_for("profile"))

    session["user"]["name"] = full_name
    session["user"]["email"] = email

    flash("Profile updated successfully!", "success")
    return redirect(url_for("profile"))


@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login_page"))

    user_id = session["user"]["id"]
    file = request.files.get("avatarInput")

    if not file or file.filename == "":
        flash("No image selected.", "warning")
        return redirect(url_for("profile"))

    filename = secure_filename(file.filename)
    filename = f"user_{user_id}_{filename}"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    try:
        update_user_image(user_id, filename)
    except Exception as e:
        print("Update image DB error:", e)
        flash("Could not update profile picture.", "danger")
        return redirect(url_for("profile"))

    session["user"]["image"] = filename

    flash("Profile picture updated successfully!", "success")
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login_page"))


@app.route("/tasks/create", methods=["POST"])
def create_task():
    if "user" not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))

    data = request.get_json(silent=True) or request.form.to_dict()
    subject = (data.get("subject") or "General").strip()
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    due = data.get("due")
    reminder = str(data.get("reminder", "no")).lower() in ("yes", "true", "1")
    priority = (data.get("priority") or "medium").lower()

    if priority not in ALLOWED_PRIORITIES:
        priority = "medium"

    if not title or not description:
        if request.is_json:
            return jsonify({"error": "Title and description required"}), 400
        flash("Title & description required!", "warning")
        return redirect(url_for("notes"))

    try:
        create_note(
            session["user"]["id"],
            title,
            subject,
            description,
            format_due_text(due),
            reminder,
            priority,
        )
    except Exception as e:
        print("DB note create error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Database error!", "danger")
        return redirect(url_for("notes"))

    if request.is_json:
        return jsonify({"success": True}), 201

    flash("Task created!", "success")
    return redirect(url_for("notes"))


@app.route("/notes")
def notes():
    if "user" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))

    user_id = session["user"]["id"]
    search = request.args.get("search", "").strip()
    subject_filter = request.args.get("subject", "").strip()

    try:
        notes_rows = get_notes(user_id, search, subject_filter)
        subjects = get_note_subjects(user_id)
    except Exception as e:
        print("DB notes error:", e)
        notes_rows = []
        subjects = []

    return render_template(
        "Notes.html",
        notes=notes_rows,
        subjects=subjects,
        search=search,
        subject_selected=subject_filter,
    )


@app.route("/tasks/delete", methods=["POST"])
def delete_task():
    if "user" not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))

    data = request.get_json(silent=True)
    note_id = data.get("note_id") if data else request.form.get("note_id")

    if not note_id:
        if request.is_json:
            return jsonify({"error": "note_id required"}), 400
        flash("Missing note_id.", "warning")
        return redirect(url_for("notes"))

    try:
        delete_note(note_id, session["user"]["id"])
    except Exception as e:
        print("Delete note error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Error deleting task.", "danger")
        return redirect(url_for("notes"))

    if request.is_json:
        return jsonify({"success": True}), 200

    flash("Task deleted.", "success")
    return redirect(url_for("notes"))


@app.route("/tasks/list")
def tasks_list():
    if "user" not in session:
        return jsonify([]), 401

    try:
        rows = get_notes_api_rows(
            session["user"]["id"],
            request.args.get("search", "").strip(),
            request.args.get("subject", "").strip(),
        )
    except Exception as e:
        print("tasks_list DB error:", e)
        rows = []

    out = []
    for row in rows:
        out.append(
            {
                "note_id": row.get("note_id"),
                "title": row.get("title") or "",
                "subject": row.get("subject") or "",
                "description": row.get("description") or "",
                "due_text": row.get("due_text") or "",
            }
        )

    return jsonify(out)


@app.route("/tasks/new")
def new_task():
    if "user" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))
    return render_template("AddTask.html")


@app.route("/exams")
def exams():
    if "user" not in session:
        flash("Please log in to access exams.", "warning")
        return redirect(url_for("login_page"))

    user_id = session["user"]["id"]
    search = request.args.get("search", "").strip()
    subject_filter = request.args.get("subject", "").strip()

    try:
        exams_rows = get_exams(user_id, search, subject_filter)
        subjects = get_exam_subjects(user_id)
    except Exception as e:
        print("Exams read error:", e)
        exams_rows = []
        subjects = []

    return render_template(
        "Exam.html",
        exams=exams_rows,
        subjects=subjects,
        search=search,
        subject_selected=subject_filter,
    )


@app.route("/exams/new")
def new_exam():
    if "user" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))
    return render_template("AddExam.html")


@app.route("/exams/create", methods=["POST"])
def create_exam():
    if "user" not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))

    data = request.get_json(silent=True) or request.form.to_dict()
    subject = (data.get("subject") or "General").strip()
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    due = data.get("due")
    reminder = str(data.get("reminder", "no")).lower() in ("yes", "true", "1", "y")
    priority = (data.get("priority") or "medium").lower()

    if priority not in ALLOWED_PRIORITIES:
        priority = "medium"

    if not title or not description:
        if request.is_json:
            return jsonify({"error": "Title and description required"}), 400
        flash("Title and description required!", "warning")
        return redirect(url_for("exams"))

    due_text = format_due_text(due)

    try:
        db_create_exam(
            session["user"]["id"],
            title,
            subject,
            description,
            due_text,
            reminder,
            priority,
        )
    except Exception as e:
        print("DB insert exam error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Database error creating exam.", "danger")
        return redirect(url_for("exams"))

    if due:
        try:
            start_dt = datetime.strptime(due, "%Y-%m-%d").replace(hour=9, minute=0)
            end_dt = start_dt + timedelta(hours=1)
            add_event_to_calendar(
                title=f"Exam: {title}",
                description=description,
                start_date=start_dt,
                end_date=end_dt,
            )
        except Exception as e:
            print("Google Calendar error:", e)

    if request.is_json:
        return jsonify({"success": True}), 201

    flash("Exam created!", "success")
    return redirect(url_for("exams"))


@app.route("/exams/delete", methods=["POST"])
def delete_exam():
    if "user" not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for("login_page"))

    data = request.get_json(silent=True)
    exam_id = data.get("exam_id") if data else request.form.get("exam_id")

    if not exam_id:
        if request.is_json:
            return jsonify({"error": "exam_id required"}), 400
        flash("Missing exam_id.", "warning")
        return redirect(url_for("exams"))

    try:
        db_delete_exam(exam_id, session["user"]["id"])
    except Exception as e:
        print("DB delete exam error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Error deleting exam.", "danger")
        return redirect(url_for("exams"))

    if request.is_json:
        return jsonify({"success": True}), 200

    flash("Exam deleted.", "success")
    return redirect(url_for("exams"))


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    search = request.args.get("search", "").strip()
    subject = request.args.get("subject", "").strip()

    try:
        notes_rows, exams_rows, subjects = get_dashboard_data(user_id, search, subject)
    except Exception as e:
        print("Dashboard DB error:", e)
        notes_rows, exams_rows, subjects = [], [], set()

    notes_rows = attach_and_filter_rows(notes_rows, due_field="due_text")
    exams_rows = attach_and_filter_rows(exams_rows, due_field="due_text")

    return render_template(
        "Dashboard.html",
        notes=notes_rows,
        exams=exams_rows,
        all_subjects=sorted(subjects),
    )


@app.route("/reminders", methods=["GET"])
def reminders():
    if "user" not in session:
        flash("Please log in to access reminders.", "warning")
        return redirect(url_for("login_page"))

    try:
        reminders_today = generate_todays_reminders_for_user(session["user"]["id"])
    except Exception as e:
        print("Reminder DB error:", e)
        reminders_today = []

    return render_template("Reminder.html", reminders=reminders_today)


@app.route("/reminders/delete", methods=["POST"])
def reminders_delete():
    if "user" not in session:
        return jsonify({"error": "Authentication required"}), 401

    reminder_id = request.form.get("reminder_id") or (request.json and request.json.get("reminder_id"))
    if not reminder_id:
        return jsonify({"error": "reminder_id required"}), 400

    try:
        found = dismiss_reminder(reminder_id, session["user"]["id"], date.today())
    except Exception as e:
        print("Error dismissing reminder:", e)
        return jsonify({"error": "Database error"}), 500

    if not found:
        return jsonify({"error": "Reminder not found or not for today"}), 404

    if request.form:
        flash("Reminder dismissed.", "info")
        return redirect(url_for("reminders"))

    return jsonify({"success": True}), 200


if __name__ == "__main__":
    app.run(debug=True)
