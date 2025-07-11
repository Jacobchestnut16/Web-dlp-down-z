import os
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


app = Flask(__name__)

PLAYLIST_FILE = 'default-playlist.json'
PLAYLIST_PROCESS_FILE = 'playlist_processed.txt'
DOWNLOAD_FILE = 'default-download.json'
PROCESS_FILE = 'process.txt'
CONFIG_FILE = 'config.json'
DOWNLOAD_DIR = '~/Downloads'
FILE_CONFIG = 'file_config.json'
SYSTEM_CONFIG = 'system_config.json'
HIERARCHY_DIR = False


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/view')
def view_index():
    return render_template('view.html')
@app.route('/view/<file>')
def view(file):
    with open(file, 'r', encoding='utf-8') as f:
        contents = [line.strip() for line in f if line.strip()]
    return render_template('view.html', file_contents=contents, where=file[:-4])


@app.route('/edit')
def edit_index():
    funfiles = []

    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            funfiles.append({'file': item['file'], 'install-playlist': item['install-playlist'], 'install-directory': item['install-directory']})

    print("FILES LOADED:", funfiles)
    return render_template('file.html', funfiles=funfiles)
@app.route('/edit/<file>', methods=['GET', 'POST'])
def edit(file):

    entries = []
    funfiles = []

    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Debug print

            if isinstance(data, list):
                for item in data:
                    filename = item.get('file', '').strip()
                    website = item.get('url', '').strip()
                    duration = item.get('duration', '')
                    if filename:  # Only add if filename exists
                        entries.append({
                            'filename': filename,
                            'website': website,
                            'duration': duration,
                            'description': item.get('description', '')
                        })
    except FileNotFoundError:
        print("default-playlist.json not found.")
    except json.JSONDecodeError as e:
        print("JSON decode error:", e)

    try:
        print("FILE LOADED:", file)
        named = (file.split('-'))[0]
        type = ((file.split('-'))[1].split('.'))[0]
    except Exception as e:
        named = None
        type = None

    install = None

    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            if named == item['file']:
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

    return render_template('file.html', entries=entries, where=file, funfiles=funfiles, type=type,
                           install=install, installOpts=installOpts, name=named, files=cnt)

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
        with open (FILE_CONFIG, 'r', encoding='utf-8') as f:
            config = json.load(f)
        for item in config:
            if item['file'] == name:
                if type == 'download':
                    item['install-download'] = install
                elif type == 'playlist':
                    item['install-playlist'] = install
        with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return redirect(url_for('edit', file=where))

@app.route('/create-file')
def create_file():
    return render_template('createfile.html')

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
        return redirect(url_for('edit', file=file))


@app.route('/group/action', methods=['GET', 'POST'])
def group_action():
    def save(file, websites, filenames):
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
        type = (file.split('-')[1]).split('.')[0]
        print(websites, filenames)
        save(file, websites, filenames)
        if action == 'execute':
            return redirect(url_for('execute_installation', file=file))
        else:
            if type == 'download':
                return redirect(url_for('run_thumbnail_generator', file=file))
            elif type == 'playlist':
                return redirect(url_for('edit', file=file))




@app.route('/save', methods=['GET', 'POST'])
def save():
    filenames = request.form.getlist('filename')
    websites = request.form.getlist('website')
    file = request.form.get('file')

    if file == CONFIG_FILE:
        data = dict(zip(filenames, websites))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return redirect(url_for('setConfigSettings'))

    try:
        entries = []
        for name, site in zip(filenames, websites):
            entries.append({
                'file': name,
                'url': site
            })

        with open(file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=4)
    except Exception as e:
        return f"Error: {e}"
    else:
        if file == DOWNLOAD_FILE:
            return redirect(url_for('run_thumbnail_generator', file=DOWNLOAD_FILE))
        return redirect(url_for('run_thumbnail_generator', file=file))  # or back to 'edit' if that’s the page

@app.route('/run/thumbnail-generator/<file>')
def run_thumbnail_generator(file):
    return render_template('thumb.html', file=file)

@app.route('/execute')
def execute_index():
    funfiles = []
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            funfiles.append({'name': item['file'].split('-')[0]})
    return render_template('execute.html', download_dir=DOWNLOAD_DIR, funfiles=funfiles)

@app.route('/execute/install/<file>')
def execute_installation(file):
    type=(file.split('-')[1]).split('.')[0]
    print('downloading',type,file)
    return render_template('install.html', file=file, type=type , download_dir=DOWNLOAD_DIR)

