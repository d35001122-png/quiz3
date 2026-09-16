

from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import uuid
from supabase import create_client, Client


app = Flask(__name__)

app.secret_key = "quiz-admin-secret"


# Supabase
SUPABASE_URL = "https://rcrbazstbgqfmhzubmrg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjcmJhenN0YmdxZm1oenVibXJnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc2NTMxMiwiZXhwIjoyMDczMzQxMzEyfQ.Y42dwejCsS66t0d-cMXaxL5Gxm9YuWx1JebUQelC5FQ"

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# =========================================
# INDIAN TIME DISPLAY HELPER
# =========================================

def format_indian_submission_time(value):
    if not value:
        return "—"

    try:
        text = str(value).strip()

        # Supabase commonly returns UTC timestamps ending in Z.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        # Treat a timezone-less timestamp as UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convert to Indian Standard Time and show AM/PM.
        return dt.astimezone(
            ZoneInfo("Asia/Kolkata")
        ).strftime("%d-%m-%Y %I:%M %p")

    except Exception as error:
        print("SUBMITTED TIME FORMAT ERROR:", repr(error))
        return str(value)


# =========================================
# QUESTION IMAGE UPLOAD
# =========================================

QUESTION_IMAGE_BUCKET = "quiz-images"
MAX_QUESTION_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def upload_question_image(file):
    """Upload an optional question image and return its public URL."""
    if not file or not file.filename:
        return None

    content_type = (file.content_type or "").lower().strip()

    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Only PNG, JPG/JPEG and WEBP images are allowed.")

    image_bytes = file.read()

    if not image_bytes:
        return None

    if len(image_bytes) > MAX_QUESTION_IMAGE_SIZE:
        raise ValueError("Question image must be 5 MB or smaller.")

    filename = f"{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"

    supabase.storage.from_(QUESTION_IMAGE_BUCKET).upload(
        filename,
        image_bytes,
        {
            "content-type": content_type,
            "cache-control": "3600",
            "upsert": "false",
        }
    )

    return supabase.storage.from_(QUESTION_IMAGE_BUCKET).get_public_url(filename)


# =========================================
# ADMIN LOGIN
# =========================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):
            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        flash("Invalid username or password.", "error")

    return render_template("admin_login.html")


# =========================================
# ADMIN LOGOUT
# =========================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# =========================================
# ADMIN AUTH CHECK
# =========================================

def admin_required():

    return session.get("admin_logged_in") is True


# =========================================
# ADMIN DASHBOARD
# =========================================

