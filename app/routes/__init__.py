from . import views, edit, execute, config, update, extractor

def register_routes(app):
    app.register_blueprint(views.bp)
    app.register_blueprint(edit.bp)
    app.register_blueprint(execute.bp)
    app.register_blueprint(config.bp)
    app.register_blueprint(update.bp)
    app.register_blueprint(extractor.bp)