@app.route('/execute/thumbnail/<file>')
def execute_thumbnail(file):
    logging.basicConfig(level=logging.DEBUG)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    def generate(master_file):
        messages = queue.Queue()

        retry = []

        yield "data: Starting Downloading process...\n\n"
        try:
            with open(master_file, 'r', encoding='utf-8') as f:
                download_json = json.load(f)

            total = len(download_json)
            current_index = 0

            download_files = download_json.copy()

            # Step 2: Process each line one by one
            for file in download_files:
                current_index += 1
                url = file["url"]  # filename URL
                name = file["file"] if file["file"] else "unnamed"

                def find_file_without_ext(directory, filename_without_ext):
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            name, ext = os.path.splitext(file)
                            if name == filename_without_ext:
                                return os.path.join(root, file)
                    return None

                if not file.get("duration") or not file.get("description"):
                    ydl_opts = {
                        'skip_download': True,
                        'quiet': True
                    }
                    with YoutubeDL(ydl_opts) as ydl:
                        try:
                            info = ydl.extract_info(url, download=False)
                            duration = info.get('duration')
                            description = info.get('description')
                        except Exception as e:
                            if "private" in str(e).lower():
                                duration = 'PRIVATE VIDEO'
                            else:
                                duration = 'None'
                            description = ''

                    with open(master_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)

                    updated = False
                    for entry in json_data:
                        if entry.get("file") == name and entry.get("url") == url:
                            entry["duration"] = duration
                            entry["description"] = description
                            updated = True
                            print(f"✅ Set duration for: {entry['file']} — {duration} seconds")

                    if updated:
                        with open(master_file, 'w', encoding='utf-8') as f:
                            json.dump(json_data, f, indent=4)
                    else:
                        print("⚠️ Matching entry not found in JSON. Nothing updated.")

                if find_file_without_ext('static/thumb', name):
                    yield f"data: ▶️ Skipping already known ({current_index}/{total}): {name}, {url}\n\n"
                    continue

                # Progress hook to receive download updates
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        percent = ansi_escape.sub('', d.get('_percent_str', '').strip())
                        speed = ansi_escape.sub('', d.get('_speed_str', '').strip())
                        eta = ansi_escape.sub('', d.get('_eta_str', '').strip())

                        messages.put(f"data: Downloading: {percent} at {speed}, ETA {eta} [{current_index}/{total}]\n\n")
                    elif d['status'] == 'finished':
                        messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                    elif d['status'] == 'error':
                        messages.put("data: ❌ Download failed.\n\n")
                    else:
                        print("STATUS:",d['status'])

                tmp_dir = os.path.join(".", "static", "thumb")
                os.makedirs(tmp_dir, exist_ok=True)

                # Build the output template path safely
                out_path = os.path.join(tmp_dir, f"{name}.%(ext)s")
                ydl_opts = {
                    'skip_download': True,
                    'writethumbnail': True,
                    'convert_thumbnails': 'jpg',
                    'outtmpl': f'{out_path}',
                    'progress_hooks': [progress_hook]
                }


                try:
                    def download_and_drain():
                        messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                        try:
                            with YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                            # Signal end
                            messages.put("done")
                        except Exception as e:
                            print(e)
                            messages.put(f"data: ❌ Download failed.\n\n")
                            messages.put(f"data: {str(e).splitlines()[0]}\n\n")
                            messages.put("error")

                    # Start download in a thread to allow streaming progress
                    thread = threading.Thread(target=download_and_drain)
                    thread.start()


                    # Stream messages from queue in real-time
                    while True:
                        try:
                            msg = messages.get(timeout=1)
                        except queue.Empty:
                            yield f"data: waiting...\n\n"
                            continue
                        if msg == "done":
                            download_json.pop(0)
                            break
                        if msg == "error":
                            retry.append({
                                'url': url,
                                'file': name
                            })
                            yield f"data: Error: {msg}\n\n"
                            download_json.pop(0)
                            break
                        yield msg

                except Exception as ve:
                    yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"
                    logging.error(f"data: Error processing {name},{url}: {str(ve).splitlines()[0]}")

        except Exception as ve:
            yield f"data: 🚫 Fatal error: {str(ve)}\n\n"
            logging.error(f"data: Fatal error: {str(ve)}")

        retries = 0
        while retries < 3:
            retries += 1
            yield f"Retrying {retries}/3 retries...\n"
            if len(retry) > 0:
                download_json = retry
                retry = []
                total = len(download_json)
                current_index = 0

                # Step 2: Process each line one by one
                download_files = download_json.copy()

                for file in download_files:
                    current_index += 1
                    url = file["url"]  # filename URL
                    name = file["file"] if file["file"] else "unnamed"

                    def find_file_without_ext(directory, filename_without_ext):
                        for root, dirs, files in os.walk(directory):
                            for file in files:
                                name, ext = os.path.splitext(file)
                                if name == filename_without_ext:
                                    return os.path.join(root, file)
                        return None

                    if find_file_without_ext('static/thumb', name):
                        yield f"data: ▶️ Skipping already known ({current_index}/{total}): {name}, {url}\n\n"
                        continue

                    # Progress hook to receive download updates
                    def progress_hook(d):
                        if d['status'] == 'downloading':
                            percent = ansi_escape.sub('', d.get('_percent_str', '').strip())
                            speed = ansi_escape.sub('', d.get('_speed_str', '').strip())
                            eta = ansi_escape.sub('', d.get('_eta_str', '').strip())

                            messages.put(
                                f"data: Downloading: {percent} at {speed}, ETA {eta} [{current_index}/{total}]\n\n")
                        elif d['status'] == 'finished':
                            messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                        elif d['status'] == 'error':
                            messages.put("data: ❌ Download failed.\n\n")
                        else:
                            print("STATUS:", d['status'])

                    tmp_dir = os.path.join(".", "static", "thumb")
                    os.makedirs(tmp_dir, exist_ok=True)

                    # Build the output template path safely
                    out_path = os.path.join(tmp_dir, f"{name}.%(ext)s")
                    ydl_opts = {
                        'skip_download': True,
                        'writethumbnail': True,
                        'convert_thumbnails': 'jpg',
                        'outtmpl': f'{out_path}',
                        'progress_hooks': [progress_hook]
                    }

                    try:
                        def download_and_drain():
                            messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                            try:
                                with YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([url])
                                # Signal end
                                messages.put("done")
                            except Exception as e:
                                print(e)
                                messages.put(f"data: ❌ Download failed.\n\n")
                                messages.put(f"data: {str(e).splitlines()[0]}\n\n")
                                messages.put("error")

                        # Start download in a thread to allow streaming progress
                        thread = threading.Thread(target=download_and_drain)
                        thread.start()

                        # Stream messages from queue in real-time
                        while True:
                            try:
                                msg = messages.get(timeout=1)
                            except queue.Empty:
                                yield f"data: waiting...\n\n"
                                continue
                            if msg == "done":
                                download_json.pop(0)
                                break
                            if msg == "error":
                                retry.append({
                                    'url': url,
                                    'file': name
                                })
                                yield f"data: Error: {msg}\n\n"
                                download_json.pop(0)
                                break
                            yield msg

                    except Exception as ve:
                        yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"
                        logging.error(f"data: Error processing {name},{url}: {str(ve).splitlines()[0]}")

        yield "data: ✅ Done.\n\n"
        logging.info("data: Done.")
        yield f"data: REDIRECT /edit/{master_file}\n\n"

    return Response(stream_with_context(generate(file)), content_type='text/event-stream')


