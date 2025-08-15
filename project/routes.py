from flask import render_template, flash, redirect, url_for, request, jsonify, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from project import db
from project.models import User, StudySession, Subject # 导入Subject
import datetime
from project.forms import LoginForm, RegistrationForm

bp = Blueprint('routes', __name__)

# --- 用户认证路由 (无变化) ---
# ... [此处省略 register, login, logout 函数] ...
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('routes.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('恭喜，您已成功注册！', 'success')
        return redirect(url_for('routes.login'))
    return render_template('register.html', title='注册', form=form)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('routes.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('无效的用户名或密码', 'danger')
            return redirect(url_for('routes.login'))
        login_user(user, remember=form.remember_me.data)
        return redirect(url_for('routes.index'))
    return render_template('login.html', title='登录', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('routes.index'))

# --- 主应用路由 ---
@bp.route('/')
@login_required
def index():
    total_seconds, days, hours, minutes, seconds, total_effective_hours = calculate_and_format_time()
    active_session = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.status.in_(['active', 'paused'])
    ).first()
    # 新增：获取用户的所有科目
    subjects = current_user.subjects.order_by(Subject.name).all()
    return render_template(
        'index.html',
        total_seconds=total_seconds,
        days=days, hours=hours, minutes=minutes, seconds=seconds,
        total_effective_hours=total_effective_hours,
        active_session_data=active_session.to_dict() if active_session else None,
        subjects=[s.to_dict() for s in subjects] # 将科目列表传给模板
    )

@bp.route('/history')
@login_required
def history():
    today_start_utc = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_utc = today_start_utc + datetime.timedelta(days=1)
    sessions = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.creation_time >= today_start_utc,
        StudySession.creation_time < today_end_utc
    ).order_by(StudySession.creation_time.desc()).all()
    return render_template('history.html', sessions=sessions, today=datetime.date.today())

# --- 学习会话 API (已更新) ---
@bp.route('/start_session', methods=['POST'])
@login_required
def start_session():
    if StudySession.query.filter(StudySession.user_id == current_user.id, StudySession.status.in_(['active', 'paused'])).first():
        return jsonify({'error': '已有正在进行的学习会话'}), 400
    data = request.get_json()
    subject_id = data.get('subject_id') # 修改：接收 subject_id
    if not subject_id:
        return jsonify({'error': '请选择一个科目'}), 400
    
    subject = Subject.query.filter_by(id=subject_id, user_id=current_user.id).first()
    if not subject:
        return jsonify({'error': '选择的科目无效'}), 404

    now = datetime.datetime.utcnow()
    new_session = StudySession(subject_id=subject.id, author=current_user, status='active', last_start_time=now)
    db.session.add(new_session)
    db.session.commit()
    return jsonify({'message': 'Session started', 'session': new_session.to_dict()}), 201

# ... [此处省略 toggle_pause_session 和 stop_session 函数，它们无需修改] ...
@bp.route('/toggle_pause_session', methods=['POST'])
@login_required
def toggle_pause_session():
    session = StudySession.query.filter(StudySession.user_id == current_user.id, StudySession.status.in_(['active', 'paused'])).first()
    if not session: return jsonify({'error': 'No active session found'}), 404
    now = datetime.datetime.utcnow()
    if session.status == 'active':
        elapsed = (now - session.last_start_time).total_seconds()
        session.accumulated_seconds += int(elapsed)
        session.status = 'paused'
        session.last_start_time = None
    elif session.status == 'paused':
        session.status = 'active'
        session.last_start_time = now
    db.session.commit()
    return jsonify({'message': f'Session {session.status}', 'session': session.to_dict()}), 200

@bp.route('/stop_session', methods=['POST'])
@login_required
def stop_session():
    session = StudySession.query.filter(StudySession.user_id == current_user.id, StudySession.status.in_(['active', 'paused'])).first()
    if not session: return jsonify({'error': 'No active session found'}), 404
    now = datetime.datetime.utcnow()
    if session.status == 'active':
        elapsed = (now - session.last_start_time).total_seconds()
        session.accumulated_seconds += int(elapsed)
    session.status = 'completed'
    session.end_time = now
    session.last_start_time = None
    db.session.commit()
    return jsonify({'message': 'Session stopped'}), 200

# --- 新增：科目管理 API ---
@bp.route('/subjects', methods=['GET'])
@login_required
def get_subjects():
    subjects = current_user.subjects.order_by(Subject.name).all()
    return jsonify([s.to_dict() for s in subjects])

