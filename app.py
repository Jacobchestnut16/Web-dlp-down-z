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

PLAYLIST_FILE = 'playlist.json'
PLAYLIST_PROCESS_FILE = 'playlist_processed.txt'
DOWNLOAD_FILE = 'download.json'
PROCESS_FILE = 'process.txt'
CONFIG_FILE = 'config.json'
DOWNLOAD_DIR = '~/Downloads'


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
    return render_template('file.html')
@app.route('/edit/<file>', methods=['GET', 'POST'])
def edit(file):

    entries = []

    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print("DATA LOADED:", data)  # Debug print

            if isinstance(data, list):
                for item in data:
                    filename = item.get('file', '').strip()
                    website = item.get('url', '').strip()
                    if filename:  # Only add if filename exists
                        entries.append({
                            'filename': filename,
                            'website': website
                        })
    except FileNotFoundError:
        print("playlist.json not found.")
    except json.JSONDecodeError as e:
        print("JSON decode error:", e)

    print("ENTRIES PREPARING FOR TEMPLATE:", entries)  # Debug print

    return render_template('file.html', entries=entries, where=file)

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
            return redirect(url_for('run_thumbnail_generator'))
        return redirect(url_for('edit', file=file, mark="Saved"))  # or back to 'edit' if that’s the page

@app.route('/run/thumbnail-generator')
def run_thumbnail_generator():
    return render_template('thumb.html')

@app.route('/execute')
def execute_index():
    return render_template('execute.html', download_dir=DOWNLOAD_DIR)

@app.route('/execute/thumbnail')
def execute_thumbnail():
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    def generate():
        messages = queue.Queue()

        yield "data: Finding thumbnails...\n\n"

        try:
            with open(DOWNLOAD_FILE, 'r', encoding='utf-8') as f:
                download_json = json.load(f)

            total = len(download_json)
            current_index = 0

            # Step 2: Process each line one by one
            for file in download_json:
                download_json.pop(0)
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

                        messages.put(f"data: Downloading: {percent} at {speed}, ETA {eta} [{current_index}/{total}]\n\n")
                    elif d['status'] == 'finished':
                        messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                    elif d['status'] == 'error':
                        messages.put("data: ❌ Download failed.\n\n")

                tmp_dir = os.path.join(".", "static", "thumb")
                os.makedirs(tmp_dir, exist_ok=True)

                # Build the output template path safely
                out_path = os.path.join(tmp_dir, f"{name}.%(ext)s")
                ydl_opts = {
                    'skip_download': True,
                    'writethumbnail': True,
                    'convert_thumbnails': 'jpg',
                    'outtmpl': f'{out_path}',
                    'quiet': False,
                    'progress_hooks': [progress_hook]
                }

                yield f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n"

                try:
                    def download_and_drain():
                        with YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        # Signal end
                        messages.put("done")

                    # Start download in a thread to allow streaming progress
                    thread = threading.Thread(target=download_and_drain)
                    thread.start()

                    # Stream messages from queue in real-time
                    while True:
                        msg = messages.get()
                        if msg == "done":
                            break
                        yield msg

                except Exception as ve:
                    yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"

        except Exception as ve:
            yield f"data: 🚫 Fatal error: {str(ve)}\n\n"

        yield "data: ✅ Done.\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')


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
                            print(entries)
                            for entry in entries:
                                video_title = entry.get('title', 'Unknown title')
                                video_url = entry.get('url')

                                if not video_url:
                                    yield f"data: ⚠️ Skipped video (missing URL): {video_title}\n\n"
                                    continue

                                full_url = entry.get('url')

                                if video_title.lower() in ['unknown title', 'unknown']:
                                    parsed = urlparse(full_url)
                                    last_segment = parsed.path.rstrip('/').split('/')[-1] or 'untitled'
                                    video_title = last_segment

                                # Save it
                                if os.path.exists(DOWNLOAD_FILE):
                                    with open(DOWNLOAD_FILE, 'r', encoding='utf-8') as f:
                                        try:
                                            entries = json.load(f)
                                            if not isinstance(entries, list):
                                                entries = []
                                        except json.JSONDecodeError:
                                            entries = []

                                    # Step 2: Append new entry
                                entries.append({
                                    "file": video_title,
                                    "url": full_url
                                })

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

        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            f.write('')

    return Response(stream_with_context(generate()), content_type='text/event-stream')

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

                        messages.put(f"data: Downloading: {percent} at {speed}, ETA {eta} [{current_index}/{total}]\n\n")
                    elif d['status'] == 'finished':
                        messages.put(f"data: ✅ Download complete: {d['filename']}\n\n")
                    elif d['status'] == 'error':
                        messages.put("data: ❌ Download failed.\n\n")

                ydl_opts = {
                    'format': 'best',
                    'outtmpl': f'{DOWNLOAD_DIR}%(title)s.%(ext)s',
                    'postprocessors': [{'key': 'FFmpegMetadata'}],
                    'addmetadata': True,
                    'progress_hooks': [progress_hook],  # ✅ This is critical!
                }

                yield f"data: ▶️ Downloading ({current_index}/{total}): {name}, {url}\n\n"
                logging.info(f"data: Downloading ({current_index}/{total}): {name}, {url}")

                try:
                    def download_and_drain():
                        with YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        # Signal end
                        messages.put("done")

                    # Start download in a thread to allow streaming progress
                    thread = threading.Thread(target=download_and_drain)
                    thread.start()

                    # Stream messages from queue in real-time
                    while True:
                        msg = messages.get()
                        if msg == "done":
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
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

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
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

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

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        with open('config.json', 'x', encoding='utf-8') as f:
            f.write('''"web-dlp-down-z Log file": "logs",
            "Download To": "~/Downloads",
            "Download File": "download.json",
            "Playlist File": "playlist.json",
            "Download full log": "log_download.txt",
            "Playlist full log": "log_download.txt",
            "Process": "process.txt",
            "Playlist Processed": "playlist_processed.txt"
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