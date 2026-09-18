from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(150), nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=50)
    image_filename = db.Column(db.String(255), nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref='events_created')

    @property
    def registered_count(self):
        return len(self.registrations)

    @property
    def seats_left(self):
        return self.capacity - self.registered_count

    @property
    def is_full(self):
        return self.seats_left <= 0

    @property
    def attended_count(self):
        return sum(1 for r in self.registrations if r.attended)


class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    attended = db.Column(db.Boolean, default=False, nullable=False)
    checked_in_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='registrations')
    event = db.relationship('Event', backref='registrations')

    __table_args__ = (db.UniqueConstraint('user_id', 'event_id', name='unique_registration'),)