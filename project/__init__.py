import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

# 初始化扩展
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'routes.login' # 未登录用户访问保护页面时，将跳转到登录页面
login_manager.login_message = "请先登录以访问此页面。"
login_manager.login_message_category = "info"

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # 注册蓝图
    from project.routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    # 在应用上下文中创建数据库表
    with app.app_context():
        # 导入模型，确保SQLAlchemy能找到它们
        from project import models
        db.create_all()

    return app