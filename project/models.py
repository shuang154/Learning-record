from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from project import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    sessions = db.relationship('StudySession', backref='author', lazy='dynamic')
    # 新增：用户与科目的关联
    subjects = db.relationship('Subject', backref='author', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# 新增：Subject模型
class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    study_sessions = db.relationship('StudySession', backref='subject', lazy='dynamic')

    def to_dict(self):
        return {'id': self.id, 'name': self.name}

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # 修改：subject字段改为subject_id外键
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    
    status = db.Column(db.String(20), default='active', nullable=False)
    creation_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime)
    accumulated_seconds = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        current_total_seconds = self.accumulated_seconds
        if self.status == 'active' and self.last_start_time:
            current_total_seconds += (datetime.utcnow() - self.last_start_time).total_seconds()

        return {
            'id': self.id,
            'subject': self.subject.to_dict(), # 返回完整的subject对象
            'status': self.status,
            'accumulated_seconds': self.accumulated_seconds,
            'last_start_time_utc': self.last_start_time.isoformat() + 'Z' if self.last_start_time else None,
            'current_total_seconds': current_total_seconds
        }