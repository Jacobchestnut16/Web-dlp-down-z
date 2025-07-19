import os
import re
import logging
import json
from flask import render_template, url_for, request, redirect,Blueprint

from app.config_loader import (FILE_CONFIG, DOWNLOAD_DIR, PLAYLIST_PROCESS_FILE, DOWNLOAD_FILE,
                               HIERARCHY_DIR, CONFIG_FILE, PROCESS_FILE, DEFAULT_CONFIG_FILE, DATA_DIR)
from ..config_loader import config_background


bp = Blueprint('edit', __name__)

@bp.route('/edit')
def edit_index():
    funfiles = []

    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            funfiles.append({'file': item['file'], 'install-playlist': item['install-playlist'], 'install-directory': item['install-directory']})

    print("FILES LOADED:", funfiles)
    return render_template('file.html', funfiles=funfiles, system_theme=config_background())

@bp.route('/edit/<file>', methods=['GET', 'POST'])
def edit(file):

    entries = []
    funfiles = []
    downloadAs = 'default'
    file_name = file
    file = os.path.join(DATA_DIR, file_name)
    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Debug print

            if isinstance(data, list):
                for item in data:
                    filename = item.get('file', '').strip()
                    website = item.get('url', '').strip()
                    duration_raw = item.get('duration', '')

                    # Check if duration is actually numeric
                    if isinstance(duration_raw, (int, float)) or str(duration_raw).isdigit():
                        duration_secs = int(duration_raw)
                        minutes = duration_secs // 60
                        seconds = duration_secs % 60
                        duration_formatted = f"{minutes}m {seconds}s"
                    else:
                        # Not a number? Assume it's a string like "PRIVATE VIDEO"
                        duration_formatted = str(duration_raw).strip()
                    if filename:  # Only add if filename exists
                        entries.append({
                            'filename': filename,
                            'website': website,
                            'duration': duration_formatted,
                            'description': item.get('description', ''),
                            'thumbnail': item.get('thumbnail', ''),
                            'downloadAs': item.get('downloadAs', 'default'),
                        })
    except FileNotFoundError:
        print("default-playlist.json not found.")
    except json.JSONDecodeError as e:
        print("JSON decode error:", e)

    try:
        named = (file_name.split('-'))[0]
        type = ((file_name.split('-'))[1].split('.'))[0]
    except Exception as e:
        named = None
        type = None

    install = None

    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            if named == item['file']:
                downloadAs = item.get('downloadAs', 'web_default')
                if type == 'download':
                    install = item['install-directory']
                elif type == 'playlist':
                    install = item['install-playlist']
                    install = install.split('-')[0]
            funfiles.append({'file': item['file'], 'install-playlist': item['install-playlist'], 'install-directory': item['install-directory']})
    installOpts = []
    if type == 'playlist':
        with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
            files = json.load(f)
            for item in files:
                installOpts.append(item['file'])

    try:
        cnt = len(data) if data else 0
    except Exception as e:
        cnt = 0

    if named == 'default':
        with open(DEFAULT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        downloadAs = data['downloadAs']

    return render_template('file.html', entries=entries, where=file_name, funfiles=funfiles, type=type,
                           install=install, installOpts=installOpts, name=named, files=cnt,
                           downloadAs=(downloadAs if downloadAs else 'web_default'), system_theme=config_background())


@bp.route('/save/installs', methods=['POST'])
def save_installs():
    install = os.path.normpath(request.form['install'])
    if not install.endswith(os.path.sep):
        install += os.path.sep
    where = request.form['file']
    name = where.split('-')[0]
    type = where.split('-')[1].split('.')[0]

    logging.info(f"{name} install {type}: {install}")
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for item in config:
        if item['file'] == name:
            if type == 'download':
                item['install-directory'] = install
            elif type == 'playlist':
                item['install-playlist'] = install
    with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    return redirect(url_for('edit.edit', file=where))


@bp.route('/create-file')
def create_file():
    return render_template('createfile.html', system_theme=config_background())


@bp.route('/new', methods=['GET', 'POST'])
def new():
    if request.method == 'POST':
        file = request.form.get('file')

        def normalize_filename(name):
            return re.sub(r'[<>:"/\\|?*\-]', '', name).strip()

        for type in ['playlist', 'download']:
            file_name = normalize_filename(file) + '-' + type + '.json'
            file_name = os.path.join(DATA_DIR, file_name)
            try:
                with open(file_name, 'x', encoding='utf-8') as f:
                    json.dump([], f)
            except FileExistsError:
                pass

        with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data.append({
            'file': file,
            'install-playlist': file + '-download.json',
            'install-directory': DOWNLOAD_DIR
        })

        with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        return redirect(url_for('edit.edit', file=file + '-playlist.json'))


@bp.route('/group/action', methods=['GET', 'POST'])
def group_action():
    def save(file, websites, filenames, description, duration, downloadAs, thumbnail):
        try:
            entries, seen_urls = [], set()
            for name, site, desc, dur, dow, thumb in zip(filenames, websites, description, duration, downloadAs, thumbnail):
                if site not in seen_urls:
                    entry = {
                        'file': name,
                        'url': site,
                        'description': desc,
                        'duration': dur,
                        'downloadAs': dow
                    }
                    if thumb:
                        entry['thumbnail'] = thumb
                    entries.append(entry)
                    seen_urls.add(site)
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=4)
        except Exception as e:
            print("ERROR:", e)

    def save_playlist(file, websites, filenames):
        try:
            entries, seen_urls = [], set()
            for name, site in zip(filenames, websites):
                if site not in seen_urls:
                    entries.append({'file': name, 'url': site})
                    seen_urls.add(site)
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=4)
        except Exception as e:
            print("ERROR:", e)

    if request.method == 'POST':
        o_file = request.form.get('file')
        file = os.path.join(DATA_DIR, file)
        action = request.form.get('action')
        filenames = request.form.getlist('filename')
        websites = request.form.getlist('website')
        description = request.form.getlist('description')
        duration = request.form.getlist('duration')
        downloadAs = request.form.getlist('downloadAs')
        thumb = request.form.getlist('thumb')
        type = o_file.split('-')[1].split('.')[0]

        if type == 'playlist':
            save_playlist(file, websites, filenames)
        elif type == 'download':
            save(file, websites, filenames, description, duration, downloadAs, thumb)

        if action == 'execute':
            return redirect(url_for('execute.execute_installation', file=o_file))
        elif action == 'remove':
            return redirect(url_for('edit.remove_group', group=o_file.split('-')[0]))
        else:
            if type == 'download':
                return redirect(url_for('execute.run_thumbnail_generator', file=o_file))
            else:
                return redirect(url_for('edit.edit', file=o_file))


