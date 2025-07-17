import os

from flask import Blueprint, render_template
import subprocess
from ..config_loader import config_background, LOG_DIR
SYSTEM_THEME = config_background()

bp = Blueprint('views', __name__)

@bp.route('/')
def index():
    def is_ffmpeg_installed():
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except:
            return False
    return render_template('index.html', ffmpeg=is_ffmpeg_installed(), system_theme=SYSTEM_THEME)



@bp.route('/view')
def view_index():
    return render_template('view.html')

@bp.route('/view/<file>')
def view(file):
    file = os.path.join(LOG_DIR, file)
    with open(file, 'r', encoding='utf-8') as f:
        contents = [line.strip() for line in f if line.strip()]
    return render_template('view.html', file_contents=contents, where=file[:-4], system_theme=SYSTEM_THEME)