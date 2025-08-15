import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'routes.login'
login_manager.login_message = "请先登录以访问此页面。"
login_manager.login_message_category = "info"

# 新增：自定义Jinja2过滤器，用于格式化时长
def format_duration_filter(seconds):
    if seconds is None:
        return "-"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts: # 如果时长小于1分钟，也显示秒
        parts.append(f"{seconds}s")
        
    return " ".join(parts)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # 注册自定义过滤器
    app.jinja_env.filters['duration'] = format_duration_filter

    from project.routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    with app.app_context():
        from project import models
        db.create_all()

    return app