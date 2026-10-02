import os
import re
import json
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Flask,
    request,
    render_template,
    session,
    redirect,
    url_for,
    jsonify,
    flash,
    send_file,
)
from agent import run_agent, get_all_sources, get_all_evidence
from rag import CONFIDENCE_THRESHOLD, load_or_build_index, add_pdf_to_index, rag_query_scoped
from translate import translate_texts
from pdf_export import build_report_pdf
from candidate_extract import extract_candidate_info
from database import (
    init_db,
    create_chat_session,
    get_chat_sessions,
    get_chat_session_owner,
    rename_chat_session,
    delete_chat_session,
    save_message,
    get_chat_history,
    add_recruiter_note,
    get_recruiter_notes,
    update_recruiter_note,
    delete_recruiter_note,
    create_user,
    verify_user,
    get_user_by_id,
    save_remember_token,
    get_user_by_remember_token,
    clear_remember_token,
    APPLICATION_STATUSES,
    create_candidate,
    get_dashboard_summary,
    get_candidates_with_status,
    get_candidate_profile,
    update_application_status,
    ASSESSMENT_CRITERIA,
    add_assessment,
    get_assessments,
    INTERVIEW_STATUSES,
    create_interview,
    get_interviews_for_candidate,
    get_interview,
    update_interview,
    cancel_interview,
    get_reminders,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)

DOCS_FOLDER = "docs"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # حد أقصى 10MB للملف

REMEMBER_COOKIE_NAME = "remember_token"
REMEMBER_COOKIE_DAYS = 30

# تهيئة قاعدة البيانات عند تشغيل السيرفر
init_db()

# تحميل/بناء فهرس الـ RAG مرة وحدة عند تشغيل السيرفر
os.makedirs(DOCS_FOLDER, exist_ok=True)
load_or_build_index()


