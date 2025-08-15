from flask import render_template, flash, redirect, url_for, request, jsonify, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from project import db
from project.models import User, StudySession
from project.forms import LoginForm, RegistrationForm
import datetime

bp = Blueprint('routes', __name__)

# --- 用户认证路由 ---

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('routes.index'))
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
    if current_user.is_authenticated:
        return redirect(url_for('routes.index'))
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
    
    # 检查用户是否有正在进行的学习会话
    active_session = StudySession.query.filter_by(author=current_user, end_time=None).first()
    
    return render_template(
        'index.html',
        total_seconds=total_seconds,
        days=days, hours=hours, minutes=minutes, seconds=seconds,
        total_effective_hours=total_effective_hours,
        active_session_data=active_session.to_dict() if active_session else None
    )

@bp.route('/history')
@login_required
def history():
    # 获取今天的日期范围 (UTC)
    today_start_utc = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_utc = today_start_utc + datetime.timedelta(days=1)

    # 查询当前用户今天的学习记录
    sessions = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.start_time >= today_start_utc,
        StudySession.start_time < today_end_utc
    ).order_by(StudySession.start_time.desc()).all()
    
    return render_template('history.html', sessions=sessions, today=datetime.date.today())

# --- API 路由 ---

@bp.route('/start_session', methods=['POST'])
@login_required
def start_session():
    # 确保没有正在进行的会话
    if StudySession.query.filter_by(author=current_user, end_time=None).first():
        return jsonify({'error': '已有正在进行的学习会话'}), 400

    data = request.get_json()
    subject = data.get('subject')
    if not subject:
        return jsonify({'error': 'Subject is required'}), 400

    new_session = StudySession(subject=subject, author=current_user)
    db.session.add(new_session)
    db.session.commit()
    return jsonify({'message': 'Session started', 'session': new_session.to_dict()}), 201

@bp.route('/stop_session', methods=['POST'])
@login_required
def stop_session():
    session = StudySession.query.filter_by(author=current_user, end_time=None).first()
    if not session:
        return jsonify({'error': 'No active session found'}), 404

    session.end_time = datetime.datetime.utcnow()
    duration = session.end_time - session.start_time
    session.duration_seconds = int(duration.total_seconds())
    db.session.commit()
    return jsonify({'message': 'Session stopped'}), 200

# (在 routes.py 中添加以下代码)

@bp.route('/delete_sessions', methods=['POST'])
@login_required
def delete_sessions():
    data = request.get_json()
    session_ids = data.get('session_ids')
    if not session_ids:
        return jsonify({'error': '未提供会话ID'}), 400

    # 查询属于当前用户且在ID列表中的会话
    sessions_to_delete = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.id.in_(session_ids)
    ).all()

    if not sessions_to_delete:
        return jsonify({'error': '没有找到可删除的会话'}), 404
    
    for session in sessions_to_delete:
        db.session.delete(session)
    
    db.session.commit()
    return jsonify({'message': f'成功删除了 {len(sessions_to_delete)} 条记录'}), 200

@bp.route('/modify_session/<int:session_id>', methods=['POST'])
@login_required
def modify_session(session_id):
    session = StudySession.query.get_or_404(session_id)

    # 验证该记录是否属于当前用户
    if session.user_id != current_user.id:
        return jsonify({'error': '无权修改此记录'}), 403

    data = request.get_json()
    try:
        new_duration_minutes = float(data.get('duration_minutes'))
    except (ValueError, TypeError):
        return jsonify({'error': '无效的时长格式'}), 400

    new_duration_seconds = int(new_duration_minutes * 60)
    session.duration_seconds = new_duration_seconds
    
    # 如果修改时长，也应该更新结束时间以保持一致性
    session.end_time = session.start_time + datetime.timedelta(seconds=new_duration_seconds)
    
    db.session.commit()
    return jsonify({'message': '记录已更新'}), 200

# --- 倒计时计算逻辑 (与之前相同) ---
def calculate_and_format_time():
    target_datetime = datetime.datetime(2025, 12, 20, 8, 30)
    effective_start_hour = 8
    effective_end_hour = 22
    effective_hours_per_day = effective_end_hour - effective_start_hour
    now = datetime.datetime.now()
    if now >= target_datetime:
        return 0, 0, '00', '00', '00', '0.0'
    total_effective_seconds = 0
    current_day = now.date()
    while current_day <= target_datetime.date():
        day_effective_start = datetime.datetime.combine(current_day, datetime.time(effective_start_hour, 0))
        day_effective_end = datetime.datetime.combine(current_day, datetime.time(effective_end_hour, 0))
        actual_start = max(now, day_effective_start)
        actual_end = min(target_datetime, day_effective_end)
        if actual_start < actual_end:
            total_effective_seconds += (actual_end - actual_start).total_seconds()
        current_day += datetime.timedelta(days=1)
    seconds_in_effective_day = effective_hours_per_day * 3600
    days = int(total_effective_seconds // seconds_in_effective_day)
    remaining_seconds_after_days = total_effective_seconds % seconds_in_effective_day
    hours = int(remaining_seconds_after_days // 3600)
    remaining_seconds_after_hours = remaining_seconds_after_days % 3600
    minutes = int(remaining_seconds_after_hours // 60)
    seconds = int(remaining_seconds_after_hours % 60)
    formatted_hours = str(hours).zfill(2)
    formatted_minutes = str(minutes).zfill(2)
    formatted_seconds = str(seconds).zfill(2)
    total_effective_hours = total_effective_seconds / 3600
    formatted_total_hours = f"{total_effective_hours:,.1f}"
    return int(total_effective_seconds), days, formatted_hours, formatted_minutes, formatted_seconds, formatted_total_hours