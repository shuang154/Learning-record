import os

# 获取项目根目录的绝对路径
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # SECRET_KEY 用于保护session和CSRF攻击，请务必修改成一个随机字符串
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-hard-to-guess-string'
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'study_tracker.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False