from flask import url_for, request, redirect,Blueprint

from ..config_loader import configBackground, set_background

bp = Blueprint('config', __name__)



@bp.route('/setConfigSettings')
def setConfigSettings():
    configBackground()
    return redirect(url_for('execute.config'))

@bp.route('/set/theme', methods=['GET', 'POST'])
def set_theme():
    if request.method == 'POST':
        set_background(request.form['theme'])

    return redirect(url_for('execute.config'))