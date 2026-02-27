from flask import Flask, render_template, request, redirect, flash, session, url_for, jsonify
from datetime import datetime, date , timedelta
import mysql.connector
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os
from google_calendar import add_event_to_calendar   

load_dotenv() 

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
#===== Database Connection =====

def get_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 3306))
    )



# ===== Login & Register Screen (LoginRegister.html + Login.html) =====


# ===== Register Screen (LoginRegister.html) =====
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/loginregister')
def loginregister():
    return render_template('LoginRegister.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']

    con = get_connection()
    cur = con.cursor()
    try:
        cur.execute("SELECT * FROM loginregister WHERE email=%s", (email,))
        existing = cur.fetchone()
        if existing:
            flash("Email already exists!", "warning")
            return redirect('/')

        cur.execute(
            "INSERT INTO loginregister (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )
        con.commit()
    except Exception as e:
        print("DB register error:", e)
        flash("Registration failed. Please try again.", "danger")
        return redirect('/')
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            con.close()
        except:
            pass

    flash("Registration successful! You can now login.", "success")
    return redirect('/')


# ===== Login(Login.html) =====

@app.route('/login_page', methods=['GET'])
def login_page():
    return render_template('Login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    if not email or not password:
        return render_template('Login.html', message=("error", "Please provide email and password."))
    con = get_connection()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM loginregister WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    con.close()

    if user and user['password'] == password:
        session['user'] = {
            'id': user['id'],
            'name': user['name'],
            'email': user['email']
        }

        return render_template('Dashboard.html', name=user['name'])
    else:
        return render_template('Login.html', message=("error", "Invalid email or password."))


# ===== Profile Screen (Profile.html) =====

@app.route('/profile', methods=['GET'])
def profile():
    if 'user' not in session:
        flash("Please log in to access your profile.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user']['id']

    con = get_connection()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT id, name, email, contact,image FROM loginregister WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()
    con.close()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login_page'))

    return render_template('Profile.html', user=user)


#==== Upload Profile Picture =====

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user']['id']
    full_name = request.form.get('fullName')
    email = request.form.get('email')
    contact = request.form.get('contact')
    password = request.form.get('newPassword')

    con = get_connection()
    cur = con.cursor()
    cur.execute("""
        UPDATE loginregister
        SET name=%s, email=%s, contact=%s, password=%s
        WHERE id=%s
    """, (full_name, email, contact, password, user_id))
    con.commit()
    cur.close()
    con.close()

    session['user']['name'] = full_name
    session['user']['email'] = email

    flash("Profile updated successfully!", "success")
    return redirect(url_for('profile'))

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


#===== Upload Profile Picture (Profile.html) =====

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user']['id']
    file = request.files.get('avatarInput')

    if not file or file.filename == '':
        flash("No image selected.", "warning")
        return redirect(url_for('profile'))

    filename = secure_filename(file.filename)
    filename = f"user_{user_id}_{filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    con = get_connection()
    cur = con.cursor()
    cur.execute("UPDATE loginregister SET image = %s WHERE id = %s", (filename, user_id))
    con.commit()
    cur.close()
    con.close()

    session['user']['image'] = filename

    flash("Profile picture updated successfully!", "success")
    return redirect(url_for('profile'))

# ===== logout =====

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('login_page'))

# ===== Tasks / Notes Screen (Notes.html + AddTask.html) =====

@app.route('/tasks/create', methods=['POST'])
def create_task():
    if 'user' not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    subject = (data.get('subject') or "General").strip()
    title = (data.get('title') or "").strip()
    description = (data.get('description') or "").strip()
    due = data.get('due')

    reminder = str(data.get('reminder', "no")).lower() in ("yes", "true", "1")
    priority = data.get('priority', "medium").lower()
    if priority not in {"low", "medium", "high"}:
        priority = "medium"

    if not title or not description:
        if request.is_json:
            return jsonify({"error": "Title and description required"}), 400
        flash("Title & description required!", "warning")
        return redirect(url_for('notes'))

    due_text = ""
    if due:
        try:
            d = datetime.strptime(due, "%Y-%m-%d")
            due_text = d.strftime("%b %d, %Y")
        except:
            due_text = due

    user_id = session['user']['id']

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO notes (id, title, subject, description, due_text, reminder, priority)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, title, subject, description, due_text, reminder, priority))
        con.commit()
    except Exception as e:
        print("DB error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Database error!", "danger")
        return redirect(url_for('notes'))
    finally:
        cur.close()
        con.close()

    if request.is_json:
        return jsonify({"success": True}), 201

    flash("Task created!", "success")
    return redirect(url_for('notes'))



#===== Tasks List Screen (Notes.html) =====

