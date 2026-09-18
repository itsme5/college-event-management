import os
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, abort, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from models import db, User, Event, Registration
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
import io
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this')

database_url = os.environ.get('DATABASE_URL', 'sqlite:///cems.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def generate_certificate_pdf(user_name, event_title, event_date):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    c.setStrokeColor(HexColor("#4e54c8"))
    c.setLineWidth(4)
    c.rect(20, 20, width - 40, height - 40)

    c.setStrokeColor(HexColor("#8f94fb"))
    c.setLineWidth(1)
    c.rect(30, 30, width - 60, height - 60)

    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(HexColor("#4e54c8"))
    c.drawCentredString(width / 2, height - 120, "Certificate of Participation")

    c.setFont("Helvetica", 16)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height - 160, "This certificate is proudly presented to")

    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(HexColor("#000000"))
    c.drawCentredString(width / 2, height - 210, user_name)

    c.setFont("Helvetica", 15)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height - 250, "for successfully attending")

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(HexColor("#4e54c8"))
    c.drawCentredString(width / 2, height - 285, event_title)

    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height - 315, f"held on {event_date}")

    c.setFont("Helvetica-Oblique", 11)
    c.setFillColor(HexColor("#777777"))
    c.drawCentredString(width / 2, 70, "College Event Management System")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))

        new_user = User(name=name, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("student_dashboard"))

@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    total_events = Event.query.count()
    return render_template("admin_dashboard.html", total_events=total_events)

@app.route("/student/dashboard")
@login_required
def student_dashboard():
    my_registrations_count = Registration.query.filter_by(user_id=current_user.id).count()

    my_registered_ids = {
        r.event_id for r in Registration.query.filter_by(user_id=current_user.id).all()
    }

    recommended_events = (
        Event.query
        .filter(~Event.id.in_(my_registered_ids) if my_registered_ids else True)
        .filter(Event.event_date >= datetime.utcnow())
        .order_by(Event.event_date)
        .limit(3)
        .all()
    )

    return render_template(
        "student_dashboard.html",
        my_registrations_count=my_registrations_count,
        recommended_events=recommended_events
    )

# ---------------- EVENT MANAGEMENT (Admin only) ----------------

@app.route("/admin/events")
@login_required
@admin_required
def manage_events():
    events = Event.query.order_by(Event.event_date).all()
    return render_template("manage_events.html", events=events)