@app.route('/execute/playlist')
def execute_playlist():
    def generate():
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist'
        }

        yield "data: Starting playlist separation...\n\n"

        try:
            with open(PLAYLIST_FILE, 'r', encoding='utf-8') as f:
                playlist_json = json.load(f)

            # Step 2: Process each line one by one
            for playlist in playlist_json:
                playlist_json.pop(0)
                url = playlist["url"]  # filename URL
                name = playlist["file"] if playlist["file"] else "unnamed"

                yield f"data: ▶️ Processing playlist: {url}\n\n"

                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)

                        if '_type' in info and info['_type'] == 'playlist':
                            entries = info.get('entries', [])
                            for entry in entries:
                                video_title = entry.get('title', 'Unknown title')
                                video_url = entry.get('url')
                                duration = info.get("duration")

                                if not video_url:
                                    yield f"data: ⚠️ Skipped video (missing URL): {video_title}\n\n"
                                    continue

                                full_url = entry.get('url')

                                if video_title.lower() in ['unknown title', 'unknown']:
                                    parsed = urlparse(full_url)
                                    last_segment = parsed.path.rstrip('/').split('/')[-1] or 'untitled'
                                    video_title = last_segment


                                if os.path.exists(DOWNLOAD_FILE):
                                    with open(DOWNLOAD_FILE, 'r', encoding='utf-8') as f:
                                        try:
                                            entries = json.load(f)
                                            if not isinstance(entries, list):
                                                entries = []
                                        except json.JSONDecodeError:
                                            entries = []

                                existing_urls = {entry.get('url') for entry in entries}

                                    # Step 2: Append new entry
                                if full_url not in existing_urls:
                                    entries.append({
                                        "file": video_title,
                                        "url": full_url,
                                        "duration": duration
                                    })
                                    existing_urls.add(full_url)

                                # Step 3: Write updated list back to file
                                with open(DOWNLOAD_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(entries, f, indent=4)

                                yield f"data: ✅ Added: {video_title}\n\n"

                        else:
                            yield f"data: ⚠️ Not a playlist: {url}\n\n"
                except Exception as ve:
                    yield f"data: ❌ Error processing {url}: {str(ve).splitlines()[0]}\n\n"


                time.sleep(0.2)

                yield f"data: ▶️ Reached Playlist end: {url}\n\n"

                with open(PLAYLIST_PROCESS_FILE, 'a', encoding='utf-8') as out:
                    log_time = datetime.datetime.now()
                    log_time = log_time.strftime('%Y-%m-%d %H:%M')
                    out.write(f'{log_time} {name} {url}\n')

                with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
                    json.dump(playlist_json, f, indent=4)


        except Exception as e:
            yield f"data: 🚫 Fatal error: {str(e)}\n\n"

        yield "data: ✅ Done.\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/execute/playlist/<file>')
def execute_playlist_file(file):
    logging.basicConfig(level=logging.DEBUG)

    file_name = (file.split('-')[0])
    file_type = ((file.split('-')[1]).split('.'))[0]
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
    for filef in files:
        if filef['file'] == file_name:
            download_to = filef['install-playlist']
            download_to = os.path.normpath(download_to)

    logging.info(f'Flattening to {download_to}')
    def generate(file):
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist'
        }

        yield "data: Starting playlist separation...\n\n"

        try:
            with open(file, 'r', encoding='utf-8') as f:
                playlist_json = json.load(f)

            # Step 2: Process each line one by one
            for playlist in playlist_json:
                playlist_json.pop(0)
                url = playlist["url"]  # filename URL
                name = playlist["file"] if playlist["file"] else "unnamed"

                yield f"data: ▶️ Processing playlist: {url}\n\n"
                logging.info(f'Processing playlist: {url}')

                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)

                        if '_type' in info and info['_type'] == 'playlist':
                            entries = info.get('entries', [])
                            # print(entries)
                            for entry in entries:
                                video_title = entry.get('title', 'Unknown title')
                                video_url = entry.get('url')
                                duration = info.get("duration")
                                description = info.get("description")

                                if not video_url:
                                    yield f"data: ⚠️ Skipped video (missing URL): {video_title}\n\n"
                                    continue

                                full_url = entry.get('url')

                                if video_title.lower() in ['unknown title', 'unknown']:
                                    parsed = urlparse(full_url)
                                    last_segment = parsed.path.rstrip('/').split('/')[-1] or 'untitled'
                                    video_title = last_segment

                                logging.info(f'Playlist found: {video_title}')

                                # Save it
                                if os.path.exists(download_to):
                                    with open(download_to, 'r', encoding='utf-8') as f:
                                        try:
                                            entries = json.load(f)
                                            if not isinstance(entries, list):
                                                entries = []
                                        except json.JSONDecodeError:
                                            entries = []

                                existing_urls = {entry.get('url') for entry in entries}

                                    # Step 2: Append new entry
                                if full_url not in existing_urls:
                                    entries.append({
                                        "file": video_title,
                                        "url": full_url,
                                        "duration": duration,
                                        "description": description
                                    })
                                    existing_urls.add(full_url)

                                # Step 3: Write updated list back to file
                                with open(download_to, 'w', encoding='utf-8') as f:
                                    json.dump(entries, f, indent=4)

                                yield f"data: ✅ Added: {video_title}\n\n"
                                logging.info(f'Added: {video_title}')

                        else:
                            yield f"data: ⚠️ Not a playlist: {url}\n\n"
                            logging.warn(f'Not a playlist: {url}')
                except Exception as ve:
                    yield f"data: ❌ Error processing {url}: {str(ve).splitlines()[0]}\n\n"
                    logging.error(f'Error: {ve}')


                time.sleep(0.2)

                yield f"data: ▶️ Reached Playlist end: {url}\n\n"
                logging.info(f'Reached Playlist end: {url}')

                with open(PLAYLIST_PROCESS_FILE, 'a', encoding='utf-8') as out:
                    log_time = datetime.datetime.now()
                    log_time = log_time.strftime('%Y-%m-%d %H:%M')
                    out.write(f'{log_time} {name} {url}\n')

                with open(file, 'w', encoding='utf-8') as f:
                    json.dump(playlist_json, f, indent=4)


        except Exception as e:
            yield f"data: 🚫 Fatal error: {str(e)}\n\n"
            logging.error(f'Error: {e}')

        yield "data: ✅ Done.\n\n"
        yield f"data: REDIRECT /run/thumbnail-generator/{download_to}\n\n"

    return Response(stream_with_context(generate(file)), content_type='text/event-stream')