@app.route('/notes')
def notes():
    if 'user' not in session:
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user']['id']
    search = request.args.get("search", "").strip()
    subject_filter = request.args.get("subject", "").strip()

    try:
        con = get_connection()
        cur = con.cursor(dictionary=True)

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

        cur.execute(sql, params)
        notes_rows = cur.fetchall()

        cur.execute("SELECT DISTINCT subject FROM notes WHERE id=%s", (user_id,))
        subjects = [r['subject'] for r in cur.fetchall()]

    except Exception as e:
        print("DB error:", e)
        notes_rows = []
        subjects = []
    finally:
        cur.close()
        con.close()

    return render_template(
        "Notes.html",
        notes=notes_rows,
        subjects=subjects,
        search=search,
        subject_selected=subject_filter
    )


#===== Delete Task =====

@app.route('/tasks/delete', methods=['POST'])
def delete_task():
    if 'user' not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))

    data = request.get_json(silent=True)
    note_id = data.get("note_id") if data else request.form.get("note_id")
    user_id = session['user']['id']

    if not note_id:
        if request.is_json:
            return jsonify({"error": "note_id required"}), 400
        flash("Missing note_id.", "warning")
        return redirect(url_for('notes'))

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("DELETE FROM notes WHERE note_id=%s AND id=%s", (note_id, user_id))
        con.commit()
    except Exception as e:
        print("Delete error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Error deleting task.", "danger")
        return redirect(url_for('notes'))
    finally:
        cur.close()
        con.close()

    if request.is_json:
        return jsonify({"success": True}), 200

    flash("Task deleted.", "success")
    return redirect(url_for('notes'))

#===== Tasks List API =====

@app.route('/tasks/list')
def tasks_list():
    if 'user' not in session:
        return jsonify([]), 401

    user_id = session['user']['id']
    search = request.args.get('search', '').strip()
    subject = request.args.get('subject', '').strip()

    try:
        con = get_connection()
        cur = con.cursor(dictionary=True)

        base_sql = "SELECT note_id, title, subject, description, due_text FROM notes WHERE id = %s"
        params = [user_id]

        if search:
            base_sql += " AND (title LIKE %s OR description LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like])

        if subject:
            base_sql += " AND subject = %s"
            params.append(subject)

        base_sql += " ORDER BY note_id DESC"

        cur.execute(base_sql, tuple(params))
        rows = cur.fetchall()

        out = []
        for r in rows:
            out.append({
                "note_id": r.get("note_id"),
                "title": r.get("title") or "",
                "subject": r.get("subject") or "",
                "description": r.get("description") or "",
                "due_text": r.get("due_text") or ""
            })

    except Exception as e:
        print("tasks_list DB error:", e)
        out = []
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            con.close()
        except:
            pass

    return jsonify(out)

#====== New Task Screen (AddTask.html) =====
@app.route('/tasks/new')
def new_task():
    if 'user' not in session:
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))
    return render_template("AddTask.html")


# ===== Exams Screen (Exam.html + AddExam.html) =====

@app.route('/exams')
def exams():
    if 'user' not in session:
        flash("Please log in to access exams.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user']['id']
    search = request.args.get("search", "").strip()
    subject_filter = request.args.get("subject", "").strip()

    try:
        con = get_connection()
        cur = con.cursor(dictionary=True)

        sql = "SELECT exam_id, title, subject, description, due_text, reminder, priority FROM exams WHERE id=%s"
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
        exams_rows = cur.fetchall()

        cur.execute("SELECT DISTINCT subject FROM exams WHERE id=%s", (user_id,))
        subjects_rows = cur.fetchall()
        subjects = [r['subject'] for r in subjects_rows if r.get('subject')]

    except Exception as e:
        print("Exams read error:", e)
        exams_rows = []
        subjects = []
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            con.close()
        except:
            pass

    return render_template('Exam.html', exams=exams_rows, subjects=subjects, search=search, subject_selected=subject_filter)

@app.route('/exams/new')
def new_exam():
    if 'user' not in session:
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))
    return render_template('AddExam.html')

ALLOWED_PRIORITIES = {"low", "medium", "high"}


