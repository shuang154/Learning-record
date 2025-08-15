from flask import render_template, flash, redirect, url_for, request, jsonify, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import func
from project import db
from project.models import User, StudySession, Subject
from project.forms import LoginForm, RegistrationForm
import datetime

bp = Blueprint('routes', __name__)

# --- 用户认证路由 (无变化) ---
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
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('routes.index')
        return redirect(next_page)
    return render_template('login.html', title='登录', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('routes.index'))

# --- 主应用路由 (无变化) ---
@bp.route('/')
@login_required
def index():
    total_seconds, days, hours, minutes, seconds, total_effective_hours = calculate_and_format_time()
    active_session = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.status.in_(['active', 'paused'])
    ).first()
    subjects = current_user.subjects.order_by(Subject.name).all()
    return render_template('index.html', total_seconds=total_seconds, days=days, hours=hours, minutes=minutes, seconds=seconds, total_effective_hours=total_effective_hours, active_session_data=active_session.to_dict() if active_session else None, subjects=[s.to_dict() for s in subjects])

# --- 学习记录页面 (已更新) ---
@bp.route('/history')
@login_required
def history():
    # 这个路由现在只负责渲染页面框架，数据由JS通过API获取
    return render_template('history.html', title="学习记录")

# --- 新增：获取学习数据的API ---
@bp.route('/get_study_data')
@login_required
def get_study_data():
    # 接收两种可能的参数
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date_utc_str = request.args.get('start_date_utc')
    end_date_utc_str = request.args.get('end_date_utc')

    base_query = StudySession.query.filter(StudySession.user_id == current_user.id)
    filtered_sessions_query = base_query
    
    start_date_utc, end_date_utc = None, None

    # 优先处理来自“今日”的精确UTC时间范围
    if start_date_utc_str and end_date_utc_str:
        try:
            # Python 3.7+ can parse 'Z' with a simple replace
            start_date_utc = datetime.datetime.fromisoformat(start_date_utc_str.replace('Z', '+00:00'))
            end_date_utc = datetime.datetime.fromisoformat(end_date_utc_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': '无效的UTC日期格式'}), 400
    
    # 否则，处理来自日期选择器的 YYYY-MM-DD 格式
    elif start_date_str:
        try:
            start_date_utc = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else start_date_utc
            end_date_utc = end_date + datetime.timedelta(days=1)
        except ValueError:
            return jsonify({'error': '无效的日期格式'}), 400

    # 如果有任何一种日期范围，就应用筛选
    if start_date_utc and end_date_utc:
        filtered_sessions_query = base_query.filter(
            StudySession.creation_time >= start_date_utc, 
            StudySession.creation_time < end_date_utc
        )

    sessions = filtered_sessions_query.order_by(StudySession.creation_time.desc()).all()
    
    chart_query = db.session.query(
        Subject.name,
        func.sum(StudySession.accumulated_seconds).label('total_seconds')
    ).join(Subject).filter(
        StudySession.user_id == current_user.id
    )

    # 对图表数据也应用同样的日期筛选
    if start_date_utc and end_date_utc:
         chart_query = chart_query.filter(
            StudySession.creation_time >= start_date_utc, 
            StudySession.creation_time < end_date_utc
        )

    chart_data = [{'subject': name, 'duration': total} for name, total in chart_query.group_by(Subject.name).all() if total and total > 0]
    
    detailed_sessions = [{
        'id': s.id,
        'subject': s.subject.name,
        'creation_time': s.creation_time.strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': s.end_time.strftime('%Y-%m-%d %H:%M:%S') if s.end_time else '进行中',
        'accumulated_seconds': s.accumulated_seconds
    } for s in sessions]

    return jsonify({
        'chart_data': chart_data,
        'sessions': detailed_sessions
    })

# --- 其他API路由和后台逻辑 (无变化) ---
@bp.route('/start_session', methods=['POST'])
@login_required
def start_session():
    if StudySession.query.filter(StudySession.user_id == current_user.id, StudySession.status.in_(['active', 'paused'])).first():
        return jsonify({'error': '已有正在进行的学习会话'}), 400
    data = request.get_json()
    subject_id = data.get('subject_id')
    if not subject_id: return jsonify({'error': '请选择一个科目'}), 400
    subject = Subject.query.filter_by(id=subject_id, user_id=current_user.id).first()
    if not subject: return jsonify({'error': '选择的科目无效'}), 404
    now = datetime.datetime.utcnow()
    new_session = StudySession(subject_id=subject.id, author=current_user, status='active', last_start_time=now)
    db.session.add(new_session)
    db.session.commit()
    return jsonify({'message': 'Session started', 'session': new_session.to_dict()}), 201

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
    if not name: return jsonify({'error': '科目名称不能为空'}), 400
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
    if subject.user_id != current_user.id: return jsonify({'error': '无权修改'}), 403
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name: return jsonify({'error': '科目名称不能为空'}), 400
    if name != subject.name and Subject.query.filter_by(user_id=current_user.id, name=name).first():
        return jsonify({'error': '该科目已存在'}), 400
    subject.name = name
    db.session.commit()
    return jsonify(subject.to_dict())

@bp.route('/delete_subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != current_user.id: return jsonify({'error': '无权删除'}), 403
    if subject.study_sessions.first(): return jsonify({'error': '该科目下已有学习记录，无法删除'}), 400
    db.session.delete(subject)
    db.session.commit()
    return jsonify({'message': '删除成功'})

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


# --- 新增：数据库检验CLI命令 ---

@bp.cli.command("verify-db")
def verify_db():
    """检验数据库中的数据是否存在差错。"""
    print("--- 开始检验数据库数据 ---")
    errors_found = 0
    
    # 1. 检验学习会话 (StudySession)
    print("\n[+] 正在检验 StudySession 表...")
    all_sessions = StudySession.query.all()
    for session in all_sessions:
        # 检查逻辑错误：时长为负
        if session.accumulated_seconds < 0:
            print(f"  [错误] Session ID {session.id}: 累计时长 (accumulated_seconds) 为负数: {session.accumulated_seconds}")
            errors_found += 1
            
        # 检查逻辑错误：结束时间早于创建时间
        if session.end_time and session.end_time < session.creation_time:
            print(f"  [错误] Session ID {session.id}: 结束时间 (end_time) 早于创建时间 (creation_time)。")
            errors_found += 1
            
        # 检查状态不一致：活动状态但没有 last_start_time
        if session.status == 'active' and not session.last_start_time:
            print(f"  [错误] Session ID {session.id}: 状态为 'active' 但 last_start_time 为空。")
            errors_found += 1

        # 检查状态不一致：非活动状态但有 last_start_time
        if session.status != 'active' and session.last_start_time:
            print(f"  [错误] Session ID {session.id}: 状态为 '{session.status}' 但 last_start_time 不为空。")
            errors_found += 1
            
        # 检查外键关联：用户是否存在
        if not session.author:
            print(f"  [错误] Session ID {session.id}: 关联的用户 (user_id={session.user_id}) 不存在。")
            errors_found += 1

        # 检查外键关联：科目是否存在
        if not session.subject:
            print(f"  [错误] Session ID {session.id}: 关联的科目 (subject_id={session.subject_id}) 不存在。")
            errors_found += 1

    if not all_sessions:
        print("  StudySession 表为空，无需检验。")

    # 2. 检验科目 (Subject)
    print("\n[+] 正在检验 Subject 表...")
    all_subjects = Subject.query.all()
    for subject in all_subjects:
        # 检查科目名是否为空或仅有空格
        if not subject.name or not subject.name.strip():
            print(f"  [错误] Subject ID {subject.id}: 科目名称 (name) 为空。")
            errors_found += 1
            
        # 检查外键关联：用户是否存在
        if not subject.author:
            print(f"  [错误] Subject ID {subject.id}: 关联的用户 (user_id={subject.user_id}) 不存在。")
            errors_found += 1
            
    if not all_subjects:
        print("  Subject 表为空，无需检验。")
        
    # 3. 检验用户 (User) - 可根据需要添加更多检查
    print("\n[+] 正在检验 User 表...")
    all_users = User.query.all()
    for user in all_users:
        if not user.username or not user.username.strip():
            print(f"  [错误] User ID {user.id}: 用户名 (username) 为空。")
            errors_found += 1

    if not all_users:
        print("  User 表为空，无需检验。")

    # --- 总结 ---
    print("\n--- 检验完成 ---")
    if errors_found == 0:
        print("恭喜！未发现任何数据差错。")
    else:
        print(f"共发现 {errors_found} 个错误，请根据以上日志进行修复。")