@app.route('/execute/download')
def execute_download():
    logging.basicConfig(level=logging.DEBUG)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    def generate():
        messages = queue.Queue()

        yield "data: Starting Downloading process...\n\n"
        logging.info("data: Downloading started")
        try:
            with open(DOWNLOAD_FILE, 'r', encoding='utf-8') as f:
                download_json = json.load(f)

            total = len(download_json)
            current_index = 0

            # Step 2: Process each line one by one
            for file in download_json:
                current_index += 1
                url = file["url"]  # filename URL
                name = file["file"] if file["file"] else "unnamed"

                # Progress hook to receive download updates
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        percent = ansi_escape.sub('', d.get('_percent_str', '').strip())
                        speed = ansi_escape.sub('', d.get('_speed_str', '').strip())
                        eta = ansi_escape.sub('', d.get('_eta_str', '').strip())

                        messages.put(f"data: Downloading: {percent} at {speed}, ETA {eta} [{current_index}/{total}]\n\n")
                    elif d['status'] == 'finished':
                        messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                    elif d['status'] == 'error':
                        messages.put("data: ❌ Download failed.\n\n")
                ydl_opts = {
                    'format': 'best',
                    'outtmpl': f'{download_to}%(title)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegMetadata'}],
                    'addmetadata': True,
                    'progress_hooks': [progress_hook],  # ✅ This is critical!
                }


                try:
                    def download_and_drain():
                        messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                        try:
                            with YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                            # Signal end
                            messages.put("done")
                        except Exception as e:
                            print(e)
                            messages.put(f"data: ❌ Download failed.\n\n")
                            messages.put(f"data: {str(e).splitlines()[0]}\n\n")
                            messages.put("error")

                    # Start download in a thread to allow streaming progress
                    thread = threading.Thread(target=download_and_drain)
                    thread.start()


                    # Stream messages from queue in real-time
                    while True:
                        try:
                            msg = messages.get(timeout=1)
                        except queue.Empty:
                            yield f"data: waiting...\n\n"
                            continue
                        if msg == "done":
                            download_json.pop(0)
                            break
                        if msg == "error":
                            retry.append({
                                'url': url,
                                'file': name
                            })
                            yield f"data: Error: {msg}\n\n"
                            download_json.pop(0)
                            break
                        yield msg

                    with open(PROCESS_FILE, 'a', encoding='utf-8') as out:
                        time = datetime.datetime.now()
                        time = time.strftime('%Y-%m-%d %H:%M')
                        out.write(f"{time} {name} {url}\n")

                    # Remove the finished URL from the list
                    with open(DOWNLOAD_FILE, 'w', encoding='utf-8') as f:
                        json.dump(download_json, f, indent=4)

                except Exception as ve:
                    yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"
                    logging.error(f"data: Error processing {name},{url}: {str(ve).splitlines()[0]}")

        except Exception as ve:
            yield f"data: 🚫 Fatal error: {str(ve)}\n\n"
            logging.error(f"data: Fatal error: {str(ve)}")

        yield "data: ✅ Done.\n\n"
        logging.info("data: Done.")

    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/execute/download/<file>')
