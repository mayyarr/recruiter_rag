import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash


def get_connection():
    return sqlite3.connect("recruiter.db")


def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role TEXT,
        content TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recruiter_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_name TEXT,
        note TEXT
    )
    """)

    # جدول جديد فقط للمستخدمين -- IF NOT EXISTS يعني ما رح يمسح
    # ولا يفرّغ أي جدول موجود مسبقًا
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        remember_token TEXT,
        created_at TEXT
    )
    """)

    # Part 1: لوحة تحكم الريكروتر -- المرشحين وطلبات التوظيف
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        cv_file TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT,
        FOREIGN KEY (candidate_id) REFERENCES candidates (id)
    )
    """)

    # Part 2: تقييمات الريكروتر لكل مرشح (بمعايير مثل Python, Backend...)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidate_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        criterion TEXT NOT NULL,
        score INTEGER NOT NULL,
        comment TEXT,
        created_at TEXT,
        FOREIGN KEY (candidate_id) REFERENCES candidates (id)
    )
    """)

    # Part 3: مواعيد المقابلات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        interview_date TEXT,
        interview_time TEXT,
        status TEXT,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY (candidate_id) REFERENCES candidates (id)
    )
    """)

    # --- Migration: لو الداتا بيس أصلاً موجودة من قبل هالتحديث،
    # جدول chat_sessions ما رح يكون فيه عمود user_id لأنه
    # CREATE TABLE IF NOT EXISTS ما بيعدّل جدول موجود مسبقًا.
    # هاد الجزء بيضيف العمود إذا كان ناقص، بدون ما يمسح ولا صف واحد.
    cursor.execute("PRAGMA table_info(chat_sessions)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if "user_id" not in existing_columns:
        cursor.execute("ALTER TABLE chat_sessions ADD COLUMN user_id INTEGER")

    conn.commit()
    conn.close()


# ---------------- Chat sessions (Task 1 + Task 4 + Task 6) ----------------

def create_chat_session(title, user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chat_sessions (user_id, title, created_at)
        VALUES (?, ?, datetime('now'))
        """,
        (user_id, title)
    )

    session_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return session_id


def get_chat_sessions(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, created_at
        FROM chat_sessions
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    sessions = []
    for row in rows:
        sessions.append({
            "id": row[0],
            "title": row[1],
            "created_at": row[2]
        })

    return sessions


def get_chat_session_owner(session_id):
    """بترجع الـ user_id يلي بملك هالمحادثة، أو None إذا مش موجودة.
    مستخدمة للتحقق من الصلاحية قبل ما نسمح بأي عملية على محادثة
    (فتح، تعديل، حذف) -- عشان مستخدم ما يقدر يوصل لمحادثة مستخدم
    تاني حتى لو خمّن رقم الـ session_id بالرابط."""

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id FROM chat_sessions WHERE id = ?",
        (session_id,)
    )

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def rename_chat_session(session_id, new_title):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE chat_sessions
        SET title = ?
        WHERE id = ?
        """,
        (new_title, session_id)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Chat session renamed"
    }


def delete_chat_session(session_id):

    conn = get_connection()
    cursor = conn.cursor()

    # Delete the session itself
    cursor.execute(
        "DELETE FROM chat_sessions WHERE id = ?",
        (session_id,)
    )

    # Task 6: deleting a session must also remove its stored messages
    cursor.execute(
        "DELETE FROM chat_messages WHERE session_id = ?",
        (str(session_id),)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Chat session and its messages deleted"
    }


# ---------------- Chat messages (Task 2 + Task 3) ----------------

def save_message(session_id, role, content):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chat_messages
        (session_id, role, content)
        VALUES (?, ?, ?)
        """,
        (session_id, role, content)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Chat message saved"
    }


