"""Study / Quiz section of Thought (optional).

Students upload PDFs, each upload is turned into a plain text file kept next to
the PDF, and that text file is the context handed to the AI when generating
questions. Generated quizzes are stored, every answer is recorded, and the
analytics page breaks results down per topic.

Disable the whole section with QUIZ_ENABLED=0. The social side of Thought never
imports openai / pypdf, so it keeps working without them.
"""
import os
import json
import uuid
from io import BytesIO
from datetime import datetime

from flask import (render_template, request, redirect, url_for, flash, jsonify,
                   send_file, abort)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from core import app, db, DESCENDING

QUIZ_ENABLED = os.environ.get("QUIZ_ENABLED", "1").lower() not in ("0", "false", "off", "no")
QUIZ_PATH = os.environ.get("QUIZ_PATH", "QUIZ/")
QUIZ_MODEL = os.environ.get("QUIZ_MODEL", "meta-llama/llama-3.3-70b-instruct")
MAX_PDF_BYTES = 25 * 1024 * 1024
CONTEXT_CHAR_BUDGET = 60000  # total characters of text sent to the model
MIN_QUESTIONS, MAX_QUESTIONS = 3, 30
LETTERS = ("A", "B", "C", "D")


@app.context_processor
def inject_quiz_flag():
    return dict(quiz_enabled=QUIZ_ENABLED)


# ---------------------------------------------------------------- storage

def _user_dir(user_id):
    path = os.path.join(QUIZ_PATH, user_id)
    os.makedirs(path, exist_ok=True)
    return path


def _doc_paths(doc):
    base = os.path.join(_user_dir(doc["user_id"]), doc["_id"])
    return base + ".pdf", base + ".txt"


def _own_doc(doc_id):
    doc = db.quiz_docs.find_one({"_id": doc_id, "user_id": current_user._id})
    if not doc:
        abort(404)
    return doc


def _own_set(set_id):
    qset = db.quiz_sets.find_one({"_id": set_id, "user_id": current_user._id})
    if not qset:
        abort(404)
    return qset


def _extract_pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p), len(pages)


# ---------------------------------------------------------------- AI

def _api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    try:
        with open("openrouterapikey.txt") as f:
            return f.read().strip()
    except OSError:
        return None


def _build_context(docs):
    """Read the local .txt files of the chosen documents, sharing the budget."""
    share = CONTEXT_CHAR_BUDGET // max(len(docs), 1)
    parts = []
    for doc in docs:
        with open(_doc_paths(doc)[1], encoding="utf-8", errors="replace") as f:
            text = f.read()[:share]
        parts.append(f"--- START OF DOCUMENT: {doc['title']} ---\n{text}\n--- END OF DOCUMENT: {doc['title']} ---")
    return "\n\n".join(parts)


def _prompt(context, titles, count, focus):
    focus_line = f"- Focus especially on: {focus}\n" if focus else ""
    return f"""Create exactly {count} multiple-choice questions based ONLY on the documents below.
Return ONLY valid JSON, no Markdown, no code fences, using exactly this structure:

{{"questions": [{{
  "topic": "Short topic name (1-3 words)",
  "question": "Question text",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "answer": "A",
  "explanation": "Short, student-friendly explanation"
}}]}}

Rules:
- Exactly {count} questions, each with exactly 4 options A-D and one correct answer.
- "topic" names the subject area the question tests. Reuse the same topic string
  for related questions so results can be grouped by topic (aim for 3-8 topics overall).
- Spread questions across all documents: {", ".join(titles)}.
{focus_line}
Documents:
{context}
"""