#===== Create Exam (AddExam.html) =====
@app.route('/exams/create', methods=['POST'])
def create_exam():
    if 'user' not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))

    
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    subject = (data.get('subject') or 'General').strip()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    due = data.get('due')

    reminder = str(data.get('reminder', "no")).lower() in ("yes", "true", "1", "y")
    priority = (data.get('priority') or "medium").lower()
    if priority not in ALLOWED_PRIORITIES:
        priority = "medium"

    if not title or not description:
        if request.is_json:
            return jsonify({"error": "Title and description required"}), 400
        flash("Title and description required!", "warning")
        return redirect(url_for('exams'))

    
    due_text = ''
    if due:
        try:
            d = datetime.strptime(due, '%Y-%m-%d')
            due_text = d.strftime('%b %d, %Y')
        except Exception:
            due_text = due

    user_id = session['user']['id']

    
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO exams (id, title, subject, description, due_text, reminder, priority)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, title, subject, description, due_text, reminder, priority))
        con.commit()
    except Exception as e:
        print("DB insert exam error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Database error creating exam.", "danger")
        return redirect(url_for('exams'))
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            con.close()
        except:
            pass

    
    
    if due:
        try:
            start_dt = datetime.strptime(due, "%Y-%m-%d")
            start_dt = start_dt.replace(hour=9, minute=0)  
            end_dt = start_dt + timedelta(hours=1)          

            add_event_to_calendar(
                title=f"Exam: {title}",
                description=description,
                start_date=start_dt,
                end_date=end_dt
            )
        except Exception as e:
            print("Google Calendar error:", e)

    if request.is_json:
        return jsonify({"success": True}), 201

    flash("Exam created!", "success")
    return redirect(url_for('exams'))


#===== Delete Exam =====

@app.route('/exams/delete', methods=['POST'])
def delete_exam():
    if 'user' not in session:
        if request.is_json:
            return jsonify({"error": "Authentication required"}), 401
        flash("Please log in.", "warning")
        return redirect(url_for('login_page'))

    data = request.get_json(silent=True)
    exam_id = data.get('exam_id') if data else request.form.get('exam_id')
    user_id = session['user']['id']

    if not exam_id:
        if request.is_json:
            return jsonify({"error": "exam_id required"}), 400
        flash("Missing exam_id.", "warning")
        return redirect(url_for('exams'))

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("DELETE FROM exams WHERE exam_id=%s AND id=%s", (exam_id, user_id))
        con.commit()
    except Exception as e:
        print("DB delete exam error:", e)
        if request.is_json:
            return jsonify({"error": "Database error"}), 500
        flash("Error deleting exam.", "danger")
        return redirect(url_for('exams'))
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            con.close()
        except:
            pass

    if request.is_json:
        return jsonify({"success": True}), 200

    flash("Exam deleted.", "success")
    return redirect(url_for('exams'))




# ===== Dashboard Screen (Dashboard.html) =====

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login"))

    user_id = session['user']['id']
    search = request.args.get("search", "").strip()
    subject = request.args.get("subject", "").strip()

    notes_rows = []
    exams_rows = []
    subjects = set()
    con = None
    cur = None

    try:
        con = get_connection()
        cur = con.cursor(dictionary=True)

        notes_sql = "SELECT * FROM notes WHERE id = %s"
        exams_sql = "SELECT * FROM exams WHERE id = %s"
        params_notes = [user_id]
        params_exams = [user_id]

        if search:
            notes_sql += " AND (title LIKE %s OR description LIKE %s)"
            exams_sql += " AND (title LIKE %s OR description LIKE %s)"
            like = f"%{search}%"
            params_notes += [like, like]
            params_exams += [like, like]

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

        for r in notes_rows + exams_rows:
            if r.get("subject"):
                subjects.add(r["subject"])

    except Exception as e:
        print("Dashboard DB error:", e)
        notes_rows = []
        exams_rows = []
        subjects = set()
    finally:
        try:
            if cur: cur.close()
        except:
            pass
        try:
            if con: con.close()
        except:
            pass

    def parse_due_text(text):
        if not text:
            return None
        txt = text.strip()
        for prefix in ("Due:", "Due -", "Due", "due:", "due -"):
            if txt.startswith(prefix):
                txt = txt[len(prefix):].strip()
                break
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(txt, fmt).date()
            except Exception:
                continue
        return None

    def attach_and_filter_rows(rows, due_field="due_text"):
        out = []
        today = date.today()
        for r in rows:
            due_text = r.get(due_field) or ""
            due_dt = parse_due_text(due_text)
            if due_dt is None:
                r["days_left"] = None
                out.append(r)
                continue
            days_left = (due_dt - today).days
            if days_left >= 1:
                r["days_left"] = days_left
                out.append(r)
            else:
                pass
        return out

    notes_rows = attach_and_filter_rows(notes_rows, due_field="due_text")
    exams_rows = attach_and_filter_rows(exams_rows, due_field="due_text")

    return render_template("Dashboard.html",
                           notes=notes_rows,
                           exams=exams_rows,
                           all_subjects=sorted(subjects))

def parse_due_date_from_text(text):
    if not text:
        return None
    txt = text.strip()
    for p in ("Due:", "Due -", "Due", "due:", "due -"):
        if txt.startswith(p):
            txt = txt[len(p):].strip()
            break
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except Exception:
            continue
    return None

