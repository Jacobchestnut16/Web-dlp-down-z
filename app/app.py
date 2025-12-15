import os
import subprocess
import time
import queue
import threading
import re
import logging
import json
import datetime
from urllib.parse import urlparse
from flask import Flask, render_template, url_for, request, redirect, Response, stream_with_context
from yt_dlp import YoutubeDL
import requests


app = Flask(__name__)

PLAYLIST_FILE = 'data/default-playlist.json'
PLAYLIST_PROCESS_FILE = 'logs/playlist_processed.txt'
DOWNLOAD_FILE = 'data/default-download.json'
PROCESS_FILE = 'logs/process.txt'
CONFIG_FILE = 'instance/config.json'
DOWNLOAD_DIR = '~/Downloads'
FILE_CONFIG = 'instance/file_config.json'
SYSTEM_CONFIG = 'system.json'
HIERARCHY_DIR = False
active_downloads = {}  # {file_name: threading.Thread}
stop_flags = {}        # {file_name: threading.Event}
SYSTEM_THEME = 'default'


@app.route('/')
def index():
    def is_ffmpeg_installed():
        try:
            # Try running `ffmpeg -version`
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    return render_template('index.html', ffmpeg=is_ffmpeg_installed(), system_theme=SYSTEM_THEME)




@app.route('/save/installs', methods=['POST'])
def save_installs():
    if request.method == 'POST':
        install = request.form['install']
        install = os.path.normpath(install)
        if not install.endswith(os.path.sep):
            install += os.path.sep
        where = request.form['file']
        name = (where.split('-'))[0]
        type = ((where.split('-'))[1].split('.'))[0]
        logging.info(f"{name} install {type}: {install}")
        with open (FILE_CONFIG, 'r', encoding='utf-8') as f:
            config = json.load(f)
        for item in config:
            if item['file'] == name:
                if type == 'download':
                    item['install-directory'] = install
                elif type == 'playlist':
                    item['install-playlist'] = install
        with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return redirect(url_for('edit', file=where))

@app.route('/create-file')
def create_file():
    return render_template('createfile.html', system_theme=SYSTEM_THEME)

@app.route('/new', methods=['GET', 'POST'])
def new():
    if request.method == 'POST':
        file = request.form.get('file')
        def normalize_filename(name):
            # Remove illegal characters (for Windows)
            return re.sub(r'[<>:"/\\|?*\-]', '', name).strip()
        for type in ['playlist', 'download']:
            fileName = normalize_filename(file)+'-'+type+'.json'
            try:
                with open(fileName, 'x', encoding='utf-8') as f:
                    data = []
                    f.write(json.dumps(data))
            except FileExistsError:
                pass
        with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
            data.append(
                {
                    'file': file,
                    'install-playlist': file+'-download.json',
                    'install-directory': DOWNLOAD_DIR
                }
            )
            f.write(json.dumps(data))
        return redirect(url_for('edit', file=file+'-playlist.json'))


@app.route('/group/action', methods=['GET', 'POST'])
def group_action():
    def save(file, websites, filenames, description, duration, downloadAs, thumbnail):
        try:
            entries = []
            seen_urls = set()
            for name, site, desc, dur, dow, thumb in zip(filenames, websites, description, duration, downloadAs, thumbnail):
                if site not in seen_urls:
                    if thumb:
                        entries.append({
                            'file': name,
                            'url': site,
                            'description': desc,
                            'duration': dur,
                            'downloadAs': dow,
                            'thumbnail': thumb,
                        })
                    else:
                        entries.append({
                            'file': name,
                            'url': site,
                            'description': desc,
                            'duration': dur,
                            'downloadAs': dow,
                        })
                    seen_urls.add(site)
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=4)
        except Exception as e:
            print("ERROR:",e)
    def save_playlist(file, websites, filenames):
        try:
            entries = []
            seen_urls = set()
            for name, site in zip(filenames, websites):
                if site not in seen_urls:
                    entries.append({
                        'file': name,
                        'url': site
                    })
                    seen_urls.add(site)
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=4)
        except Exception as e:
            print("ERROR:",e)
    if request.method == 'POST':
        file = request.form.get('file')
        action = request.form.get('action')
        filenames = request.form.getlist('filename')
        websites = request.form.getlist('website')
        description = request.form.getlist('description')
        duration = request.form.getlist('duration')
        downloadAs = request.form.getlist('downloadAs')
        thumb = request.form.getlist('thumb')
        type = (file.split('-')[1]).split('.')[0]
        if type == 'playlist':
            save_playlist(file, websites, filenames)
        if type == 'download':
            save(file, websites, filenames, description, duration, downloadAs, thumb)

        if action == 'execute':
            return redirect(url_for('execute_installation', file=file))
        elif action == 'remove':
            return redirect(url_for('remove_group', group=file.split('-')[0]))
        else:
            if type == 'download':
                return redirect(url_for('run_thumbnail_generator', file=file))
            elif type == 'playlist':
                return redirect(url_for('edit', file=file))

@app.route('/group/remove/<group>')
def remove_group(group):
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for f in range(len(data)):
        if group == data[f]['file']:
            logging.log(logging.INFO, 'remove', data[f]['file'],"at",f)
            try:
                data.pop(f)
                os.remove(group+'-playlist.json')
                os.remove(group + '-download.json')
            except Exception as e:
                logging.log(logging.ERROR, e)
    with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return redirect(url_for('edit_index'))

@app.route('/save', methods=['GET', 'POST'])
def save():
    filenames = request.form.getlist('filename')
    websites = request.form.getlist('website')
    description = request.form.getlist('description')
    duration = request.form.getlist('duration')
    file = request.form.get('file')

    if file == CONFIG_FILE:
        data = dict(zip(filenames, websites))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return redirect(url_for('setConfigSettings'))

    try:
        entries = []
        for name, site, description, duration in zip(filenames, websites, description, duration):
            entries.append({
                'file': name,
                'url': site,
                'description': description,
                'duration': duration
            })

        with open(file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=4)
    except Exception as e:
        return f"Error: {e}"
    else:
        if file == DOWNLOAD_FILE:
            return redirect(url_for('run_thumbnail_generator', file=DOWNLOAD_FILE))
        return redirect(url_for('run_thumbnail_generator', file=file))  # or back to 'edit' if that’s the page

@app.route('/save/downloadAs', methods=['GET', 'POST'])
def saveAS():
    where = request.form['file']
    name = (where.split('-'))[0]
    downloadAs = request.form.get('downloadAs')
    with open(FILE_CONFIG if name != 'default' else 'default-config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    if name != 'default':
        for item in config:
            if item['file'] == name:
                item['downloadAs'] = downloadAs
    else:
        config['downloadAs'] = downloadAs
    with open(FILE_CONFIG if name != 'default' else 'default-config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)
    return redirect(url_for('edit', file=where))











if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    try:
        with open('instance/config.json', 'x', encoding='utf-8') as f:
            f.write('''"web-dlp-down-z Log file": "logs",
            "Download To": "~/Downloads",
            "Download File": "default-default-download.json",
            "Playlist File": "default-default-playlist.json",
            "Download full logs": "log_download.txt",
            "Playlist full logs": "log_download.txt",
            "Process": "process.txt",
            "Playlist Processed": "playlist_processed.txt",
            "hierarchy": "false"
            ''')
    except FileExistsError:
        pass
    configBackground()
    files = [PLAYLIST_FILE, PLAYLIST_PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE]
    for f in files:
        try:
            with open(f, 'x') as file:
                file.write('')
        except FileExistsError:
            pass
    app.run(debug=True, host='0.0.0.0', port=8080)