def execute_download_file(file):
    logging.basicConfig(level=logging.DEBUG)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

    file_name = (file.split('-')[0])
    file_type = ((file.split('-')[1]).split('.'))[0]
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
    for filef in files:
        if filef['file'] == file_name:
            download_to = filef['install-directory']
            download_to = os.path.normpath(download_to)
            if not download_to.endswith(os.path.sep):
                download_to += os.path.sep
            try:
                os.makedirs(os.path.dirname(download_to), exist_ok=True)
            except OSError as err:
                print(f"data: Error: {str(err)}\n\n")

    def generate(download_file, download_to):
        messages = queue.Queue()
        retry = []

        yield "data: Starting Downloading process...\n\n"
        logging.info("data: Downloading started")
        try:
            with open(download_file, 'r', encoding='utf-8') as f:
                download_json = json.load(f)

            total = len(download_json)
            current_index = 0

            download_files = download_json.copy()

            # Step 2: Process each line one by one
            for file in download_files:
                current_index += 1
                url = file["url"]  # filename URL
                name = file["file"] if file["file"] else "unnamed"

                # Progress hook to receive download updates
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        percent = ansi_escape.sub('', d.get('_percent_str', '').strip())
                        speed = ansi_escape.sub('', d.get('_speed_str', '').strip())
                        eta = ansi_escape.sub('', d.get('_eta_str', '').strip())

                        messages.put(f"data: Downloading: {percent} at {speed}, ETA {eta} - {name} [{current_index}/{total}]\n\n")
                    elif d['status'] == 'finished':
                        messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                    elif d['status'] == 'error':
                        messages.put("data: ❌ Download failed.\n\n")
                    else:
                        print(d["status"])

                with YoutubeDL({'quiet': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    description = info.get('description', '').replace('\n', ' ').replace('"', "'")
                    uploader = info.get('uploader', '')
                    webpage_url_domain = info.get('webpage_url_domain', '')

                if HIERARCHY_DIR:
                    download_to = os.path.normpath(
                        os.path.join(download_to, webpage_url_domain, uploader)
                    ) + os.path.sep

                    os.makedirs(download_to, exist_ok=True)
                yield f"data: Download_dir ^{download_to}\n\n"

                ydl_opts = {
                    'format': 'best',
                    'outtmpl': f'{download_to}%(title)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegMetadata'}],
                    'addmetadata': True,
                    'progress_hooks': [progress_hook],  # ✅ This is critical!
                    'postprocessor_args': [
                        '-metadata', f'comment={description}',
                        '-metadata', f'artist={uploader}',
                        '-metadata', f'album={webpage_url_domain}'
                    ]
                }


                try:
                    def download_and_drain():
                        messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                        try:
                            with YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                            # Signal end
                            messages.put("done")
                        except Exception as e:
                            print(e)
                            messages.put(f"data: ❌ Download failed.\n\n")
                            messages.put(f"data: {str(e).splitlines()[0]}\n\n")
                            messages.put("error")

                    # Start download in a thread to allow streaming progress
                    thread = threading.Thread(target=download_and_drain)
                    thread.start()


                    # Stream messages from queue in real-time
                    STATUS = None
                    while True:
                        try:
                            msg = messages.get(timeout=1)
                        except queue.Empty:
                            # yield f"data: waiting...\n\n"
                            continue
                        if msg == "done":
                            download_json.pop(0)
                            STATUS = "Downloaded"
                            break
                        if msg == "error":
                            retry.append({
                                'url': url,
                                'file': name
                            })
                            yield f"data: Error: {msg}\n\n"
                            download_json.pop(0)
                            STATUS = "Error"
                            break
                        yield msg

                    with open(PROCESS_FILE, 'a', encoding='utf-8') as out:
                        time = datetime.datetime.now()
                        time = time.strftime('%Y-%m-%d %H:%M')
                        out.write(f"{time} {name} {url} {STATUS}\n")

                    # Remove the finished URL from the list
                    with open(download_file, 'w', encoding='utf-8') as f:
                        json.dump(download_json, f, indent=4)

                except Exception as ve:
                    yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"
                    logging.error(f"data: Error processing {name},{url}: {str(ve).splitlines()[0]}")

        except Exception as ve:
            yield f"data: 🚫 Fatal error: {str(ve)}\n\n"
            logging.error(f"data: Fatal error: {str(ve)}")

        retries = 0
        while retries < 3:
            retries += 1
            yield f"Retrying {retries}/3 retries...\n"
            if len(retry) > 0:
                download_json = retry
                retry = []
                total = len(download_json)
                current_index = 0

                # Step 2: Process each line one by one
                download_files = download_json.copy()

                for file in download_files:
                    download_json.pop(0)
                    current_index += 1
                    url = file["url"]  # filename URL
                    name = file["file"] if file["file"] else "unnamed"

                    # Progress hook to receive download updates
                    def progress_hook(d):
                        if d['status'] == 'downloading':
                            percent = ansi_escape.sub('', d.get('_percent_str', '').strip())
                            speed = ansi_escape.sub('', d.get('_speed_str', '').strip())
                            eta = ansi_escape.sub('', d.get('_eta_str', '').strip())

                            messages.put(
                                f"data: Downloading: {percent} at {speed}, ETA {eta} - {name} [{current_index}/{total}]\n\n")

                        elif d['status'] == 'finished':
                            messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                        elif d['status'] == 'error':
                            messages.put("data: ❌ Download failed.\n\n")
                        else:
                            print("STATUS:", d['status'])

                    if HIERARCHY_DIR:
                        download_to = os.path.normpath(
                            os.path.join(download_to, webpage_url_domain, uploader)
                        ) + os.path.sep

                        os.makedirs(download_to, exist_ok=True)

                    yield f"data: Download_dir ^{download_to}\n\n"

                    ydl_opts = {
                        'format': 'best',
                        'outtmpl': f'{download_to}%(title)s.%(ext)s',
                        'postprocessors': [{'key': 'FFmpegMetadata'}],
                        'addmetadata': True,
                        'progress_hooks': [progress_hook],  # ✅ This is critical!
                    }

                    try:
                        def download_and_drain():
                            messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                            try:
                                with YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([url])
                                # Signal end
                                messages.put("done")
                            except Exception as e:
                                print(e)
                                messages.put(f"data: ❌ Download failed.\n\n")
                                messages.put(f"data: {str(e).splitlines()[0]}\n\n")
                                messages.put("error")

                        # Start download in a thread to allow streaming progress
                        thread = threading.Thread(target=download_and_drain)
                        thread.start()

                        # Stream messages from queue in real-time
                        while True:
                            try:
                                msg = messages.get(timeout=1)
                            except queue.Empty:
                                # yield f"data: waiting...\n\n"
                                continue
                            if msg == "done":
                                download_json.pop(0)
                                break
                            if msg == "error":
                                retry.append({
                                    'url': url,
                                    'file': name
                                })
                                yield f"data: Error: {msg}\n\n"
                                download_json.pop(0)
                                break
                            yield msg

                        with open(PROCESS_FILE, 'a', encoding='utf-8') as out:
                            time = datetime.datetime.now()
                            time = time.strftime('%Y-%m-%d %H:%M')
                            out.write(f"{time} {name} {url} {STATUS}\n")

                        # Remove the finished URL from the list
                        with open(download_file, 'w', encoding='utf-8') as f:
                            json.dump(retry, f, indent=4)

                    except Exception as ve:
                        yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"
                        logging.error(f"data: Error processing {name},{url}: {str(ve).splitlines()[0]}")

        yield "data: ✅ Done.\n\n"
        logging.info("data: Done.")

    return Response(stream_with_context(generate(file, download_to)), content_type='text/event-stream')