def generate_todays_reminders_for_user(user_id):
    """
    Create reminders for tasks/exams that are 1..7 days away.
    - Deletes reminders older than today (cleanup)
    - Inserts reminder rows for today for eligible items (unique constraint avoids duplicates)
    - Returns today's non-dismissed reminders with source details
    """
    today = date.today()
    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor(dictionary=True)

        cur.execute("DELETE FROM reminders WHERE user_id = %s AND reminder_date < %s", (user_id, today))
        con.commit()

        cur.execute("SELECT note_id AS id, title, subject, description, due_text, 'notes' AS src FROM notes WHERE id = %s", (user_id,))
        notes = cur.fetchall() or []

        cur.execute("SELECT exam_id AS id, title, subject, description, due_text, 'exams' AS src FROM exams WHERE id = %s", (user_id,))
        exams = cur.fetchall() or []

        candidates = notes + exams

        for item in candidates:
            due_dt = parse_due_date_from_text(item.get("due_text") or "")
            if not due_dt:
                continue
            days_left = (due_dt - today).days
            if 1 <= days_left <= 7:
                try:
                    cur.execute(
                        "INSERT INTO reminders (user_id, source_table, source_id, reminder_date) VALUES (%s, %s, %s, %s)",
                        (user_id, item['src'], item['id'], today)
                    )
                    con.commit()
                except Exception:
                    con.rollback()
                    pass

        cur.execute("""
            SELECT r.reminder_id, r.source_table, r.source_id, r.reminder_date, r.dismissed,
                   COALESCE(n.title, e.title) AS title,
                   COALESCE(n.subject, e.subject) AS subject,
                   COALESCE(n.description, e.description) AS description,
                   COALESCE(n.due_text, e.due_text) AS due_text
            FROM reminders r
            LEFT JOIN notes n ON (r.source_table='notes' AND r.source_id = n.note_id)
            LEFT JOIN exams e ON (r.source_table='exams' AND r.source_id = e.exam_id)
            WHERE r.user_id = %s AND r.reminder_date = %s AND (r.dismissed = FALSE OR r.dismissed IS NULL)
            ORDER BY r.created_at ASC
        """, (user_id, today))

        rows = cur.fetchall() or []
        out = []
        for r in rows:
            due_dt = parse_due_date_from_text(r.get("due_text") or "")
            days_left = None
            if due_dt:
                days_left = (due_dt - today).days
            out.append({
                "reminder_id": r.get("reminder_id"),
                "source_table": r.get("source_table"),
                "source_id": r.get("source_id"),
                "title": r.get("title") or "(no title)",
                "subject": r.get("subject") or "",
                "description": r.get("description") or "",
                "due_text": r.get("due_text") or "",
                "days_left": days_left
            })

        return out

    finally:
        try:
            if cur: cur.close()
        except:
            pass
        try:
            if con: con.close()
        except:
            pass



# ===== Reminder Screen (Reminder.html) =====

@app.route('/reminders', methods=['GET'])
def reminders():
    if 'user' not in session:
        flash("Please log in to access reminders.", "warning")
        return redirect(url_for('login_page'))

    user_id = session['user']['id']
    reminders_today = generate_todays_reminders_for_user(user_id)
    return render_template('Reminder.html', reminders=reminders_today)

# ===== Delete/Dismiss Reminder =====
@app.route('/reminders/delete', methods=['POST'])
def reminders_delete():
    if 'user' not in session:
        return jsonify({"error": "Authentication required"}), 401

    reminder_id = request.form.get('reminder_id') or (request.json and request.json.get('reminder_id'))
    if not reminder_id:
        return jsonify({"error": "reminder_id required"}), 400

    user_id = session['user']['id']
    today = date.today()
    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT reminder_id FROM reminders WHERE reminder_id=%s AND user_id=%s AND reminder_date=%s", (reminder_id, user_id, today))
        row = cur.fetchone()
        if not row:
            cur.close()
            con.close()
            return jsonify({"error": "Reminder not found or not for today"}), 404

        cur.execute("UPDATE reminders SET dismissed = TRUE WHERE reminder_id = %s", (reminder_id,))
        con.commit()
        cur.close()
        con.close()

        if request.form:
            flash("Reminder dismissed.", "info")
            return redirect(url_for('reminders'))
        return jsonify({"success": True}), 200

    except Exception as e:
        print("Error dismissing reminder:", e)
        try:
            if cur: cur.close()
        except:
            pass
        try:
            if con: con.close()
        except:
            pass
        return jsonify({"error": "Database error"}), 500



if __name__ == '__main__':
    app.run(debug=True)