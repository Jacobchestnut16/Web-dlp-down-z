import os
import time
import queue
import threading
import re
import logging
import json
import datetime
from urllib.parse import urlparse
from flask import render_template, Response, stream_with_context, Blueprint
from yt_dlp import YoutubeDL
from app.config_loader import (FILE_CONFIG, DOWNLOAD_DIR, PLAYLIST_PROCESS_FILE, DOWNLOAD_FILE, HIERARCHY_DIR,
                               CONFIG_FILE, PROCESS_FILE, SYSTEM_FILE, STYLE_DIR, DATA_DIR, LOG_DIR)
active_downloads = {}  # {file_name: threading.Thread}
stop_flags = {}        # {file_name: threading.Event}
from ..config_loader import config_background


bp = Blueprint('execute', __name__)

@bp.route('/run/thumbnail-generator/<file>')
def run_thumbnail_generator(file):
    return render_template('thumb.html', file=file, system_theme=config_background())

@bp.route('/execute')
def execute_index():
    funfiles = []
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            funfiles.append({'name': item['file'].split('-')[0]})
    return render_template('execute.html', download_dir=DOWNLOAD_DIR, funfiles=funfiles, system_theme=config_background())

@bp.route('/execute/install/<file>')
def execute_installation(file):
    type=(file.split('-')[1]).split('.')[0]
    print('downloading',type,file)
    return render_template('install.html', file=file, type=type , download_dir=DOWNLOAD_DIR, system_theme=config_background())

@bp.route('/execute/thumbnail/<file>')
def execute_thumbnail(file):
    print('downloading',file)
    logging.basicConfig(level=logging.DEBUG)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    def generate(master_file):
        messages = queue.Queue()

        yield "data: Scraping metadata...\n\n"
        try:
            with open(os.path.join(DATA_DIR, master_file), 'r', encoding='utf-8') as f:
                download_json = json.load(f)

            total = len(download_json)
            current_index = 0

            download_files = download_json.copy()

            # Step 2: Process each line one by one
            for file in download_files:
                current_index += 1
                url = file["url"]  # filename URL
                name = file["file"] if file["file"] else "unnamed"

                if file.get("duration") in [None, ""] or file.get("description") in [None, ""] or file.get("thumbnail") in [None, ""]:
                    yield (f"data:Item ({current_index}/{total}), Updating metadata for {name}: {('Duration.' if not file.get('duration') else '')}"
                           f" {('Description.' if not file.get('duration') else '')} {('thumbnail.' if not file.get('thumbnail') else '')}\n\n")
                    ydl_opts = {
                        'skip_download': True,
                        'quiet': True
                    }
                    with YoutubeDL(ydl_opts) as ydl:
                        try:
                            info = ydl.extract_info(url, download=False)
                            try:
                                thumbnail = info.get('thumbnail')
                            except Exception:
                                thumbnail = ''
                            try:
                                duration = info.get('duration')
                            except Exception as e:
                                if "private" in str(e).lower():
                                    duration = 'PRIVATE VIDEO'
                                else:
                                    duration = 'None'
                            try:
                                description = info.get('description')
                            except Exception:
                                description = ''
                        except Exception as e:
                            if "private" in str(e).lower():
                                duration = 'PRIVATE VIDEO'
                            else:
                                duration = 'None'
                            description = ''
                            thumbnail = ''

                    with open(os.path.join(DATA_DIR, master_file), 'r', encoding='utf-8') as f:
                        json_data = json.load(f)

                    updated = False
                    for entry in json_data:
                        if entry.get("file") == name and entry.get("url") == url:
                            entry["duration"] = duration
                            entry["description"] = description
                            entry["thumbnail"] = thumbnail
                            updated = True

                    if updated:
                        with open(os.path.join(DATA_DIR, master_file), 'w', encoding='utf-8') as f:
                            json.dump(json_data, f, indent=4)
                    else:
                        yield f"data: Error: File {name} Failed to update metadata.\n\n"
                else:
                    yield (f"data:Item ({current_index}/{total}), metadata for {name} already exists skipping\n\n")
        except Exception as e:
            yield f"data: Error: File {name} Failed to update metadata.\n\n"

        yield f"data: REDIRECT /edit/{master_file}\n\n"

    return Response(stream_with_context(generate(file)), content_type='text/event-stream')

@bp.route('/execute/playlist/<file>')
def execute_playlist_file(file):
    logging.basicConfig(level=logging.DEBUG)

    file_name = (file.split('-')[0])
    file_type = ((file.split('-')[1]).split('.'))[0]
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
    if file_type != 'default':
        for filef in files:
            if filef['file'] == file_name:
                download_to = os.path.join(DATA_DIR, filef['install-playlist'])
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
            with open(os.path.join(DATA_DIR,file), 'r', encoding='utf-8') as f:
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

                                    # Step 2: append new entry
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

                with open(os.path.join(LOG_DIR, PLAYLIST_PROCESS_FILE), 'a', encoding='utf-8') as out:
                    time = datetime.datetime.now()
                    time = time.strftime('%Y-%m-%d %H:%M')
                    out.write(f'{time} {name} {url}\n')

                # Remove the finished URL from the list
                with open(os.path.join(DATA_DIR, file), 'w', encoding='utf-8') as f:
                    json.dump(playlist_json, f, indent=4)


        except Exception as e:
            yield f"data: 🚫 Fatal error: {str(e)}\n\n"
            logging.error(f'Error: {e}')

        yield "data: ✅ Done.\n\n"
        yield f"data: REDIRECT /run/thumbnail-generator/{download_to}\n\n"

    return Response(stream_with_context(generate(file)), content_type='text/event-stream')