@app.route("/admin")
def admin_dashboard():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    response = (
        supabase
        .table("quizzes")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    quizzes = response.data or []

    # Submission counts for each quiz.
    for quiz in quizzes:
        try:
            count_response = (
                supabase
                .table("quiz_responses")
                .select("id", count="exact")
                .eq("quiz_id", quiz["id"])
                .execute()
            )
            quiz["submission_count"] = count_response.count or 0
        except Exception as error:
            print("SUBMISSION COUNT ERROR:", repr(error))
            quiz["submission_count"] = 0

    return render_template(
        "admin_dashboard.html",
        quizzes=quizzes
    )


# =========================================
# CREATE QUIZ PAGE
# =========================================

@app.route("/admin/quiz/create")
def create_quiz_page():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    return render_template(
        "create_quiz.html"
    )


# =========================================
# CREATE QUIZ
# =========================================

@app.route("/admin/quiz/create", methods=["POST"])
def create_quiz():

    if not admin_required():
        return redirect(url_for("admin_login"))

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not title:
        flash("Quiz title is required.", "error")
        return redirect(url_for("create_quiz_page"))

    quiz_data = {
        "title": title,
        "description": description,
        "status": "draft",
        "winners_revealed": False,
        "leaderboard_revealed": False,
        "results_revealed": False
    }

    try:

        print("\n==============================")
        print("CREATING QUIZ")
        print("Data:", quiz_data)
        print("==============================")

        response = (
            supabase
            .table("quizzes")
            .insert(quiz_data)
            .execute()
        )

        print("SUPABASE RESPONSE:")
        print(response)

        print("RESPONSE DATA:")
        print(response.data)

        if not response.data:
            raise Exception(
                "Quiz inserted but Supabase returned no data."
            )

        quiz = response.data[0]

        flash(
            "Quiz created successfully.",
            "success"
        )

        return redirect(
            url_for(
                "add_question_page",
                quiz_id=quiz["id"]
            )
        )

    except Exception as error:

        print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("CREATE QUIZ ERROR:")
        print(repr(error))
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")

        flash(
            f"Unable to create quiz: {error}",
            "error"
        )

        return redirect(
            url_for("create_quiz_page")
        )

# =========================================
# ADD QUESTION PAGE
# =========================================

@app.route("/admin/quiz/<quiz_id>/questions/add")
def add_question_page(quiz_id):

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    quiz_response = (
        supabase
        .table("quizzes")
        .select("*")
        .eq("id", quiz_id)
        .single()
        .execute()
    )

    quiz = quiz_response.data

    question_response = (
        supabase
        .table("questions")
        .select("*")
        .eq("quiz_id", quiz_id)
        .order("question_order")
        .execute()
    )

    questions = question_response.data or []

    return render_template(
        "create_quiz.html",
        quiz=quiz,
        questions=questions
    )


# =========================================
# ADD QUESTION
# =========================================

@app.route(
    "/admin/quiz/<quiz_id>/questions/add",
    methods=["POST"]
)
def add_question(quiz_id):

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    question_text = request.form.get(
        "question_text",
        ""
    ).strip()

    option_a = request.form.get(
        "option_a",
        ""
    ).strip()

    option_b = request.form.get(
        "option_b",
        ""
    ).strip()

    option_c = request.form.get(
        "option_c",
        ""
    ).strip()

    option_d = request.form.get(
        "option_d",
        ""
    ).strip()

    correct_answer = request.form.get(
        "correct_answer",
        ""
    ).strip().upper()

    image_url = None

    if request.files.get("question_image"):
        try:
            image_url = upload_question_image(request.files.get("question_image"))
        except Exception as error:
            print("QUESTION IMAGE UPLOAD ERROR:", repr(error))
            flash(f"Unable to upload question image: {error}", "error")
            return redirect(
                url_for(
                    "add_question_page",
                    quiz_id=quiz_id
                )
            )

    if not all([
        question_text,
        option_a,
        option_b,
        option_c,
        option_d,
        correct_answer
    ]):

        flash(
            "Please fill all question fields.",
            "error"
        )

        return redirect(
            url_for(
                "add_question_page",
                quiz_id=quiz_id
            )
        )

    if correct_answer not in ["A", "B", "C", "D"]:

        flash(
            "Invalid correct answer.",
            "error"
        )

        return redirect(
            url_for(
                "add_question_page",
                quiz_id=quiz_id
            )
        )

    # Find the next question number

    existing = (
        supabase
        .table("questions")
        .select("question_order")
        .eq("quiz_id", quiz_id)
        .order("question_order", desc=True)
        .limit(1)
        .execute()
    )

    if existing.data:

        next_order = (
            existing.data[0]["question_order"] + 1
        )

    else:

        next_order = 1


    question_data = {
        "quiz_id": quiz_id,
        "question_text": question_text,
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "option_d": option_d,
        "correct_answer": correct_answer,
        "question_order": next_order,
        "image_url": image_url
    }


    try:

        (
            supabase
            .table("questions")
            .insert(question_data)
            .execute()
        )

        flash(
            f"Question {next_order} added.",
            "success"
        )

    except Exception as error:

        print(
            "ADD QUESTION ERROR:",
            error
        )

        flash(
            "Unable to add question.",
            "error"
        )

    return redirect(
        url_for(
            "add_question_page",
            quiz_id=quiz_id
        )
    )


# =========================================
# UPDATE QUESTION
# =========================================

@app.route(
    "/admin/quiz/<quiz_id>/questions/<question_id>/update",
    methods=["POST"]
)
def update_question(quiz_id, question_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    question_text = request.form.get(
        "question_text",
        ""
    ).strip()

    option_a = request.form.get(
        "option_a",
        ""
    ).strip()

    option_b = request.form.get(
        "option_b",
        ""
    ).strip()

    option_c = request.form.get(
        "option_c",
        ""
    ).strip()

    option_d = request.form.get(
        "option_d",
        ""
    ).strip()

    correct_answer = request.form.get(
        "correct_answer",
        ""
    ).strip().upper()

    new_image_url = None

    if request.files.get("question_image"):
        try:
            new_image_url = upload_question_image(request.files.get("question_image"))
        except Exception as error:
            print("QUESTION IMAGE UPLOAD ERROR:", repr(error))
            flash(f"Unable to upload question image: {error}", "error")
            return redirect(
                url_for(
                    "add_question_page",
                    quiz_id=quiz_id
                )
            )

    if not all([
        question_text,
        option_a,
        option_b,
        option_c,
        option_d,
        correct_answer
    ]):

        flash(
            "Please fill all question fields.",
            "error"
        )

        return redirect(
            url_for(
                "add_question_page",
                quiz_id=quiz_id
            )
        )

    if correct_answer not in ["A", "B", "C", "D"]:

        flash(
            "Invalid correct answer.",
            "error"
        )

        return redirect(
            url_for(
                "add_question_page",
                quiz_id=quiz_id
            )
        )

    update_data = {
        "question_text": question_text,
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "option_d": option_d,
        "correct_answer": correct_answer,
    }

    # Keep the existing image when editing unless a new image is selected.
    if new_image_url:
        update_data["image_url"] = new_image_url

    try:

        (
            supabase
            .table("questions")
            .update(update_data)
            .eq("id", question_id)
            .execute()
        )

        flash(
            "Question updated successfully.",
            "success"
        )

    except Exception as error:

        print(
            "UPDATE QUESTION ERROR:",
            error
        )

        flash(
            "Unable to update question.",
            "error"
        )

    return redirect(
        url_for(
            "add_question_page",
            quiz_id=quiz_id
        )
    )


# =========================================
# DELETE QUESTION
# =========================================

@app.route(
    "/admin/quiz/<quiz_id>/questions/<question_id>/delete",
    methods=["POST"]
)
def delete_question(quiz_id, question_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:

        (
            supabase
            .table("questions")
            .delete()
            .eq("id", question_id)
            .execute()
        )

        flash(
            "Question deleted successfully.",
            "success"
        )

    except Exception as error:

        print(
            "DELETE QUESTION ERROR:",
            error
        )

        flash(
            "Unable to delete question.",
            "error"
        )

    return redirect(
        url_for(
            "add_question_page",
            quiz_id=quiz_id
        )
    )


# =========================================
# TOGGLE QUIZ ACTIVE / DRAFT
# =========================================

@app.route("/admin/quiz/<quiz_id>/toggle-status", methods=["POST"])
def toggle_quiz_status(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        quiz_response = (
            supabase
            .table("quizzes")
            .select("id,title,status")
            .eq("id", quiz_id)
            .single()
            .execute()
        )

        quiz = quiz_response.data

        if not quiz:
            flash("Quiz not found.", "error")
            return redirect(url_for("admin_dashboard"))

        current_status = (quiz.get("status") or "draft").lower()
        new_status = "draft" if current_status == "running" else "running"

        (
            supabase
            .table("quizzes")
            .update({"status": new_status})
            .eq("id", quiz_id)
            .execute()
        )

        if new_status == "running":
            flash(f'"{quiz["title"]}" is now ACTIVE.', "success")
        else:
            flash(f'"{quiz["title"]}" moved to DRAFT.', "success")

    except Exception as error:
        print("TOGGLE QUIZ STATUS ERROR:", repr(error))
        flash(f"Unable to change quiz status: {error}", "error")

    return redirect(url_for("admin_dashboard"))


# =========================================
# STUDENT SUBMISSIONS + LEADERBOARD
# =========================================

@app.route("/admin/quiz/<quiz_id>/results")
def admin_quiz_results(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        quiz_response = (
            supabase
            .table("quizzes")
            .select("*")
            .eq("id", quiz_id)
            .single()
            .execute()
        )

        quiz = quiz_response.data

        if not quiz:
            flash("Quiz not found.", "error")
            return redirect(url_for("admin_dashboard"))

        response = (
            supabase
            .table("quiz_responses")
            .select(
                "id,quiz_id,student_id,roll_no,name,section,year,"
                "answers,total_questions,answered_questions,score,"
                "total_time_taken,submitted_at"
            )
            .eq("quiz_id", quiz_id)
            .execute()
        )

        submissions = response.data or []

        # Ranking rule:
        # 1. Higher marks first.
        # 2. If marks are equal, lower total time first.
        # 3. If both are equal, earlier submission first.
        def score_value(row):
            try:
                return float(row.get("score") or 0)
            except (TypeError, ValueError):
                return 0

        def time_value(row):
            try:
                return int(row.get("total_time_taken") or 0)
            except (TypeError, ValueError):
                return 10**12

        def submitted_value(row):
            return row.get("submitted_at") or ""

        submissions.sort(
            key=lambda row: (
                -score_value(row),
                time_value(row),
                submitted_value(row)
            )
        )

        leaderboard = []

        for index, row in enumerate(submissions, start=1):
            item = dict(row)
            item["rank"] = index
            item["score_number"] = score_value(row)
            item["time_seconds"] = time_value(row)
            leaderboard.append(item)

        # Existing declared winners for this quiz.
        winners_response = (
            supabase
            .table("winners")
            .select("*")
            .eq("quiz_id", quiz_id)
            .order("rank")
            .execute()
        )

        winners = winners_response.data or []
        winner_ids = {
            str(w.get("student_id"))
            for w in winners
            if w.get("student_id") is not None
        }

        for item in leaderboard:
            item["submitted_display"] = format_indian_submission_time(
                item.get("submitted_at")
            )

        return render_template(
            "admin_results.html",
            quiz=quiz,
            leaderboard=leaderboard,
            submissions=leaderboard,
            winners=winners,
            winner_ids=winner_ids
        )

    except Exception as error:
        print("ADMIN RESULTS ERROR:", repr(error))
        flash(f"Unable to load results: {error}", "error")
        return redirect(url_for("admin_dashboard"))



# =========================================
# DELETE INDIVIDUAL STUDENT SUBMISSION
# =========================================

@app.route(
    "/admin/quiz/<quiz_id>/submission/<submission_id>/delete",
    methods=["POST"]
)
def delete_submission(quiz_id, submission_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        # Verify that this submission belongs to this quiz.
        response = (
            supabase
            .table("quiz_responses")
            .select("id,quiz_id,student_id,name,roll_no")
            .eq("id", submission_id)
            .eq("quiz_id", quiz_id)
            .single()
            .execute()
        )

        submission = response.data

        if not submission:
            flash("Submission not found.", "error")
            return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))

        # Remove a related winner entry, if this student was declared a winner.
        student_id = submission.get("student_id")

        if student_id is not None:
            (
                supabase
                .table("winners")
                .delete()
                .eq("quiz_id", quiz_id)
                .eq("student_id", student_id)
                .execute()
            )

        # Delete only the selected submission.
        (
            supabase
            .table("quiz_responses")
            .delete()
            .eq("id", submission_id)
            .eq("quiz_id", quiz_id)
            .execute()
        )

        # Keep the winners visibility flag correct if no winners remain.
        winners_left = (
            supabase
            .table("winners")
            .select("id", count="exact")
            .eq("quiz_id", quiz_id)
            .execute()
        )

        if (winners_left.count or 0) == 0:
            (
                supabase
                .table("quizzes")
                .update({"winners_revealed": False})
                .eq("id", quiz_id)
                .execute()
            )

        flash(
            f"Submission of {submission.get('name') or 'student'} deleted successfully.",
            "success"
        )

    except Exception as error:
        print("DELETE SUBMISSION ERROR:", repr(error))
        flash(f"Unable to delete submission: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# VIEW INDIVIDUAL STUDENT SUBMISSION
# =========================================

@app.route("/admin/quiz/<quiz_id>/submission/<submission_id>")
def admin_submission_detail(quiz_id, submission_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        quiz_response = (
            supabase.table("quizzes")
            .select(
                "id,title,status,winners_revealed,"
                "leaderboard_revealed,results_revealed"
            )
            .eq("id", quiz_id)
            .single()
            .execute()
        )
        quiz = quiz_response.data

        if not quiz:
            flash("Quiz not found.", "error")
            return redirect(url_for("admin_dashboard"))

        response = (
            supabase.table("quiz_responses")
            .select(
                "id,quiz_id,student_id,roll_no,name,section,year,"
                "answers,total_questions,answered_questions,score,"
                "total_time_taken,submitted_at"
            )
            .eq("id", submission_id)
            .eq("quiz_id", quiz_id)
            .single()
            .execute()
        )
        submission = response.data

        if not submission:
            flash("Submission not found.", "error")
            return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))

        questions_response = (
            supabase.table("questions")
            .select(
                "id,question_text,image_url,option_a,option_b,option_c,option_d,"
                "correct_answer,question_order"
            )
            .eq("quiz_id", quiz_id)
            .order("question_order")
            .execute()
        )

        raw_answers = submission.get("answers") or {}
        if not isinstance(raw_answers, dict):
            raw_answers = {}

        review = []

        for index, question in enumerate(
            questions_response.data or [], start=1
        ):
            question_id = str(question.get("id"))
            student_answer = raw_answers.get(question_id)

            if student_answer is None:
                student_answer = raw_answers.get(question.get("id"))

            if student_answer is not None:
                student_answer = str(student_answer).strip().upper()

            correct_answer = (
                str(question.get("correct_answer") or "")
                .strip()
                .upper()
            )

            if not student_answer:
                state = "not_answered"
            elif student_answer == correct_answer:
                state = "correct"
            else:
                state = "wrong"

            review.append({
                "number": index,
                "question_text": question.get("question_text") or "",
                "image_url": question.get("image_url"),
                "options": {
                    "A": question.get("option_a") or "",
                    "B": question.get("option_b") or "",
                    "C": question.get("option_c") or "",
                    "D": question.get("option_d") or "",
                },
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "state": state,
            })

        return render_template(
            "admin_submission.html",
            quiz=quiz,
            submission=submission,
            questions=review,
        )

    except Exception as error:
        print("ADMIN SUBMISSION DETAIL ERROR:", repr(error))
        flash(f"Unable to load submission: {error}", "error")
        return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# DECLARE WINNERS
#
# Selecting winners:
#   - saves only selected students to winners
#   - reveals winners to ALL students
#   - also reveals leaderboard to ALL students
#   - does NOT reveal individual result/scripts
# =========================================

@app.route("/admin/quiz/<quiz_id>/declare-winners", methods=["POST"])
def declare_quiz_winners(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    selected_student_ids = list(dict.fromkeys(
        str(value).strip()
        for value in request.form.getlist("student_ids")
        if str(value).strip()
    ))

    if not selected_student_ids:
        flash("Select at least one student from the leaderboard.", "error")
        return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))

    try:
        quiz_response = (
            supabase.table("quizzes")
            .select("id,title")
            .eq("id", quiz_id)
            .single()
            .execute()
        )
        quiz = quiz_response.data

        if not quiz:
            flash("Quiz not found.", "error")
            return redirect(url_for("admin_dashboard"))

        response = (
            supabase.table("quiz_responses")
            .select(
                "id,quiz_id,student_id,roll_no,name,section,year,"
                "total_questions,answered_questions,score,"
                "total_time_taken,submitted_at"
            )
            .eq("quiz_id", quiz_id)
            .execute()
        )
        rows = response.data or []

        def score_value(row):
            try:
                return float(row.get("score") or 0)
            except (TypeError, ValueError):
                return 0

        def time_value(row):
            try:
                return int(row.get("total_time_taken") or 0)
            except (TypeError, ValueError):
                return 10**12

        rows.sort(key=lambda row: (
            -score_value(row),
            time_value(row),
            row.get("submitted_at") or ""
        ))

        ranked = {}
        for index, row in enumerate(rows, start=1):
            student_id = row.get("student_id")
            if student_id is not None:
                ranked[str(student_id)] = (index, row)

        missing = [
            student_id
            for student_id in selected_student_ids
            if student_id not in ranked
        ]

        if missing:
            flash(
                "One or more selected students are not valid submissions for this quiz.",
                "error"
            )
            return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))

        # Replace previous winners for this quiz.
        (
            supabase.table("winners")
            .delete()
            .eq("quiz_id", quiz_id)
            .execute()
        )

        declared_at = datetime.now(timezone.utc).isoformat()
        winner_rows = []

        for student_id in selected_student_ids:
            rank, row = ranked[student_id]

            winner_rows.append({
                "quiz_id": quiz_id,
                "student_id": row.get("student_id"),
                "roll_no": row.get("roll_no"),
                "name": row.get("name"),
                "section": row.get("section"),
                "year": row.get("year"),
                "rank": rank,
                "score": row.get("score") or 0,
                "total_questions": row.get("total_questions") or 0,
                "total_time_taken": row.get("total_time_taken") or 0,
                "submitted_at": row.get("submitted_at"),
                "declared_at": declared_at
            })

        (
            supabase.table("winners")
            .insert(winner_rows)
            .execute()
        )

        # Winners are independent from the leaderboard.
        # Redeclaring winners simply replaces the previous winners list.
        # The leaderboard and individual results keep their current visibility.
        (
            supabase.table("quizzes")
            .update({
                "winners_revealed": True
            })
            .eq("id", quiz_id)
            .execute()
        )

        flash(
            f"{len(winner_rows)} winner(s) declared/redeclared successfully.",
            "success"
        )

    except Exception as error:
        print("DECLARE WINNERS ERROR:", repr(error))
        flash(f"Unable to declare winners: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# DECLARE LEADERBOARD
#
# Releases leaderboard to ALL students.
# Does not release individual result/scripts.
# Does not change winners.
# =========================================

@app.route("/admin/quiz/<quiz_id>/declare-leaderboard", methods=["POST"])
def declare_quiz_leaderboard(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        (
            supabase.table("quizzes")
            .update({"leaderboard_revealed": True})
            .eq("id", quiz_id)
            .execute()
        )

        flash(
            "Leaderboard declared. All students can now see the leaderboard.",
            "success"
        )

    except Exception as error:
        print("DECLARE LEADERBOARD ERROR:", repr(error))
        flash(f"Unable to declare leaderboard: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# DECLARE INDIVIDUAL RESULTS / SCRIPTS
#
# Releases each student's own result/script.
# This is separate from winners and leaderboard.
# =========================================

@app.route("/admin/quiz/<quiz_id>/declare-results", methods=["POST"])
def declare_quiz_results(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        (
            supabase.table("quizzes")
            .update({"results_revealed": True})
            .eq("id", quiz_id)
            .execute()
        )

        flash(
            "Individual results/scripts declared. Students can now see their own results.",
            "success"
        )

    except Exception as error:
        print("DECLARE RESULTS ERROR:", repr(error))
        flash(f"Unable to declare results: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# UNDECLARE WINNERS
# =========================================

@app.route("/admin/quiz/<quiz_id>/undeclare-winners", methods=["POST"])
def undeclare_quiz_winners(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        (
            supabase.table("winners")
            .delete()
            .eq("quiz_id", quiz_id)
            .execute()
        )

        (
            supabase.table("quizzes")
            .update({"winners_revealed": False})
            .eq("id", quiz_id)
            .execute()
        )

        flash(
            "Winners undeclared. Leaderboard and individual results were not changed.",
            "success"
        )

    except Exception as error:
        print("UNDECLARE WINNERS ERROR:", repr(error))
        flash(f"Unable to undeclare winners: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# UNDECLARE LEADERBOARD
# =========================================

@app.route("/admin/quiz/<quiz_id>/undeclare-leaderboard", methods=["POST"])
def undeclare_quiz_leaderboard(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        (
            supabase.table("quizzes")
            .update({"leaderboard_revealed": False})
            .eq("id", quiz_id)
            .execute()
        )

        flash(
            "Leaderboard undeclared. Winners and individual results were not changed.",
            "success"
        )

    except Exception as error:
        print("UNDECLARE LEADERBOARD ERROR:", repr(error))
        flash(f"Unable to undeclare leaderboard: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# UNDECLARE RESULTS
# =========================================

@app.route("/admin/quiz/<quiz_id>/undeclare-results", methods=["POST"])
def undeclare_quiz_results(quiz_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    try:
        (
            supabase.table("quizzes")
            .update({"results_revealed": False})
            .eq("id", quiz_id)
            .execute()
        )

        flash(
            "Individual results/scripts undeclared. Winners and leaderboard were not changed.",
            "success"
        )

    except Exception as error:
        print("UNDECLARE RESULTS ERROR:", repr(error))
        flash(f"Unable to undeclare results: {error}", "error")

    return redirect(url_for("admin_quiz_results", quiz_id=quiz_id))


# =========================================
# HOME
# =========================================

@app.route("/")
def home():
    return redirect(url_for("admin_login"))


# =========================================
# RUN
# =========================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