@bp.route('/group/remove/<group>')
def remove_group(group):
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for i in range(len(data)):
        if group == data[i]['file']:
            logging.info(f'remove {data[i]["file"]} at {i}')
            try:
                data.pop(i)
                os.remove(f'{os.path.join(DATA_DIR, group)}-playlist.json')
                os.remove(f'{os.path.join(DATA_DIR, group)}-download.json')
            except Exception as e:
                logging.error(e)
            break

    with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    return redirect(url_for('edit.edit_index'))


@bp.route('/save', methods=['GET', 'POST'])
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
        return redirect(url_for('config.setConfigSettings'))

    try:
        entries = []
        for name, site, desc, dur in zip(filenames, websites, description, duration):
            entries.append({
                'file': name,
                'url': site,
                'description': desc,
                'duration': dur
            })
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=4)
    except Exception as e:
        return f"Error: {e}"
    else:
        return redirect(url_for('execute.run_thumbnail_generator', file=file))


@bp.route('/save/downloadAs', methods=['GET', 'POST'])
def saveAS():
    where = request.form['file']
    name = where.split('-')[0]
    downloadAs = request.form.get('downloadAs')

    config_path = FILE_CONFIG if name != 'default' else 'default-config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if name != 'default':
        for item in config:
            if item['file'] == name:
                item['downloadAs'] = downloadAs
    else:
        config['downloadAs'] = downloadAs

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

    return redirect(url_for('edit.edit', file=where))