# --- Helpers for UX additions ---------------------------------
COMPARISON_KEYWORDS = [
    "compare",
    " vs ",
    "versus",
    "difference between",
    "who is better",
    "which one",
    "better fit",
    "between ",
]


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def display_name_from_filename(filename):
    """Turn a CV filename like 'Ahmad_Khalil.pdf' into 'Ahmad Khalil'."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"\b(cv|resume|final|v\d+)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title()


def is_comparison_question(question):
    q = question.lower()
    return any(kw in q for kw in COMPARISON_KEYWORDS)


def build_comparison_cards(final_answer, question, sources):
    if not final_answer or not sources or len(sources) < 2:
        return None
    if not is_comparison_question(question):
        return None

    candidates = []
    for source in sources:
        name = display_name_from_filename(source)
        if name:
            candidates.append({"source": source, "name": name})

    if len(candidates) < 2:
        return None

    positions = []
    for cand in candidates:
        first_name = cand["name"].split()[0]
        match = re.search(re.escape(first_name), final_answer, re.IGNORECASE)
        if match:
            positions.append((match.start(), cand))

    if len(positions) < 2:
        return None

    positions.sort(key=lambda p: p[0])

    cards = []
    for i, (start, cand) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(final_answer)
        segment = final_answer[start:end].strip()

        sentences = re.split(r"(?<=[.!?])\s+", segment)
        points = [s.strip() for s in sentences if s.strip()]

        cards.append(
            {
                "name": cand["name"],
                "source": cand["source"],
                "points": points[:4],
            }
        )

    return cards


def build_suggestions(question, final_answer, sources):
    if not final_answer:
        return []

    names = []
    for source in sources:
        name = display_name_from_filename(source)
        if name and name not in names:
            names.append(name)

    suggestions = []

    if names:
        suggestions.append(f"Tell me more about {names[0]}'s experience")

    if len(names) >= 2:
        suggestions.append(f"Compare {names[0]} with {names[1]}")

    if names:
        suggestions.append(f"What other skills does {names[0]} have?")

    suggestions.append("How many CVs are currently loaded?")

    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique_suggestions.append(s)

    return unique_suggestions[:3]


def get_current_session_id():
    """الحصول على رقم الجلسة الحالية أو إنشاء واحدة جديدة -- مربوطة
    بالمستخدم المسجّل دخوله فقط. إذا كان الـ session_id المحفوظ
    بالكوكي يخص مستخدم تاني (مثلاً بعد تسجيل خروج ودخول بحساب
    مختلف بنفس المتصفح)، منتجاهله ومنعمل واحدة جديدة."""
    session_id = session.get("session_id")
    user_id = session.get("user_id")

    if session_id is not None:
        owner_id = get_chat_session_owner(session_id)
        if owner_id != user_id:
            session_id = None

    if session_id is None:
        session_id = create_chat_session("New Chat", user_id)
        session["session_id"] = session_id

    return session_id


# --- Auth helpers -----------------------------------------------

def login_required(view_func):
    """يحمي أي route: لازم يكون فيه مستخدم مسجّل دخول (بالسيشن أو
    عن طريق remember-me cookie) وإلا بيرجّعه لصفحة تسجيل الدخول."""

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if session.get("user_id"):
            return view_func(*args, **kwargs)

        # جرب الـ remember-me cookie قبل ما نرجّعه لصفحة اللوجن
        token = request.cookies.get(REMEMBER_COOKIE_NAME)
        if token:
            user = get_user_by_remember_token(token)
            if user:
                session["user_id"] = user["id"]
                session["user_email"] = user["email"]
                return view_func(*args, **kwargs)

        return redirect(url_for("login"))

    return wrapper


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not email or not password:
            flash("Please fill in both email and password.", "error")
            return redirect(url_for("signup"))

        if password != confirm:
            flash("Password and confirmation do not match.", "error")
            return redirect(url_for("signup"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("signup"))

        result = create_user(email, password)
        if not result["success"]:
            flash(result["message"], "error")
            return redirect(url_for("signup"))

        session["user_id"] = result["user_id"]
        session["user_email"] = email
        flash("Account created successfully.", "success")
        return redirect(url_for("index"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember_me = request.form.get("remember_me") == "on"

        user = verify_user(email, password)
        if not user:
            flash("Incorrect email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["user_email"] = user["email"]

        resp = redirect(url_for("index"))

        if remember_me:
            token = save_remember_token(user["id"])
            resp.set_cookie(
                REMEMBER_COOKIE_NAME,
                token,
                max_age=REMEMBER_COOKIE_DAYS * 24 * 60 * 60,
                httponly=True,
                samesite="Lax",
            )

        return resp

    return render_template("login.html")


@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        clear_remember_token(user_id)

    session.pop("user_id", None)
    session.pop("user_email", None)
    session.pop("session_id", None)

    resp = redirect(url_for("login"))
    resp.delete_cookie(REMEMBER_COOKIE_NAME)
    return resp


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    evidence = []
    steps = []
    comparison_cards = None
    suggestions = []
    last_question = None
    last_answer = None
    proposed_action = None

    session_id = get_current_session_id()

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            # Task 3: جلب المحادثات السابقة لتقديم سياق الوكيل
            prior_history = get_chat_history(str(session_id))

            state = run_agent(question, conversation_history=prior_history)
            final_answer = state["final_answer"]
            steps = state["steps"]
            evidence = get_all_evidence(state)
            sources = get_all_sources(state)
            proposed_action = state.get("proposed_action")

            comparison_cards = build_comparison_cards(
                final_answer, question, sources
            )
            suggestions = build_suggestions(question, final_answer, sources)

            last_question = question
            last_answer = final_answer

            # Task 2: حفظ الأسئلة والإجابات في SQLite
            save_message(str(session_id), "user", question)
            save_message(str(session_id), "assistant", final_answer)

    # Task 3: جلب الرسائل من قاعدة البيانات
    history = get_chat_history(str(session_id))

    # Task 4: جلب جلسات المستخدم الحالي فقط -- مو كل الجلسات
    chat_sessions = get_chat_sessions(session["user_id"])

    # Task 5: جلب ملاحظات التوظيف لتمريرها للواجهة
    recruiter_notes = get_recruiter_notes()

    return render_template(
        "index.html",
        history=history,
        evidence=evidence,
        steps=steps,
        comparison_cards=comparison_cards,
        suggestions=suggestions,
        confidence_threshold=CONFIDENCE_THRESHOLD,
        chat_sessions=chat_sessions,
        current_session_id=session_id,
        recruiter_notes=recruiter_notes,
        current_user_email=session.get("user_email"),
        last_question=last_question,
        last_answer=last_answer,
        proposed_action=proposed_action,
    )


@app.route("/upload_cv", methods=["POST"])
@login_required
def upload_cv():
    """استقبال سيفي (أو أكتر) من الواجهة، حفظه بمجلد docs،
    وإضافته لفهرس الـ RAG بدون إعادة بناء باقي الفهرس."""
    files = request.files.getlist("cv_files")

    if not files or all(f.filename == "" for f in files):
        flash("لم يتم اختيار أي ملف.", "error")
        return redirect(url_for("index"))

    added = []
    skipped = []

    for file in files:
        if file.filename == "":
            continue

        if not allowed_file(file.filename):
            skipped.append(f"{file.filename} (نوع غير مدعوم، PDF فقط)")
            continue

        filename = secure_filename(file.filename)
        save_path = os.path.join(DOCS_FOLDER, filename)

        if os.path.exists(save_path):
            skipped.append(f"{filename} (موجود مسبقًا)")
            continue

        file.save(save_path)

        try:
            add_pdf_to_index(filename)
            added.append(filename)
        except Exception as e:
            skipped.append(f"{filename} (فشل الفهرسة: {e})")
            # نحذف الملف لو فشلت فهرسته عشان ما يضل معلّق بدون فهرس
            if os.path.exists(save_path):
                os.remove(save_path)

    if added:
        flash(f"تمت إضافة {len(added)} سيفي بنجاح: {', '.join(added)}", "success")
    if skipped:
        flash(f"تم تجاوز: {', '.join(skipped)}", "error")

    return redirect(url_for("index"))


@app.route("/voice_chat", methods=["POST"])
@login_required
def voice_chat():
    try:
        question = request.form.get("question", "").strip()

        if not question:
            return jsonify({
                "success": False,
                "answer": "I didn't hear a question."
            }), 400

        # Get current chat session
        session_id = get_current_session_id()

        # Get previous conversation
        prior_history = get_chat_history(str(session_id))

        # Run the SAME agent used by normal chat
        state = run_agent(
            question,
            conversation_history=prior_history
        )

        final_answer = state.get("final_answer", "").strip()

        if not final_answer:
            return jsonify({
                "success": False,
                "answer": "I couldn't generate an answer."
            }), 500

        # Save conversation
        save_message(
            str(session_id),
            "user",
            question
        )

        save_message(
            str(session_id),
            "assistant",
            final_answer
        )

        return jsonify({
            "success": True,
            "answer": final_answer
        })

    except Exception as e:
        print("VOICE CHAT ERROR:", e)

        return jsonify({
            "success": False,
            "answer": "Sorry, something went wrong while processing your voice question."
        }), 500

@app.route("/translate_chat", methods=["POST"])
@login_required
def translate_chat():
    """بتاخد مجموعة نصوص من الواجهة (رسائل الشات) وبترجعهم مترجمين.
    مستخدمة من زر 'ترجم للعربي' بالواجهة."""
    try:
        data = request.get_json(silent=True) or {}
        texts = data.get("texts", [])
        target_lang = data.get("target_lang", "ar")

        if not texts:
            return jsonify({"success": True, "translations": []})

        translations = translate_texts(texts, target_lang)

        return jsonify({"success": True, "translations": translations})

    except Exception as e:
        print("TRANSLATE ROUTE ERROR:", e)
        return jsonify({"success": False, "translations": texts}), 500


@app.route("/export_report", methods=["POST"])
@login_required
def export_report():
    """Task 14: بتاخد آخر سؤال/جواب (+ الأدلة أو كروت المقارنة إذا
    كانت موجودة) من الفورم المخفي بالواجهة، وبتولّد تقرير PDF منسّق
    على شكل جداول، وبترجعه كملف تحميل مباشر."""
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()

    try:
        evidence = json.loads(request.form.get("evidence_json", "[]"))
    except (TypeError, ValueError):
        evidence = []

    try:
        comparison_cards = json.loads(request.form.get("comparison_json", "null"))
    except (TypeError, ValueError):
        comparison_cards = None

    if not question and not answer:
        flash("Nothing to export yet -- ask a question first.", "error")
        return redirect(url_for("index"))

    pdf_path = build_report_pdf(question, answer, evidence, comparison_cards)

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="candidate_report.pdf",
        mimetype="application/pdf",
    )


@app.route("/dashboard")
@login_required
def dashboard():
    """Part 1: لوحة تحكم الريكروتر -- كروت ملخّصة + جدول المرشحين +
    فلتر بالحالة. كل البيانات جايّة من SQLite، ولا صف واحد ثابت
    بالـ HTML."""
    status_filter = request.args.get("status", "All")
    candidates = get_candidates_with_status(status_filter)
    summary = get_dashboard_summary()
    reminders = get_reminders()

    return render_template(
        "dashboard.html",
        candidates=candidates,
        summary=summary,
        status_filter=status_filter,
        statuses=APPLICATION_STATUSES,
        reminders=reminders,
    )


@app.route("/candidates/<int:candidate_id>", methods=["GET", "POST"])
@login_required
def candidate_profile(candidate_id):
    candidate = get_candidate_profile(candidate_id)
    if not candidate:
        flash("Candidate not found.", "error")
        return redirect(url_for("dashboard"))

    candidate_answer = None
    candidate_question = None
    candidate_evidence = []

    if request.method == "POST":
        # Part 2: شات مقيّد على هالمرشح بس -- مقيّد على ملف سيرته هو
        # (cv_file)، بدون اعتماد على استخراج اسم من نص السؤال.
        candidate_question = request.form.get("candidate_question", "").strip()
        if candidate_question and candidate.get("cv_file"):
            answer, retrieved, sources, evidence, best_score = rag_query_scoped(
                candidate_question, allowed_sources=[candidate["cv_file"]]
            )
            candidate_answer = answer
            candidate_evidence = [
                {"source": s, "snippet": evidence.get(s, "")} for s in sources
            ]

    notes = get_recruiter_notes(candidate["name"])
    assessments = get_assessments(candidate_id)
    interviews = get_interviews_for_candidate(candidate_id)

    return render_template(
        "candidate_profile.html",
        candidate=candidate,
        notes=notes["notes"],
        statuses=APPLICATION_STATUSES,
        assessment_criteria=ASSESSMENT_CRITERIA,
        assessments=assessments,
        interviews=interviews,
        candidate_question=candidate_question,
        candidate_answer=candidate_answer,
        candidate_evidence=candidate_evidence,
    )


@app.route("/candidates/<int:candidate_id>/assessments/add", methods=["POST"])
@login_required
def add_candidate_assessment(candidate_id):
    """Part 2: الريكروتر هو يلي بيدخل الدرجة (1-10) -- الـ AI ممكن
    يعطي أدلة بالشات المقيّد فوق، بس ما بيقرر الدرجة."""
    criterion = request.form.get("criterion", "").strip()
    comment = request.form.get("comment", "").strip()

    try:
        score = int(request.form.get("score", ""))
    except (TypeError, ValueError):
        score = None

    if not criterion or score is None or not (1 <= score <= 10):
        flash("Please choose a criterion and a score between 1 and 10.", "error")
    else:
        add_assessment(candidate_id, criterion, score, comment)
        flash("Assessment saved.", "success")

    return redirect(url_for("candidate_profile", candidate_id=candidate_id))


@app.route("/candidates/<int:candidate_id>/interviews/schedule", methods=["POST"])
@login_required
def schedule_interview(candidate_id):
    """Part 3: جدولة مباشرة من الواجهة -- فعل مباشر من الريكروتر
    نفسه، فما بيحتاج خطوة Approve إضافية (هاي مختلفة عن مسار الـ
    Agent يلي لازم يمر بموافقة صريحة أول)."""
    interview_date = request.form.get("interview_date", "").strip()
    interview_time = request.form.get("interview_time", "").strip()
    notes = request.form.get("notes", "").strip()

    if not interview_date:
        flash("Please choose an interview date.", "error")
    else:
        create_interview(candidate_id, interview_date, interview_time, notes)
        flash("Interview scheduled.", "success")

    return redirect(url_for("candidate_profile", candidate_id=candidate_id))


@app.route("/interviews/<int:interview_id>/update", methods=["POST"])
@login_required
def update_interview_route(interview_id):
    interview = get_interview(interview_id)
    if not interview:
        flash("Interview not found.", "error")
        return redirect(url_for("dashboard"))

    interview_date = request.form.get("interview_date", "").strip()
    interview_time = request.form.get("interview_time", "").strip()
    notes = request.form.get("notes", "").strip()

    update_interview(interview_id, interview_date, interview_time, notes)
    flash("Interview updated.", "success")
    return redirect(url_for("candidate_profile", candidate_id=interview["candidate_id"]))


@app.route("/interviews/<int:interview_id>/cancel")
@login_required
def cancel_interview_route(interview_id):
    interview = get_interview(interview_id)
    if not interview:
        flash("Interview not found.", "error")
        return redirect(url_for("dashboard"))

    cancel_interview(interview_id)
    flash("Interview cancelled.", "success")
    return redirect(url_for("candidate_profile", candidate_id=interview["candidate_id"]))


@app.route("/agent/approve_action", methods=["POST"])
@login_required
def approve_agent_action():
    """Part 3: الحفظ الفعلي بقاعدة البيانات لأي إجراء اقترحه الـ
    Agent -- بيصير بس هون، بعد ما الريكروتر يدوس Approve. الـ Agent
    نفسه ما بيلمس SQLite أبدًا."""
    action_type = request.form.get("action_type", "")
    candidate_id = request.form.get("candidate_id", "")

    try:
        candidate_id = int(candidate_id)
    except (TypeError, ValueError):
        flash("Invalid proposed action.", "error")
        return redirect(url_for("index"))

    if action_type == "schedule_interview":
        interview_date = request.form.get("interview_date", "").strip()
        interview_time = request.form.get("interview_time", "").strip()
        notes = request.form.get("notes", "").strip()
        create_interview(candidate_id, interview_date, interview_time, notes)
        flash("Interview approved and saved.", "success")

    elif action_type == "status_change":
        new_status = request.form.get("new_status", "").strip()
        result = update_application_status(candidate_id, new_status)
        if result["success"]:
            flash("Status change approved and saved.", "success")
        else:
            flash("Invalid status.", "error")

    else:
        flash("Unknown proposed action.", "error")

    return redirect(url_for("candidate_profile", candidate_id=candidate_id))


@app.route("/agent/cancel_action", methods=["POST"])
@login_required
def cancel_agent_action():
    flash("Proposed action discarded -- nothing was saved.", "success")
    return redirect(url_for("index"))


@app.route("/candidates/<int:candidate_id>/status", methods=["POST"])
@login_required
def candidate_update_status(candidate_id):
    """تحديث حالة التوظيف -- بالكامل تحت تحكم الريكروتر عن طريق
    هالفورم اليدوي، أبدًا مش من الـ LLM."""
    new_status = request.form.get("status", "")
    result = update_application_status(candidate_id, new_status)
    if not result["success"]:
        flash("Invalid status.", "error")
    return redirect(url_for("candidate_profile", candidate_id=candidate_id))


@app.route("/candidates/add")
@login_required
def add_candidate_form():
    return render_template("candidate_add.html")


@app.route("/candidates/extract", methods=["POST"])
@login_required
def extract_candidate():
    """Optional Challenge: بتستقبل PDF، بتحفظه، بتقرا نصه، وبتطلب
    من الـ LLM يستخرج بس معلومات واقعية (اسم + إيميل) -- بدون ما
    يخترع شي وبدون ما يقيّم المرشح. النتيجة بتترض كفورم قابل للتعديل،
    وما رح تنحفظ بجدول candidates إلا بعد ما الريكروتر يدوس
    Confirm & Save."""
    file = request.files.get("cv_file")

    if not file or file.filename == "":
        flash("Please choose a CV PDF first.", "error")
        return redirect(url_for("add_candidate_form"))

    if not allowed_file(file.filename):
        flash("Only PDF files are supported.", "error")
        return redirect(url_for("add_candidate_form"))

    filename = secure_filename(file.filename)
    save_path = os.path.join(DOCS_FOLDER, filename)

    if os.path.exists(save_path):
        flash(f"{filename} already exists. Rename the file and try again.", "error")
        return redirect(url_for("add_candidate_form"))

    file.save(save_path)

    try:
        extracted = extract_candidate_info(save_path, filename)
    except Exception as e:
        print("CANDIDATE EXTRACT ERROR:", e)
        extracted = {"name": None, "email": None, "cv_file": filename}
        flash(
            "Could not extract details automatically -- please fill them in manually.",
            "error",
        )

    # منضيف الملف لفهرس الـ RAG فورًا (نفس سلوك Upload CVs العادي)،
    # حتى الريكروتر يقدر يسأل عن هالمرشح بالشات فورًا، حتى قبل ما
    # يأكّد حفظه بجدول candidates.
    try:
        add_pdf_to_index(filename)
    except Exception as e:
        print("INDEXING ERROR (candidate CV):", e)

    return render_template(
        "candidate_review.html",
        extracted=extracted,
        statuses=APPLICATION_STATUSES,
    )


@app.route("/candidates/confirm", methods=["POST"])
@login_required
def confirm_candidate():
    """الحفظ الفعلي بجدول candidates -- بيصير بس هون، بعد ما
    الريكروتر راجع/صحح البيانات ودوس Confirm & Save. الحالة
    الابتدائية (status) قيمة عادية من قائمة منسدلة بالفورم، الـ LLM
    ما إله أي دخل فيها."""
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    cv_file = request.form.get("cv_file", "").strip()
    status = request.form.get("status", "Applied").strip()

    if not name or not cv_file:
        flash("Name and CV file are required to save the candidate.", "error")
        return redirect(url_for("add_candidate_form"))

    candidate_id = create_candidate(name, email or None, cv_file, status)
    flash(f"{name} was added to the dashboard.", "success")
    return redirect(url_for("candidate_profile", candidate_id=candidate_id))


@app.route("/clear")
@login_required
def clear():
    session.pop("session_id", None)
    return redirect(url_for("index"))


# --- Tasks 4 & 6: التحكم بالجلسات ---

@app.route("/select_session/<int:session_id>")
@login_required
def select_session(session_id):
    if get_chat_session_owner(session_id) != session.get("user_id"):
        flash("You don't have access to this chat.", "error")
        return redirect(url_for("index"))
    session["session_id"] = session_id
    return redirect(url_for("index"))


@app.route("/new_chat", methods=["POST"])
@login_required
def new_chat():
    title = request.form.get("title", "New Chat").strip()
    new_id = create_chat_session(title if title else "New Chat", session["user_id"])
    session["session_id"] = new_id
    return redirect(url_for("index"))


@app.route("/rename_session/<int:session_id>", methods=["POST"])
@login_required
def rename_session(session_id):
    if get_chat_session_owner(session_id) != session.get("user_id"):
        flash("You don't have access to this chat.", "error")
        return redirect(url_for("index"))
    new_title = request.form.get("title", "").strip()
    if new_title:
        rename_chat_session(session_id, new_title)
    return redirect(url_for("index"))


@app.route("/delete_session/<int:session_id>")
@login_required
def delete_session(session_id):
    if get_chat_session_owner(session_id) != session.get("user_id"):
        flash("You don't have access to this chat.", "error")
        return redirect(url_for("index"))
    delete_chat_session(session_id)
    if session.get("session_id") == session_id:
        session.pop("session_id", None)
    return redirect(url_for("index"))


# --- Task 5: إدارة ملاحظات التوظيف (CRUD) ---

@app.route("/notes/add", methods=["POST"])
@login_required
def add_note():
    candidate_name = request.form.get("candidate_name", "").strip()
    note = request.form.get("note", "").strip()
    if candidate_name and note:
        add_recruiter_note(candidate_name, note)
    next_url = request.form.get("next")
    return redirect(next_url or url_for("index"))


@app.route("/notes/update/<int:note_id>", methods=["POST"])
@login_required
def update_note(note_id):
    new_note = request.form.get("note", "").strip()
    if new_note:
        update_recruiter_note(note_id, new_note)
    next_url = request.form.get("next")
    return redirect(next_url or url_for("index"))


@app.route("/notes/delete/<int:note_id>")
@login_required
def delete_note(note_id):
    delete_recruiter_note(note_id)
    next_url = request.args.get("next")
    return redirect(next_url or url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)