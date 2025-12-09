from .routes import bp

# Import route modules so blueprints register all endpoints
from . import public  # noqa: F401
from . import client  # noqa: F401
from . import company  # noqa: F401
from . import driver  # noqa: F401