def get_chat_history(session_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id
        """,
        (session_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        messages.append({
            "role": row[0],
            "content": row[1]
        })

    return messages


# ---------------- Recruiter notes (Task 5) ----------------

def add_recruiter_note(candidate_name, note):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO recruiter_notes
        (candidate_name, note)
        VALUES (?, ?)
        """,
        (candidate_name, note)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Recruiter note saved"
    }


def get_recruiter_notes(candidate_name=None):
    """
    إذا انبعت candidate_name: بترجع ملاحظات هاد المرشح بس.
    إذا ما انبعت شي (None): بترجع كل الملاحظات المخزنة -- هاد اللي
    محتاجاه app.py لعرض كل الملاحظات بالواجهة (Task 5).
    """

    conn = get_connection()
    cursor = conn.cursor()

    if candidate_name:
        cursor.execute(
            """
            SELECT id, candidate_name, note
            FROM recruiter_notes
            WHERE candidate_name = ?
            ORDER BY id
            """,
            (candidate_name,)
        )
    else:
        cursor.execute(
            """
            SELECT id, candidate_name, note
            FROM recruiter_notes
            ORDER BY id
            """
        )

    rows = cursor.fetchall()
    conn.close()

    notes = []
    for row in rows:
        notes.append({
            "id": row[0],
            "candidate_name": row[1],
            "note": row[2]
        })

    return {
        "success": True,
        "candidate_name": candidate_name,
        "notes": notes
    }


def update_recruiter_note(note_id, new_note):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE recruiter_notes
        SET note = ?
        WHERE id = ?
        """,
        (new_note, note_id)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Recruiter note updated"
    }


def delete_recruiter_note(note_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM recruiter_notes WHERE id = ?",
        (note_id,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Recruiter note deleted"
    }


# ---------------- Users (Auth) ----------------

def create_user(email, password):
    """بينشئ حساب جديد. بيرجع success=False إذا الإيميل مستخدم مسبقًا."""

    conn = get_connection()
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)

    try:
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (email, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return {"success": True, "user_id": user_id}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "This email is already registered."}
    finally:
        conn.close()


def get_user_by_email(email):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, email, password_hash, remember_token
        FROM users
        WHERE email = ?
        """,
        (email,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "remember_token": row[3],
    }


def verify_user(email, password):
    """بيتحقق من الإيميل وكلمة السر. بيرجع بيانات المستخدم لو صح، وإلا None."""
    user = get_user_by_email(email)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def get_user_by_id(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, email FROM users WHERE id = ?",
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {"id": row[0], "email": row[1]}


def save_remember_token(user_id):
    """بيولّد توكن عشوائي، يخزّنه بالداتا بيس، وبيرجعه عشان ينحط بكوكي المتصفح."""

    token = secrets.token_hex(32)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET remember_token = ? WHERE id = ?",
        (token, user_id)
    )

    conn.commit()
    conn.close()

    return token