def parse_questions(raw):
    """Parse and validate the model's JSON. Raises ValueError on bad output."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "", 1).replace("```", "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"model did not return valid JSON ({e})")
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("no questions in model response")
    questions = []
    for q in items:
        opts = q.get("options") if isinstance(q, dict) else None
        if (not isinstance(opts, dict) or set(opts) != set(LETTERS)
                or q.get("answer") not in LETTERS or not q.get("question")):
            continue  # skip malformed questions rather than failing the batch
        questions.append({
            "id": uuid.uuid4().hex[:12],
            "topic": (str(q.get("topic") or "General").strip() or "General")[:40],
            "question": str(q["question"]),
            "options": {k: str(opts[k]) for k in LETTERS},
            "answer": q["answer"],
            "explanation": str(q.get("explanation") or ""),
        })
    if not questions:
        raise ValueError("every question in the response was malformed")
    return questions


def generate_questions(docs, count, focus):
    key = _api_key()
    if not key:
        raise RuntimeError("AI is not configured (set OPENROUTER_API_KEY or create openrouterapikey.txt).")
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
    prompt = _prompt(_build_context(docs), [d["title"] for d in docs], count, focus)
    response = client.chat.completions.create(
        model=QUIZ_MODEL, messages=[{"role": "user", "content": prompt}])
    return parse_questions(response.choices[0].message.content)


# ---------------------------------------------------------------- analytics

def compute_analytics(answers):
    """answers: list of quiz_answers docs. Returns overall + per-topic stats."""
    topics = {}
    attempts = {}
    for a in answers:
        t = topics.setdefault(a["topic"], {"topic": a["topic"], "correct": 0, "wrong": 0, "attempts": {}})
        t["correct" if a["correct"] else "wrong"] += 1
        at = t["attempts"].setdefault(a["attempt_id"], {"ts": a["answered_at"], "c": 0, "n": 0})
        at["n"] += 1
        at["c"] += 1 if a["correct"] else 0
        glob = attempts.setdefault(a["attempt_id"], {"ts": a["answered_at"], "c": 0, "n": 0, "title": a.get("set_title", "")})
        glob["n"] += 1
        glob["c"] += 1 if a["correct"] else 0

    def series(d):
        rows = sorted(d.values(), key=lambda r: r["ts"])
        return [{"label": r["ts"].strftime("%b %d %H:%M"), "accuracy": round(100 * r["c"] / r["n"]),
                 "title": r.get("title", "")} for r in rows]

    topic_list = []
    for t in topics.values():
        total = t["correct"] + t["wrong"]
        topic_list.append({"topic": t["topic"], "correct": t["correct"], "wrong": t["wrong"],
                           "total": total, "accuracy": round(100 * t["correct"] / total),
                           "trend": series(t["attempts"])})
    topic_list.sort(key=lambda t: (t["accuracy"], -t["total"]))  # weakest first
    total = len(answers)
    correct = sum(1 for a in answers if a["correct"])
    return {"total": total, "correct": correct, "wrong": total - correct,
            "accuracy": round(100 * correct / total) if total else 0,
            "topics": topic_list, "timeline": series(attempts)}


# ---------------------------------------------------------------- routes

def _guard():
    if not QUIZ_ENABLED:
        abort(404)


@app.route("/quiz")
@login_required
def quiz():
    _guard()
    uid = current_user._id
    docs = list(db.quiz_docs.find({"user_id": uid}).sort("uploaded_at", DESCENDING))
    sets = list(db.quiz_sets.find({"user_id": uid}).sort("created_at", DESCENDING))
    return render_template("quiz/dashboard.html", docs=docs, sets=sets,
                           ai_ready=bool(_api_key()), min_q=MIN_QUESTIONS, max_q=MAX_QUESTIONS)


@app.route("/quiz/upload", methods=["POST"])
@login_required
def quiz_upload():
    _guard()
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        flash("Choose one or more PDF files.")
        return redirect(url_for("quiz"))
    for f in files:
        name = secure_filename(f.filename)
        data = f.read(MAX_PDF_BYTES + 1)
        if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
            flash(f"{name or 'file'}: only PDF files are supported.")
            continue
        if len(data) > MAX_PDF_BYTES:
            flash(f"{name}: larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.")
            continue
        try:
            text, pages = _extract_pdf_text(data)
        except Exception as e:
            flash(f"{name}: could not read this PDF ({e}).")
            continue
        if not text.strip():
            flash(f"{name}: no selectable text found (scanned PDFs are not supported).")
            continue
        doc = {"_id": uuid.uuid4().hex, "user_id": current_user._id,
               "title": name.rsplit(".", 1)[0][:80] or "Untitled", "filename": name,
               "pages": pages, "chars": len(text), "size": len(data),
               "uploaded_at": datetime.now()}
        pdf_path, txt_path = _doc_paths(doc)
        with open(pdf_path, "wb") as out:
            out.write(data)
        with open(txt_path, "w", encoding="utf-8") as out:  # the local context file for the AI
            out.write(text)
        db.quiz_docs.insert_one(doc)
        flash(f"Uploaded {name} ({pages} pages).")
    return redirect(url_for("quiz"))


@app.route("/quiz/doc/<doc_id>/pdf")
@login_required
def quiz_doc_pdf(doc_id):
    _guard()
    doc = _own_doc(doc_id)
    return send_file(os.path.abspath(_doc_paths(doc)[0]), mimetype="application/pdf",
                     download_name=doc["filename"])


@app.route("/quiz/doc/<doc_id>/text")
@login_required
def quiz_doc_text(doc_id):
    _guard()
    doc = _own_doc(doc_id)
    return send_file(os.path.abspath(_doc_paths(doc)[1]), mimetype="text/plain; charset=utf-8")


@app.route("/quiz/doc/<doc_id>/delete", methods=["POST"])
@login_required
def quiz_doc_delete(doc_id):
    _guard()
    doc = _own_doc(doc_id)
    for path in _doc_paths(doc):
        if os.path.exists(path):
            os.remove(path)
    db.quiz_docs.delete_one({"_id": doc_id})
    flash(f"Deleted {doc['filename']}. Quizzes already generated from it are kept.")
    return redirect(url_for("quiz"))


@app.route("/quiz/generate", methods=["POST"])
@login_required
def quiz_generate():
    _guard()
    ids = request.form.getlist("docs")
    docs = [d for d in (db.quiz_docs.find_one({"_id": i, "user_id": current_user._id}) for i in ids) if d]
    if not docs:
        flash("Select at least one document.")
        return redirect(url_for("quiz"))
    try:
        count = max(MIN_QUESTIONS, min(MAX_QUESTIONS, int(request.form.get("count", 10))))
    except ValueError:
        count = 10
    focus = (request.form.get("focus") or "").strip()[:200]
    try:
        questions = generate_questions(docs, count, focus)
    except Exception as e:
        flash(f"Quiz generation failed: {e}")
        return redirect(url_for("quiz"))
    title = (request.form.get("title") or "").strip()[:80] or \
        ", ".join(d["title"] for d in docs)[:80] + f" ({datetime.now().strftime('%b %d')})"
    qset = {"_id": uuid.uuid4().hex, "user_id": current_user._id, "title": title,
            "doc_titles": [d["title"] for d in docs], "questions": questions,
            "created_at": datetime.now()}
    db.quiz_sets.insert_one(qset)
    return redirect(url_for("quiz_take", set_id=qset["_id"]))


@app.route("/quiz/set/<set_id>")
@login_required
def quiz_take(set_id):
    _guard()
    qset = _own_set(set_id)
    # correct answers stay on the server until a question is checked
    public = [{k: v for k, v in q.items() if k not in ("answer", "explanation")} for q in qset["questions"]]
    return render_template("quiz/take.html", qset=qset, questions=public, attempt_id=uuid.uuid4().hex)


@app.route("/quiz/set/<set_id>/answer", methods=["POST"])
@login_required
def quiz_answer(set_id):
    _guard()
    qset = _own_set(set_id)
    body = request.get_json(silent=True) or {}
    q = next((q for q in qset["questions"] if q["id"] == body.get("question_id")), None)
    selected, attempt_id = body.get("selected"), str(body.get("attempt_id") or "")
    if not q or selected not in LETTERS or not attempt_id:
        return jsonify(error="bad request"), 400
    if db.quiz_answers.find_one({"user_id": current_user._id, "attempt_id": attempt_id, "question_id": q["id"]}):
        return jsonify(error="already answered"), 409
    correct = selected == q["answer"]
    db.quiz_answers.insert_one({
        "user_id": current_user._id, "set_id": set_id, "set_title": qset["title"],
        "attempt_id": attempt_id, "question_id": q["id"], "topic": q["topic"],
        "selected": selected, "correct": correct, "answered_at": datetime.now()})
    return jsonify(correct=correct, answer=q["answer"], explanation=q["explanation"])


@app.route("/quiz/set/<set_id>/delete", methods=["POST"])
@login_required
def quiz_set_delete(set_id):
    _guard()
    qset = _own_set(set_id)
    db.quiz_sets.delete_one({"_id": set_id})
    db.quiz_answers.delete_many({"user_id": current_user._id, "set_id": set_id})
    flash(f"Deleted quiz “{qset['title']}” and its results.")
    return redirect(url_for("quiz"))


@app.route("/quiz/analytics")
@login_required
def quiz_analytics():
    _guard()
    answers = list(db.quiz_answers.find({"user_id": current_user._id}))
    return render_template("quiz/analytics.html", stats=compute_analytics(answers))
