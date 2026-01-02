from flask import Flask

def create_app():
    app = Flask(__name__)

    from .config_loader import config_background
    config_background()

    from .routes import register_routes
    register_routes(app)

    return app