def get_user_by_remember_token(token):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, email FROM users WHERE remember_token = ?",
        (token,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {"id": row[0], "email": row[1]}


def clear_remember_token(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET remember_token = NULL WHERE id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


# ---------------- Part 1: Candidates & Applications ----------------

APPLICATION_STATUSES = ["Applied", "Screening", "Interview", "Hold"]


def create_candidate(name, email, cv_file, status="Applied"):
    """بينشئ مرشح جديد بجدول candidates + طلب توظيف واحد (application)
    إله بالحالة المبدئية. الحالة الافتراضية "Applied" مضروبة من
    التطبيق نفسه -- مش من الـ LLM ولا بتنحسب تلقائيًا، الريكروتر هو
    يلي بيقدر يغيّرها لاحقًا من صفحة بروفايل المرشح."""
    if status not in APPLICATION_STATUSES:
        status = "Applied"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO candidates (name, email, cv_file, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (name, email, cv_file)
    )
    candidate_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO applications (candidate_id, status, created_at)
        VALUES (?, ?, datetime('now'))
        """,
        (candidate_id, status)
    )

    conn.commit()
    conn.close()

    return candidate_id


def get_dashboard_summary():
    """بيرجع إجمالي عدد المرشحين + عدد كل حالة (للكروت الملخّصة
    بأعلى لوحة التحكم)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM candidates")
    total = cursor.fetchone()[0]

    counts = {status: 0 for status in APPLICATION_STATUSES}

    cursor.execute(
        """
        SELECT a.status, COUNT(*)
        FROM applications a
        WHERE a.id IN (
            SELECT MAX(id) FROM applications GROUP BY candidate_id
        )
        GROUP BY a.status
        """
    )
    for status, count in cursor.fetchall():
        if status in counts:
            counts[status] = count

    conn.close()

    return {"total": total, **counts}


def get_candidates_with_status(status_filter=None):
    """جدول المرشحين مع آخر حالة طلب توظيف إلهم. كل مرشح بياخد صف
    واحد بس، حتى لو تراكم له أكتر من application بالمستقبل (بناخد
    أحدث واحدة إله)."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT c.id, c.name, c.email, c.cv_file, a.status
        FROM candidates c
        LEFT JOIN applications a
            ON a.id = (
                SELECT id FROM applications
                WHERE candidate_id = c.id
                ORDER BY id DESC LIMIT 1
            )
    """
    params = ()
    if status_filter and status_filter != "All":
        query += " WHERE a.status = ?"
        params = (status_filter,)
    query += " ORDER BY c.id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    candidates = []
    for row in rows:
        candidates.append({
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "cv_file": row[3],
            "status": row[4] or "Applied",
        })
    return candidates


def get_candidate_profile(candidate_id):
    """تفاصيل مرشح واحد + كل طلبات التوظيف (applications) إله،
    مرتبة الأحدث أول. مستخدمة لصفحة بروفايل المرشح (زر View)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, email, cv_file, created_at FROM candidates WHERE id = ?",
        (candidate_id,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    candidate = {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "cv_file": row[3],
        "created_at": row[4],
    }

    cursor.execute(
        """
        SELECT id, status, created_at
        FROM applications
        WHERE candidate_id = ?
        ORDER BY id DESC
        """,
        (candidate_id,)
    )
    app_rows = cursor.fetchall()
    conn.close()

    candidate["applications"] = [
        {"id": r[0], "status": r[1], "created_at": r[2]} for r in app_rows
    ]
    candidate["status"] = app_rows[0][1] if app_rows else "Applied"

    return candidate


def update_application_status(candidate_id, new_status):
    """بتضيف application جديدة بالحالة الجديدة (بدل ما تعدّل القديمة
    بمكانها) -- هيك منحتفظ بتاريخ كل تغيير حالة، وهاد ضروري حتى نقدر
    نحسب "من إيمتى المرشح بحالة Screening" لتذكيرات Part 4. دايمًا
    بالتحكم اليدوي من الريكروتر، أبدًا مش من الـ LLM."""
    if new_status not in APPLICATION_STATUSES:
        return {"success": False, "message": "Invalid status"}

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO applications (candidate_id, status, created_at)
        VALUES (?, ?, datetime('now'))
        """,
        (candidate_id, new_status)
    )

    conn.commit()
    conn.close()

    return {"success": True}


def find_candidate_by_name(name_query):
    """بتدور عن مرشح بالاسم (مطابقة مرنة) -- مستخدمة من أدوات الـ
    Agent (Part 3) لما الريكروتر يذكر اسم مرشح بالشات. بترجع أول
    تطابق أو None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, cv_file FROM candidates")
    rows = cursor.fetchall()
    conn.close()

    q = (name_query or "").strip().lower()
    if not q:
        return None

    for row in rows:
        if row[1].strip().lower() == q:
            return {"id": row[0], "name": row[1], "email": row[2], "cv_file": row[3]}

    for row in rows:
        cand_name = row[1].strip().lower()
        if q in cand_name or cand_name in q:
            return {"id": row[0], "name": row[1], "email": row[2], "cv_file": row[3]}

    return None


# ---------------- Part 2: Candidate Assessments ----------------

ASSESSMENT_CRITERIA = ["Python", "Backend", "RAG", "Agentic AI", "Communication"]


def add_assessment(candidate_id, criterion, score, comment):
    """الريكروتر هو يلي بيدخل الـ score -- الـ AI ممكن يعطي أدلة من
    السيرة الذاتية بس ما بيقرر الدرجة نفسها."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO candidate_assessments (candidate_id, criterion, score, comment, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (candidate_id, criterion, score, comment)
    )
    conn.commit()
    conn.close()


