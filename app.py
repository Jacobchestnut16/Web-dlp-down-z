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

PLAYLIST_FILE = 'default-playlist.json'
PLAYLIST_PROCESS_FILE = 'playlist_processed.txt'
DOWNLOAD_FILE = 'default-download.json'
PROCESS_FILE = 'process.txt'
CONFIG_FILE = 'config.json'
DOWNLOAD_DIR = '~/Downloads'
FILE_CONFIG = 'file_config.json'
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

@app.route('/view')
def view_index():
    return render_template('view.html')
@app.route('/view/<file>')
def view(file):
    with open(file, 'r', encoding='utf-8') as f:
        contents = [line.strip() for line in f if line.strip()]
    return render_template('view.html', file_contents=contents, where=file[:-4], system_theme=SYSTEM_THEME)


@app.route('/edit')
def edit_index():
    funfiles = []

    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            funfiles.append({'file': item['file'], 'install-playlist': item['install-playlist'], 'install-directory': item['install-directory']})

    print("FILES LOADED:", funfiles)
    return render_template('file.html', funfiles=funfiles, system_theme=SYSTEM_THEME)
@app.route('/edit/<file>', methods=['GET', 'POST'])
def edit(file):

    entries = []
    funfiles = []
    downloadAs = 'default'

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
        with open('default-config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        downloadAs = data['downloadAs']

    return render_template('file.html', entries=entries, where=file, funfiles=funfiles, type=type,
                           install=install, installOpts=installOpts, name=named, files=cnt,
                           downloadAs=(downloadAs if downloadAs else 'web_default'), system_theme=SYSTEM_THEME)

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

@app.route('/run/thumbnail-generator/<file>')
def run_thumbnail_generator(file):
    return render_template('thumb.html', file=file, system_theme=SYSTEM_THEME)

@app.route('/execute')
def execute_index():
    funfiles = []
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            funfiles.append({'name': item['file'].split('-')[0]})
    return render_template('execute.html', download_dir=DOWNLOAD_DIR, funfiles=funfiles, system_theme=SYSTEM_THEME)

@app.route('/execute/install/<file>')
def execute_installation(file):
    type=(file.split('-')[1]).split('.')[0]
    print('downloading',type,file)
    return render_template('install.html', file=file, type=type , download_dir=DOWNLOAD_DIR, system_theme=SYSTEM_THEME)

@app.route('/execute/thumbnail/<file>')
def execute_thumbnail(file):
    logging.basicConfig(level=logging.DEBUG)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    def generate(master_file):
        messages = queue.Queue()

        yield "data: Scraping metadata...\n\n"
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

                if file.get("duration") in [None, "", "None"] or file.get("description") in [None, ""]:
                    yield (f"data:Item ({current_index}/{total}), Updating metadata for {name}: {('Duration.' if not file.get('duration') else '')}"
                           f" {('Description.' if not file.get('duration') else '')} {('thumbnail.' if not file.get('thumbnail') else '')}\n\n")
                    ydl_opts = {
                        'skip_download': True,
                        'quiet': True
                    }
                    with YoutubeDL(ydl_opts) as ydl:
                        try:
                            info = ydl.extract_info(url, download=False)
                            thumbnail = info.get('thumbnail')
                            duration = info.get('duration')
                            description = info.get('description')
                        except Exception as e:
                            if "private" in str(e).lower():
                                duration = 'PRIVATE VIDEO'
                            else:
                                duration = 'None'
                            description = ''
                            thumbnail = ''

                    with open(master_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)

                    updated = False
                    for entry in json_data:
                        if entry.get("file") == name and entry.get("url") == url:
                            entry["duration"] = duration
                            entry["description"] = description
                            entry["thumbnail"] = thumbnail
                            updated = True

                    if updated:
                        with open(master_file, 'w', encoding='utf-8') as f:
                            json.dump(json_data, f, indent=4)
                    else:
                        yield f"data: Error: File {name} Failed to update metadata.\n\n"
        except Exception as e:
            yield f"data: Error: File {name} Failed to update metadata.\n\n"

        yield f"data: REDIRECT /edit/{master_file}\n\n"

    return Response(stream_with_context(generate(file)), content_type='text/event-stream')

@app.route('/execute/playlist/<file>')
def execute_playlist_file(file):
    logging.basicConfig(level=logging.DEBUG)

    file_name = (file.split('-')[0])
    file_type = ((file.split('-')[1]).split('.'))[0]
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
    if file_type != 'default':
        for filef in files:
            if filef['file'] == file_name:
                download_to = filef['install-playlist']
    else:
        download_to = DOWNLOAD_FILE


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

AUDIO_FORMATS = ['mp3', 'm4a', 'aac', 'opus', 'vorbis', 'wav', 'flac', 'alac']
VIDEO_FORMATS = ['mp4', 'webm', 'flv', '3gp']


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
            downloadAs = filef.get('downloadAs') or ""
    if file_name == "default":
        download_to = DOWNLOAD_DIR
        with open('default-config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        download_to = config.get('downloadAs') or ""
        download_to = os.path.normpath(download_to)

    if not download_to.endswith(os.path.sep):
        download_to += os.path.sep
    try:
        os.makedirs(os.path.dirname(download_to), exist_ok=True)
    except OSError as err:
        print(f"data: Error: {str(err)}\n\n")


    def generate(download_file, download_to, downloadAs):
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
                ds = filef.get('downloadAs') or ""
                downloadAs = ds if ds else downloadAs


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

                try:
                    with YoutubeDL({'quiet': True}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        description = info.get('description', '').replace('\n', ' ').replace('"', "'")
                        uploader = info.get('uploader', '')
                        webpage_url_domain = info.get('webpage_url_domain', '')
                except Exception as e:
                    yield f"data: ❌ Download failed.\n\n"
                    yield f"data: {str(e).splitlines()[0]}\n\n"
                    continue

                if HIERARCHY_DIR:
                    download_to = os.path.normpath(
                        os.path.join(download_to, webpage_url_domain, uploader)
                    ) + os.path.sep

                    os.makedirs(download_to, exist_ok=True)
                yield f"data: Download_dir ^{download_to}\n\n"

                ydl_opts = {
                    'format': 'bestaudio/best' if downloadAs in AUDIO_FORMATS else ('bestvideo+bestaudio/best' if downloadAs in VIDEO_FORMATS else 'best'),
                    'outtmpl': f'{download_to}%(title)s.%(ext)s',
                    'addmetadata': True,
                    'progress_hooks': [progress_hook],  # ✅ This is critical!
                    'postprocessor_args': [
                        '-metadata', f'comment={description}',
                        '-metadata', f'artist={uploader}',
                        '-metadata', f'album={webpage_url_domain}'
                    ]
                }

                if downloadAs in AUDIO_FORMATS:
                    ydl_opts.update({
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': downloadAs,
                        }, {
                            'key': 'FFmpegMetadata'
                        }]
                    })
                elif downloadAs in VIDEO_FORMATS:
                    ydl_opts.update({
                        'merge_output_format': downloadAs,  # Needed for combining video+audio
                        'postprocessors': [{
                            'key': 'FFmpegMetadata'
                        }]
                    })
                else:
                    ydl_opts.update({
                        'postprocessors': [{
                            'key': 'FFmpegMetadata'
                        }]
                    })

                try:
                    def download_and_drain():
                        messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                        try:

                            if stop_flags.get(file_name, threading.Event()).is_set():
                                messages.put("data: ❌ Download stopped by user.\n\n")
                                messages.put("stop")
                                return

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
                    stop_flags[file_name] = threading.Event()
                    thread = threading.Thread(target=download_and_drain)
                    thread.start()
                    active_downloads[file_name] = thread


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
                        if msg == "stop":
                            yield "data: ⛔ Download stopped by user.\n\n"
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
                        'outtmpl': f'{download_to}%(title)s.{downloadAs}',
                        'postprocessors': [{'key': 'FFmpegMetadata'}],
                        'addmetadata': True,
                        'progress_hooks': [progress_hook],  # ✅ This is critical!
                    }

                    try:
                        def download_and_drain():
                            messages.put(f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n")
                            try:

                                if stop_flags.get(file_name, threading.Event()).is_set():
                                    messages.put("data: ❌ Download stopped by user.\n\n")
                                    messages.put("stop")
                                    return

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
                        stop_flags[file_name] = threading.Event()
                        thread = threading.Thread(target=download_and_drain)
                        thread.start()
                        active_downloads[file_name] = thread

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
                            if msg == "stop":
                                yield "data: ⛔ Download stopped by user.\n\n"
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
        stop_flags.pop(file_name, None)
        active_downloads.pop(file_name, None)
    return Response(stream_with_context(generate(file, download_to, downloadAs)), content_type='text/event-stream')


@app.route('/execute/stop/<file>', methods=['POST'])
def stop_download(file):
    if file in stop_flags:
        stop_flags[file].set()  # Signal the thread to stop
        return "Stopping download...", 200
    return "No download in progress for this file.", 404
@app.route('/config')
def config():
    entries = []
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    for key, value in config.items():
        print(key, value)
        entries.append({'filename': key, 'website': value})
    with open('system.json', 'r') as f:
        system = json.load(f)
    try:
        system_theme = system['theme']
    except Exception as e:
        system_theme = 'default'
        system['theme'] = 'default'
        with open('system.json', 'w', encoding='utf-8') as f:
            json.dump(system, f, ensure_ascii=False, indent=4)

    return render_template('config.html', entries=entries, where='config', system_theme=system_theme)

@app.route('/setConfigSettings')
def setConfigSettings():
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE,HIERARCHY_DIR,SYSTEM_THEME
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    with open('system.json', 'r', encoding='utf-8') as f:
        system = json.load(f)
    try:
        SYSTEM_THEME = system['theme']
    except Exception as e:
        system['theme'] = 'default'
        with open('system.json', 'w', encoding='utf-8') as f:
            json.dump(system, f, ensure_ascii=False, indent=4)
    logging.info(f"web setConfigSettings: SYSTEM theme: {SYSTEM_THEME}")

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
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE, HIERARCHY_DIR, SYSTEM_THEME
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    with open('system.json', 'r', encoding='utf-8') as f:
        system = json.load(f)
    try:
        SYSTEM_THEME = system['theme']
    except Exception as e:
        system['theme'] = 'default'
        with open('system.json', 'w', encoding='utf-8') as f:
            json.dump(system, f, ensure_ascii=False, indent=4)
    logging.info(f"web setConfigSettings: SYSTEM theme: {SYSTEM_THEME}")

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

@app.route('/set/theme', methods=['GET', 'POST'])
def set_theme():
    if request.method == 'POST':
        theme = request.form['theme']
        global SYSTEM_THEME
        SYSTEM_THEME = theme
        with open('system.json', 'r', encoding='utf-8') as f:
            system = json.load(f)
        system['theme'] = theme
        with open('system.json', 'w', encoding='utf-8') as f:
            json.dump(system, f, indent=4)
    return redirect(url_for('config'))



def fetch_remote_json(url):
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def fetch_remote_file(url):
    res = requests.get(url, timeout=5)
    res.raise_for_status()
    return res.text

BASE_URL = 'https://raw.githubusercontent.com/Jacobchestnut16/Web-dlp-down-z/refs/heads/update/'
def check_for_updates():
    global BASE_URL
    try:
        pre_release_auth = fetch_remote_file('https://raw.githubusercontent.com/Jacobchestnut16/Web-dlp-down-z/refs/heads/pre-release/beta_key').strip()
        with open('beta_key', 'r', encoding='utf-8') as f:
            beta_key = f.read().strip()
            print(f'beta_key: {beta_key}')
        print(f'match: {beta_key == pre_release_auth}')
        if beta_key == pre_release_auth:
            BASE_URL = "https://raw.githubusercontent.com/Jacobchestnut16/Web-dlp-down-z/refs/heads/pre-release/"
    except Exception as e:
        print(e)
    try:
        system_json = 'system.json'
        with open(system_json, 'r', encoding='utf-8') as f:
            version = json.load(f)['version']
    except Exception as e:
        system_json = 'app/instance/system.json'
        with open(system_json, 'r', encoding='utf-8') as f:
            version = json.load(f)['version']
    ulr = BASE_URL+'system.json'
    remote_version = fetch_remote_json(ulr)["version"]
    if version != remote_version:
        return ("Update required", remote_version)
    else:
        return ("Up to date", version)


@app.route('/update/start')
def update_now():
    print("update now")
    def generate():
        print("staring update")
        def merge_json_files(existing_path, patch_data):
            if not os.path.exists(existing_path):
                user_config = {}
            else:
                with open(existing_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)

            # Merge new keys that don't exist
            for key, value in patch_data.items():
                if key not in user_config:
                    user_config[key] = value

            # Save updated config
            with open(existing_path, 'w', encoding='utf-8') as f:
                json.dump(user_config, f, indent=4)

        def version_tuple(v):
            return tuple(map(int, v.split('.')))

        try:
            system_json = 'system.json'
            with open(system_json, 'r', encoding='utf-8') as f:
                version = json.load(f)['version']
        except Exception as e:
            system_json = 'app/instance/system.json'
            with open(system_json, 'r', encoding='utf-8') as f:
                version = json.load(f)['version']
        version_split = version_tuple(version)
        remote_json = fetch_remote_json(BASE_URL + 'system.json')
        add_files = []
        update_files = []
        clean_files = []
        for version_entry in remote_json["versions"]:
            for key, value in version_entry.items():
                if version_split < version_tuple(key):
                    for f in value.get('add', []):
                        if f not in add_files:
                            add_files.append(f)
                    for f in value.get('merge', []):
                        if f not in update_files:
                            update_files.append(f)
                    for f in value.get('remove', []):
                        if f not in clean_files:
                            clean_files.append(f)
        if "app.py" in add_files:
            app_need_update = True
            while "app.py" in add_files:
                add_files.remove("app.py")
        else:
            app_need_update = False

        for file_needs_removed in clean_files:
            while file_needs_removed in add_files:
                add_files.remove(file_needs_removed)
            while file_needs_removed in update_files:
                update_files.remove(file_needs_removed)

        needs_updating = {'add': add_files, 'merge': update_files, 'remove': clean_files,
                          'app_need_update': app_need_update}
        if os.path.exists('system_update.json'):
            with open('system_update.json', 'r', encoding='utf-8') as f:
                updated = json.load(f).get("updated", {})
            with open('system_update.json', 'w', encoding='utf-8') as f:
                f.write('')
        else:
            updated = {"add": [], "merge": [], "remove": [], "app_need_update": app_need_update}
        with open('system_update.json', 'w', encoding='utf-8') as f:
            json.dump({"needs_updating": needs_updating, "updated": updated}, f, indent=4)
        print(updated)

        for f in add_files:
            if f not in updated['add']:
                time.sleep(1)
                try:
                    dir_path = os.path.dirname(f)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)

                    content = fetch_remote_file(BASE_URL + f)

                    try:
                        with open(f, 'x', encoding='utf-8') as file:
                            file.write(content)
                    except FileExistsError:
                        with open(f, 'w', encoding='utf-8') as file:
                            file.write(content)

                    updated['add'].append(f)
                    with open('system_update.json', 'w', encoding='utf-8') as state:
                        json.dump({"needs_updating": needs_updating, "updated": updated}, state, indent=4)

                    yield f"data: Added {f}\n\n"

                except Exception as e:
                    yield f"data: ❌ Error adding {f}: {str(e)}\n\n"
                    logging.exception(f"Error while adding file: {f}")
        for f in update_files:
            if f not in updated['merge']:
                yield f"data: Updating {f}\n\n"
                try:
                    try:
                        merge_json_files(f, fetch_remote_json(BASE_URL + f))
                    except Exception as e:
                        yield f"data: {e}\n\n"
                    updated['merge'].append(f)
                    with open('system_update.json', 'w', encoding='utf-8') as f:
                        json.dump({"needs_updating": needs_updating, "updated": updated}, f, indent=4)
                except Exception as e:
                    yield f"Error: updating {f}, {e}\n\n"
        for f in clean_files:
            if f not in updated['remove']:
                yield f"data: Removing {f}"
                try:
                    try:
                        os.remove(f)
                    except FileNotFoundError:
                        yield f"data: File {f} not found, skipping remove\n\n"
                    updated['remove'].append(f)
                    with open('system_update.json', 'w', encoding='utf-8') as f:
                        json.dump({"needs_updating": needs_updating, "updated": updated}, f, indent=4)
                except Exception as e:
                    yield f"Error: removing {f}, {e}\n\n"
        all_applied = (
                set(needs_updating['add']) == set(updated['add']) and
                set(needs_updating['merge']) == set(updated['merge']) and
                set(needs_updating['remove']) == set(updated['remove'])
        )
        if all_applied:
            system_json = 'system.json'
            try:
                with open(system_json, 'r', encoding='utf-8') as f:
                    system_features = json.load(f)
                system_features['version'] = remote_json['version']
                with open(system_json, 'w', encoding='utf-8') as f:
                    json.dump(system_features, f, indent=4)
            except Exception as e:
                system_json = 'app/instance/system.json'
                with open(system_json, 'r', encoding='utf-8') as f:
                    system_features = json.load(f)
                system_features['version'] = remote_json['version']
                with open(system_json, 'w', encoding='utf-8') as f:
                    json.dump(system_features, f, indent=4)
            if app_need_update:
                with open('app.py', 'w', encoding='utf-8') as f:
                    f.write(fetch_remote_file(BASE_URL + 'app.py'))
                yield f"data: Update complete, APP NEEDS RESTARTED.\n\n"
            else:
                yield f"data: Update complete.\n\n"
            os.remove('system_update.json')
        else:
            yield f"data: Update failed.\n\n"
            yield f"data: add, {set(needs_updating['add']) == set(updated['add'])}.\n\n"
            yield f"data: add, {needs_updating['add']} == {updated['add']}.\n\n"
            yield f"data: merge, {set(needs_updating['merge']) == set(updated['merge'])}.\n\n"
            yield f"data: merge, {needs_updating['merge']} == {updated['merge']}.\n\n"
            yield f"data: remove, {set(needs_updating['remove']) == set(updated['remove'])}.\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')



@app.route('/update')
def update():
    try:
        system_json = 'system.json'
        with open(system_json, 'r', encoding='utf-8') as f:
            current = json.load(f)['version']
    except Exception as e:
        system_json = 'app/instance/system.json'
        with open(system_json, 'r', encoding='utf-8') as f:
            current = json.load(f)['version']


    update = check_for_updates()
    if update[0] == "Update required":
        return render_template('update.html', updateTxt=update[0], updateVersion=update[1], current=current,
                               system_theme=SYSTEM_THEME)
    else:
        return render_template('update.html', updateTxt=update[0], current=current, system_theme=SYSTEM_THEME)



if __name__ == '__main__':

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
    app.run(debug=True, host='0.0.0.0', port=8080, use_reloader=False)