@bp.route('/add_subject', methods=['POST'])
@login_required
def add_subject():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '科目名称不能为空'}), 400
    if Subject.query.filter_by(user_id=current_user.id, name=name).first():
        return jsonify({'error': '该科目已存在'}), 400
    
    new_subject = Subject(name=name, author=current_user)
    db.session.add(new_subject)
    db.session.commit()
    return jsonify(new_subject.to_dict()), 201

@bp.route('/update_subject/<int:subject_id>', methods=['POST'])
@login_required
def update_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        return jsonify({'error': '无权修改'}), 403
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '科目名称不能为空'}), 400
    if name != subject.name and Subject.query.filter_by(user_id=current_user.id, name=name).first():
        return jsonify({'error': '该科目已存在'}), 400
        
    subject.name = name
    db.session.commit()
    return jsonify(subject.to_dict())

@bp.route('/delete_subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id:
        return jsonify({'error': '无权删除'}), 403
    if subject.study_sessions.first():
        return jsonify({'error': '该科目下已有学习记录，无法删除'}), 400

    db.session.delete(subject)
    db.session.commit()
    return jsonify({'message': '删除成功'})

# --- 后台管理和倒计时逻辑 (无变化) ---
# ... [此处省略 delete_sessions, modify_session, calculate_and_format_time 函数] ...
@bp.route('/delete_sessions', methods=['POST'])
@login_required
def delete_sessions():
    data = request.get_json(); session_ids = data.get('session_ids')
    if not session_ids: return jsonify({'error': '未提供会话ID'}), 400
    sessions_to_delete = StudySession.query.filter(StudySession.user_id == current_user.id, StudySession.id.in_(session_ids)).all()
    if not sessions_to_delete: return jsonify({'error': '没有找到可删除的会话'}), 404
    for session in sessions_to_delete: db.session.delete(session)
    db.session.commit()
    return jsonify({'message': f'成功删除了 {len(sessions_to_delete)} 条记录'}), 200

@bp.route('/modify_session/<int:session_id>', methods=['POST'])
@login_required
def modify_session(session_id):
    session = StudySession.query.get_or_404(session_id)
    if session.user_id != current_user.id: return jsonify({'error': '无权修改此记录'}), 403
    data = request.get_json()
    try:
        new_duration_seconds = int(data.get('duration_seconds'))
        if new_duration_seconds < 0: raise ValueError("Duration cannot be negative.")
    except (ValueError, TypeError):
        return jsonify({'error': '无效的时长格式'}), 400
    session.accumulated_seconds = new_duration_seconds
    session.end_time = session.creation_time + datetime.timedelta(seconds=new_duration_seconds)
    db.session.commit()
    return jsonify({'message': '记录已更新'}), 200

def calculate_and_format_time():
    target_datetime = datetime.datetime(2025, 12, 20, 8, 30)
    effective_start_hour, effective_end_hour = 8, 22
    effective_hours_per_day = effective_end_hour - effective_start_hour
    now = datetime.datetime.now()
    if now >= target_datetime: return 0, 0, '00', '00', '00', '0.0'
    total_effective_seconds = 0; current_day = now.date()
    while current_day <= target_datetime.date():
        day_effective_start = datetime.datetime.combine(current_day, datetime.time(effective_start_hour, 0))
        day_effective_end = datetime.datetime.combine(current_day, datetime.time(effective_end_hour, 0))
        actual_start = max(now, day_effective_start); actual_end = min(target_datetime, day_effective_end)
        if actual_start < actual_end: total_effective_seconds += (actual_end - actual_start).total_seconds()
        current_day += datetime.timedelta(days=1)
    seconds_in_effective_day = effective_hours_per_day * 3600
    days = int(total_effective_seconds // seconds_in_effective_day)
    remaining_seconds_after_days = total_effective_seconds % seconds_in_effective_day
    hours = int(remaining_seconds_after_days // 3600)
    remaining_seconds_after_hours = remaining_seconds_after_days % 3600
    minutes = int(remaining_seconds_after_hours // 60)
    seconds = int(remaining_seconds_after_hours % 60)
    formatted_hours = str(hours).zfill(2); formatted_minutes = str(minutes).zfill(2); formatted_seconds = str(seconds).zfill(2)
    total_effective_hours = total_effective_seconds / 3600
    formatted_total_hours = f"{total_effective_hours:,.1f}"
    return int(total_effective_seconds), days, formatted_hours, formatted_minutes, formatted_seconds, formatted_total_hours