AUDIO_FORMATS = ['mp3', 'm4a', 'aac', 'opus', 'vorbis', 'wav', 'flac', 'alac']
VIDEO_FORMATS = ['mp4', 'webm', 'flv', '3gp']


@bp.route('/execute/download/<file>')
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
        print("data: Downloading started")
        try:
            with open(os.path.join(DATA_DIR, download_file), 'r', encoding='utf-8') as f:
                download_json = json.load(f)

            total = len(download_json)
            current_index = 0

            download_files = download_json.copy()

            yield "data: grabbing cookies\n\n"
            print("data: grabbing cookies")

            def json_cookies_to_netscape_string(cookies_json):
                """
                Convert JSON cookies (list of dicts) to Netscape cookie format string.
                """
                lines = []
                lines.append("# Netscape HTTP Cookie File")
                lines.append("# This file is generated from JSON cookies\n")

                for c in cookies_json:
                    print(c)
                    domain = c.get('domain', '')
                    flag = "TRUE" if domain.startswith('.') else "FALSE"
                    path = c.get('path', '/')
                    secure = "TRUE" if c.get('secure', False) else "FALSE"
                    expiry = str(int(c.get('expirationDate', c.get('expires', 0))))
                    name = c.get('name', '')
                    value = c.get('value', '')
                    lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

                with open(os.path.join(DATA_DIR, 'cookies.txt'), 'w', encoding='utf-8') as out:
                    out.write("\n".join(lines))

                return "\n".join(lines)

            try:
                with open(os.path.join(DATA_DIR, 'cookies.json'), 'r', encoding='utf-8') as f:
                    cookies_json = json.load(f)
                cookies = json_cookies_to_netscape_string(cookies_json)
                yield f'data: cookies: {cookies}\n\n'
            except FileNotFoundError:
                try:
                    with open(os.path.join(DATA_DIR, 'cookies.txt'), 'r', encoding='utf-8') as f:
                        cookies = f.read().strip().replace('\n', '')
                    yield f'data: cookies: {cookies}\n\n'
                except Exception as e:
                    yield f"data: cookies file not found, skipping: {e}\n\n"

            # Step 2: Process each line one by one
            for file in download_files:
                print(f"file: {file['file']}")
                current_index += 1
                url = file["url"]  # filename URL
                name = file["file"] if file["file"] else "unnamed"
                ds = filef.get('downloadAs') or ""
                downloadAs = ds if ds else downloadAs


                # Progress hook to receive download updates
                if HIERARCHY_DIR:
                    download_to = os.path.normpath(
                        os.path.join(download_to, webpage_url_domain, uploader)
                    ) + os.path.sep

                    os.makedirs(download_to, exist_ok=True)
                yield f"data: Download_dir ^{download_to}\n\n"
                print(f"data: download_dir: {download_to}")


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


                ydl_opts = {
                    'format': 'bestaudio/best' if downloadAs in AUDIO_FORMATS else ('bestvideo+bestaudio/best' if downloadAs in VIDEO_FORMATS else 'best'),
                    'outtmpl': f'{download_to}%(title)s.%(ext)s',
                    'addmetadata': True,
                    'verbose': True,
                    'progress_hooks': [progress_hook],  # ✅ This is critical!
                    'postprocessor_args': [
                        '-metadata', f'comment={description}',
                        '-metadata', f'artist={uploader}',
                        '-metadata', f'album={webpage_url_domain}'
                    ]
                }
                if cookies:
                    ydl_opts['cookiefile'] = os.path.join(DATA_DIR, 'cookies.txt')

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

                    with open(os.path.join(LOG_DIR, PROCESS_FILE), 'a', encoding='utf-8') as out:
                        time = datetime.datetime.now()
                        time = time.strftime('%Y-%m-%d %H:%M')
                        out.write(f"{time} {name} {url} {STATUS}\n")

                    # Remove the finished URL from the list
                    with open(os.path.join(DATA_DIR, download_file), 'w', encoding='utf-8') as f:
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

                        with open(os.path.join(LOG_DIR, PROCESS_FILE), 'a', encoding='utf-8') as out:
                            time = datetime.datetime.now()
                            time = time.strftime('%Y-%m-%d %H:%M')
                            out.write(f"{time} {name} {url} {STATUS}\n")

                        # Remove the finished URL from the list
                        with open(os.path.join(DATA_DIR, download_file), 'w', encoding='utf-8') as f:
                            json.dump(download_json, f, indent=4)

                    except Exception as ve:
                        yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"
                        logging.error(f"data: Error processing {name},{url}: {str(ve).splitlines()[0]}")

        yield "data: ✅ Done.\n\n"
        logging.info("data: Done.")
        stop_flags.pop(file_name, None)
        active_downloads.pop(file_name, None)
    return Response(stream_with_context(generate(file, download_to, downloadAs)), content_type='text/event-stream')


@bp.route('/execute/stop/<file>', methods=['POST'])
def stop_download(file):
    if file in stop_flags:
        stop_flags[file].set()  # Signal the thread to stop
        return "Stopping download...", 200
    return "No download in progress for this file.", 404

@bp.route('/config')
def config():
    entries = []
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    for key, value in config.items():
        print(key, value)
        entries.append({'filename': key, 'website': value})
    with open(SYSTEM_FILE, 'r') as f:
        system = json.load(f)
    try:
        system_theme = system['theme']
    except Exception as e:
        system_theme = 'default'
        system['theme'] = 'default'
        with open(SYSTEM_FILE, 'w', encoding='utf-8') as f:
            json.dump(system, f, ensure_ascii=False, indent=4)
    styles = os.listdir(STYLE_DIR)
    styles.remove('style.css')

    return render_template('config.html', entries=entries, where='config', system_theme=system_theme, styles=styles)