@app.route('/config')
def config():
    entries = []
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    for key, value in config.items():
        print(key, value)
        entries.append({'filename': key, 'website': value})
    return render_template('config.html', entries=entries, where='config')

@app.route('/setConfigSettings')
def setConfigSettings():
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE,HIERARCHY_DIR
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    if str(config['hierarchy']).lower().strip() == 'true':
        HIERARCHY_DIR = True
    else:
        HIERARCHY_DIR = False

    logging.info(f"web setConfigSettings: running")
    try:
        DOWNLOAD_DIR = os.path.normpath(config['Download To'])
        DOWNLOAD_DIR = DOWNLOAD_DIR + os.path.sep
        logging.info(f"web setConfigSettings: Download Dir {DOWNLOAD_DIR}")
    except Exception as e:
        logging.error(f"web setConfigSettings: could not open Download Dir: {str(e)}")
    try:
        DOWNLOAD_FILE = os.path.normpath(config['Download File'])
        logging.info(f"web setConfigSettings: Download File {DOWNLOAD_FILE}")
    except Exception as e:
        logging.error(f"web setConfigSettings: could not open Download File: {str(e)}")
    try:
        PLAYLIST_FILE = os.path.normpath(config['Playlist File'])
        logging.info(f"web setConfigSettings: Playlist File {PLAYLIST_FILE}")
    except Exception as e:
        logging.error(f"web setConfigSettings: could not open Playlist File: {str(e)}")
    try:
        PROCESS_FILE = os.path.normpath(config['Process'])
        logging.info(f"web setConfigSettings: Process File {PROCESS_FILE}")
    except Exception as e:
        logging.error(f"web setConfigSettings: could not open Process File: {str(e)}")
    try:
        PLAYLIST_PROCESS_FILE = os.path.normpath(config['Playlist Processed'])
        logging.info(f"web setConfigSettings: Playlist Processed File {PLAYLIST_PROCESS_FILE}")
    except Exception as e:
        logging.error(f"web setConfigSettings: could not open Playlist Processed File: {str(e)}")
    return redirect(url_for('config'))

