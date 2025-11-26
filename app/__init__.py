from flask import Flask, session
from .config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Additional session configuration for Safari compatibility
    # Safari requires explicit SameSite=None with Secure for cross-site cookies
    # But for localhost, we use Lax which Safari accepts
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SECURE'] = False  # False for localhost (http://)
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
    
    # Ensure cookies work across browsers (especially Safari)
    app.config['SESSION_COOKIE_NAME'] = 'agriflow_session'
    app.config['SESSION_COOKIE_PATH'] = '/'
    app.config['SESSION_COOKIE_DOMAIN'] = None  # None for localhost

    # Middleware to ensure session is permanent (helps with Safari)
    @app.before_request
    def make_session_permanent():
        session.permanent = True

    from .routes import bp
    app.register_blueprint(bp)

    return app