@app.route("/admin/events/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_event():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        location = request.form.get("location")
        event_date_str = request.form.get("event_date")
        capacity = request.form.get("capacity")

        try:
            event_date = datetime.strptime(event_date_str, "%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            flash("Please provide a valid date and time.", "danger")
            return redirect(url_for("create_event"))

        new_event = Event(
            title=title,
            description=description,
            location=location,
            event_date=event_date,
            capacity=int(capacity) if capacity else 50,
            created_by=current_user.id
        )
        db.session.add(new_event)
        db.session.commit()

        flash("Event created successfully!", "success")
        return redirect(url_for("manage_events"))

    return render_template("event_form.html", event=None)

@app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)

    if request.method == "POST":
        event.title = request.form.get("title")
        event.description = request.form.get("description")
        event.location = request.form.get("location")
        event_date_str = request.form.get("event_date")
        capacity = request.form.get("capacity")

        try:
            event.event_date = datetime.strptime(event_date_str, "%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            flash("Please provide a valid date and time.", "danger")
            return redirect(url_for("edit_event", event_id=event.id))

        event.capacity = int(capacity) if capacity else event.capacity

        db.session.commit()
        flash("Event updated successfully!", "success")
        return redirect(url_for("manage_events"))

    return render_template("event_form.html", event=event)

@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash("Event deleted.", "info")
    return redirect(url_for("manage_events"))

# ---------------- ATTENDANCE MANAGEMENT (Admin only) ----------------

@app.route("/admin/events/<int:event_id>/attendance", methods=["GET", "POST"])
@login_required
@admin_required
def manage_attendance(event_id):
    event = Event.query.get_or_404(event_id)
    registrations = Registration.query.filter_by(event_id=event.id).join(User).order_by(User.name).all()

    if request.method == "POST":
        attended_ids = set(request.form.getlist("attended"))
        for reg in registrations:
            if str(reg.id) in attended_ids:
                if not reg.attended:
                    reg.attended = True
                    reg.checked_in_at = datetime.utcnow()
            else:
                reg.attended = False
                reg.checked_in_at = None
        db.session.commit()
        flash("Attendance updated successfully!", "success")
        return redirect(url_for("manage_attendance", event_id=event.id))

    return render_template("manage_attendance.html", event=event, registrations=registrations)

# ---------------- USER MANAGEMENT (Admin only) ----------------

@app.route("/admin/users")
@login_required
@admin_required
def manage_users():
    users = User.query.order_by(User.role.desc(), User.name).all()
    return render_template("manage_users.html", users=users)

# ---------------- REPORTS (Admin only) ----------------

@app.route("/admin/reports")
@login_required
@admin_required
def reports():
    total_events = Event.query.count()
    total_students = User.query.filter_by(role="student").count()
    total_registrations = Registration.query.count()
    total_attended = Registration.query.filter_by(attended=True).count()

    attendance_rate = round((total_attended / total_registrations * 100), 1) if total_registrations > 0 else 0

    events_summary = []
    for event in Event.query.order_by(Event.event_date).all():
        events_summary.append({
            "title": event.title,
            "date": event.event_date,
            "capacity": event.capacity,
            "registered": event.registered_count,
            "attended": event.attended_count
        })

    return render_template(
        "reports.html",
        total_events=total_events,
        total_students=total_students,
        total_registrations=total_registrations,
        total_attended=total_attended,
        attendance_rate=attendance_rate,
        events_summary=events_summary
    )

# ---------------- STUDENT EVENT BROWSING & REGISTRATION ----------------

@app.route("/events")
@login_required
def browse_events():
    events = Event.query.order_by(Event.event_date).all()
    my_registered_ids = set()
    if current_user.role == "student":
        my_registered_ids = {
            r.event_id for r in Registration.query.filter_by(user_id=current_user.id).all()
        }
    return render_template("browse_events.html", events=events, my_registered_ids=my_registered_ids)

@app.route("/events/<int:event_id>/register", methods=["POST"])
@login_required
def register_for_event(event_id):
    event = Event.query.get_or_404(event_id)

    if current_user.role != "student":
        flash("Only students can register for events.", "warning")
        return redirect(url_for("browse_events"))

    existing = Registration.query.filter_by(user_id=current_user.id, event_id=event.id).first()
    if existing:
        flash("You are already registered for this event.", "info")
        return redirect(url_for("browse_events"))

    if event.is_full:
        flash("Sorry, this event is full.", "danger")
        return redirect(url_for("browse_events"))

    new_registration = Registration(user_id=current_user.id, event_id=event.id)
    db.session.add(new_registration)
    db.session.commit()

    flash(f"Successfully registered for {event.title}!", "success")
    return redirect(url_for("browse_events"))

@app.route("/events/<int:event_id>/unregister", methods=["POST"])
@login_required
def unregister_from_event(event_id):
    registration = Registration.query.filter_by(user_id=current_user.id, event_id=event_id).first()
    if registration:
        db.session.delete(registration)
        db.session.commit()
        flash("Registration cancelled.", "info")
    return redirect(url_for("browse_events"))

@app.route("/my-registrations")
@login_required
def my_registrations():
    registrations = Registration.query.filter_by(user_id=current_user.id).order_by(Registration.registered_at.desc()).all()
    return render_template("my_registrations.html", registrations=registrations)

@app.route("/certificate/<int:registration_id>")
@login_required
def download_certificate(registration_id):
    registration = Registration.query.get_or_404(registration_id)

    if registration.user_id != current_user.id:
        abort(403)

    if not registration.attended:
        flash("Certificate is only available after attendance is marked.", "warning")
        return redirect(url_for("my_registrations"))

    pdf_buffer = generate_certificate_pdf(
        user_name=registration.user.name,
        event_title=registration.event.title,
        event_date=registration.event.event_date.strftime('%d %B %Y')
    )

    filename = f"certificate_{registration.event.title.replace(' ', '_')}.pdf"
    return send_file(pdf_buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)