def configBackground():
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE,HIERARCHY_DIR
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    if str(config['hierarchy']).lower().strip() == 'true':
        HIERARCHY_DIR = True
    else:
        HIERARCHY_DIR = False

    logging.info(f"configBackground: running")
    try:
        DOWNLOAD_DIR = os.path.normpath(config['Download To'])
        DOWNLOAD_DIR = DOWNLOAD_DIR + os.path.sep
        logging.info(f"configBackground: Download Dir {DOWNLOAD_DIR}")
    except Exception as e:
        logging.error(f"configBackground: could not open Download Dir: {str(e)}")
    try:
        DOWNLOAD_FILE = os.path.normpath(config['Download File'])
        logging.info(f"configBackground: Download File {DOWNLOAD_FILE}")
    except Exception as e:
        logging.error(f"configBackground: could not open Download File: {str(e)}")
    try:
        PLAYLIST_FILE = os.path.normpath(config['Playlist File'])
        logging.info(f"configBackground: Playlist File {PLAYLIST_FILE}")
    except Exception as e:
        logging.error(f"configBackground: could not open Playlist File: {str(e)}")
    try:
        PROCESS_FILE = os.path.normpath(config['Process'])
        logging.info(f"configBackground: Process File {PROCESS_FILE}")
    except Exception as e:
        logging.error(f"configBackground: could not open Process File: {str(e)}")
    try:
        PLAYLIST_PROCESS_FILE = os.path.normpath(config['Playlist Processed'])
        logging.info(f"configBackground: Playlist Processed File {PLAYLIST_PROCESS_FILE}")
    except Exception as e:
        logging.error(f"configBackground: could not open Playlist Processed File: {str(e)}")


