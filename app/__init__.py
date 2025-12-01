from flask import Flask, session
from .config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400
    app.config['SESSION_COOKIE_NAME'] = 'agriflow_session'
    app.config['SESSION_COOKIE_PATH'] = '/'
    app.config['SESSION_COOKIE_DOMAIN'] = None

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    from .routes import bp
    app.register_blueprint(bp)

    return app