def get_assessments(candidate_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, criterion, score, comment, created_at
        FROM candidate_assessments
        WHERE candidate_id = ?
        ORDER BY id DESC
        """,
        (candidate_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "criterion": r[1], "score": r[2], "comment": r[3], "created_at": r[4]}
        for r in rows
    ]


# ---------------- Part 3: Interviews ----------------

INTERVIEW_STATUSES = ["Scheduled", "Cancelled", "Completed"]


def create_interview(candidate_id, interview_date, interview_time, notes=None, status="Scheduled"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO interviews (candidate_id, interview_date, interview_time, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (candidate_id, interview_date, interview_time, status, notes)
    )
    interview_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return interview_id


def get_interviews_for_candidate(candidate_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, interview_date, interview_time, status, notes
        FROM interviews
        WHERE candidate_id = ?
        ORDER BY interview_date DESC, id DESC
        """,
        (candidate_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "interview_date": r[1], "interview_time": r[2], "status": r[3], "notes": r[4]}
        for r in rows
    ]


def get_interview(interview_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, candidate_id, interview_date, interview_time, status, notes
        FROM interviews WHERE id = ?
        """,
        (interview_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0], "candidate_id": row[1], "interview_date": row[2],
        "interview_time": row[3], "status": row[4], "notes": row[5],
    }


def update_interview(interview_id, interview_date, interview_time, notes):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE interviews
        SET interview_date = ?, interview_time = ?, notes = ?
        WHERE id = ?
        """,
        (interview_date, interview_time, notes, interview_id)
    )
    conn.commit()
    conn.close()


def cancel_interview(interview_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE interviews SET status = 'Cancelled' WHERE id = ?",
        (interview_id,)
    )
    conn.commit()
    conn.close()


# ---------------- Part 4: Reminders / Upcoming Activity ----------------

def get_reminders():
    """بتفحص: (1) مقابلات بكرا، (2) مرشحين بحالة Screening من 7 أيام
    أو أكتر (محسوبة من تاريخ آخر تغيير حالة، مش تاريخ إنشاء المرشح)."""
    conn = get_connection()
    cursor = conn.cursor()

    reminders = []

    cursor.execute(
        """
        SELECT c.name, i.interview_time
        FROM interviews i
        JOIN candidates c ON c.id = i.candidate_id
        WHERE i.status = 'Scheduled'
          AND date(i.interview_date) = date('now', '+1 day')
        ORDER BY i.interview_time
        """
    )
    for name, time_ in cursor.fetchall():
        if time_:
            text = f"{name} has an interview tomorrow at {time_}."
        else:
            text = f"{name} has an interview tomorrow."
        reminders.append({"type": "interview", "text": text})

    cursor.execute(
        """
        SELECT c.name, a.created_at
        FROM candidates c
        JOIN applications a ON a.id = (
            SELECT id FROM applications WHERE candidate_id = c.id ORDER BY id DESC LIMIT 1
        )
        WHERE a.status = 'Screening'
          AND julianday('now') - julianday(a.created_at) >= 7
        """
    )
    for name, _ in cursor.fetchall():
        reminders.append({
            "type": "followup",
            "text": f"{name} has been in Screening for more than 7 days.",
        })

    conn.close()
    return reminders