def legacy_read():
    def config_file():
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(config)
        config["hierarchy"] = "false"
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    def file_config():
        updated_configs = []
        read = []
        with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
            configs = json.load(f)
        for config in configs:
            if config['file'] not in read:
                playlist = None
                download = None
                if config['type'] == 'playlist':
                    playlist = config['install']
                    for f in configs:
                        if f['file'] == config['file'] and f['type'] == 'download':
                            download = f['install']
                elif config['type'] == 'download':
                    download = config['install']
                    for f in configs:
                        if f['file'] == config['file'] and f['type'] == 'playlist':
                            playlist = f['install']
                read.append(config['file'])
                updated_configs.append(
                    {
                        'file': config['file'],
                        'install-playlist': playlist if playlist is not None else config['file']+'-playlist.json',
                        'install-directory': download if download is not None else DOWNLOAD_DIR,
                    }
                )
                for file_name in [config['file']+'-playlist.json', config['file']+'-download.json']:
                    try:
                        with open(file_name, 'x', encoding='utf-8') as f:
                            data = []
                            f.write(json.dumps(data))
                    except FileExistsError:
                        pass
        with open(FILE_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(updated_configs, f, indent=4)

    with open(SYSTEM_CONFIG, 'r', encoding='utf-8') as f:
        SYSTEM_SET = json.load(f)
    for upgrade_needed in SYSTEM_SET[1]['legacy-read']:
        if upgrade_needed == 'config_file':
            try:
                config_file()
                SYSTEM_SET[1]['config_file'].remove(upgrade_needed)
            except Exception as e:
                logging.error(f"UPGRADING: ERROR COULD NOT UPGRADE: {str(e)}")
        if upgrade_needed == 'file_config':
            try:
                file_config()
                SYSTEM_SET[1]['legacy-read'].remove(upgrade_needed)
            except Exception as e:
                logging.error(f"UPGRADING: ERROR COULD NOT UPGRADE: {str(e)}")
    filtered_data = []
    updated_to = SYSTEM_SET[1]["UPDATE"]
    for entry in SYSTEM_SET:
        if 'UPDATE' in entry and entry.get('legacy-read') == []:
            continue  # Skip this entry
        filtered_data.append(entry)
    filtered_data[0]['Version'] = updated_to
    with open(SYSTEM_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, indent=4)





if __name__ == '__main__':
    with open(SYSTEM_CONFIG, 'r', encoding='utf-8') as f:
        SYSTEM_SET = json.load(f)
    try:
        if len(SYSTEM_SET[1]['legacy-read']) > 0:
            legacy_read()
    except Exception as e:
        pass

    logging.basicConfig(level=logging.INFO)
    try:
        with open('config.json', 'x', encoding='utf-8') as f:
            f.write('''"web-dlp-down-z Log file": "logs",
            "Download To": "~/Downloads",
            "Download File": "default-default-download.json",
            "Playlist File": "default-default-playlist.json",
            "Download full log": "log_download.txt",
            "Playlist full log": "log_download.txt",
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
