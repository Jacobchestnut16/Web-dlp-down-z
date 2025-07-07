import os
import time
import queue
import threading
import re
from urllib.parse import urlparse
from flask import Flask, render_template, url_for, request, redirect, Response, stream_with_context
from yt_dlp import YoutubeDL


app = Flask(__name__)

PLAYLIST_FILE = 'playlist.txt'
PLAYLIST_PROCESS_FILE = 'playlist_processed.txt'
DOWNLOAD_FILE = 'download.txt'
PROCESS_FILE = 'process.txt'
CONFIG_FILE = 'config.txt'
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
    with open(file, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
        entries = []
        for line in lines:
            parts = line.rsplit(maxsplit=1)
            if len(parts) == 2:
                filename, website = parts
                entries.append({'filename': filename, 'website': website})
            else:
                # If there's a malformed line, skip or handle it
                entries.append({'filename': parts[0], 'website': ''})
    return render_template('file.html', entries=entries, where=file[:-4])

@app.route('/save', methods=['GET', 'POST'])
def save():
    filenames = request.form.getlist('filename')
    websites = request.form.getlist('website')
    file = request.form.get('file')

    try:
        with open(file, 'w', encoding='utf-8') as f:
            for name, site in zip(filenames, websites):
                line = f"{name} {site}\n"
                f.write(line)
    except Exception as e:
        return f"Error: {e}"
    else:
        if file == CONFIG_FILE:
            return redirect(url_for('setConfigSettings'))
        return redirect(url_for('edit', file=file, mark="Saved"))  # or back to 'edit' if that’s the page

@app.route('/execute')
def execute_index():
    return render_template('execute.html')

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
                playlist_lines = [line.strip() for line in f if line.strip()]

            # Step 2: Process each line one by one
            while playlist_lines:
                line = playlist_lines.pop(0)
                parts = line.strip().split(' ')
                url = parts[-1]  # filename URL
                name = parts[0] if len(parts) > 1 else "unnamed"

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
                                with open(DOWNLOAD_FILE, 'a', encoding='utf-8') as out:
                                    out.write(f"{video_title} {full_url}\n")

                                yield f"data: ✅ Added: {video_title}\n\n"

                        else:
                            yield f"data: ⚠️ Not a playlist: {url}\n\n"
                except Exception as ve:
                    yield f"data: ❌ Error processing {url}: {str(ve).splitlines()[0]}\n\n"


                time.sleep(0.2)

                yield f"data: ▶️ Reached Playlist end: {url}\n\n"

                with open(PLAYLIST_PROCESS_FILE, 'a', encoding='utf-8') as out:
                    out.write(f'{name} {url}\n')

                with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
                    for remaining in playlist_lines:
                        f.write(remaining + '\n')

        except Exception as e:
            yield f"data: 🚫 Fatal error: {str(e)}\n\n"

        yield "data: ✅ Done.\n\n"

        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            f.write('')

    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/execute/download')
def execute_download():
    with open(DOWNLOAD_FILE, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
        total = len(lines) + 1
        count = 1
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    def generate():
        messages = queue.Queue()

        yield "data: Starting Downloading process...\n\n"

        try:
            with open(DOWNLOAD_FILE, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]

            while lines:
                line = lines.pop(0)
                parts = line.strip().split(' ')
                url = parts[-1]
                name = parts[0] if len(parts) > 1 else "unnamed"
                current_index = total - len(lines)

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
                        out.write(f'{name} {url}\n')

                    # Remove the finished URL from the list
                    with open(DOWNLOAD_FILE, 'w', encoding='utf-8') as f:
                        for rem_line in lines:
                            f.write(rem_line + '\n')

                except Exception as ve:
                    yield f"data: ❌ Error processing {name},{url}: {str(ve).splitlines()[0]}\n\n"

        except Exception as ve:
            yield f"data: 🚫 Fatal error: {str(ve)}\n\n"

        yield "data: ✅ Done.\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')



@app.route('/config')
def config():
    with open(CONFIG_FILE, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
        entries = []
        for line in lines:
            parts = line.rsplit("'")
            if len(parts) == 2:
                filename, website = parts
                entries.append({'filename': filename, 'website': website})
            else:
                # If there's a malformed line, skip or handle it
                entries.append({'filename': parts[0], 'website': ''})
    return render_template('config.html', entries=entries, where='config')

@app.route('/setConfigSettings')
def setConfigSettings():
    with open('config.txt', 'r', encoding='utf-8') as f:
        try:
            rnf = f.readline().split("'")
            DOWNLOAD_DIR = os.path.normpath(rnf[1].strip())
            DOWNLOAD_DIR = DOWNLOAD_DIR + os.sep if not DOWNLOAD_DIR.endswith(os.sep) else DOWNLOAD_DIR
        except Exception:
            DOWNLOAD_DIR = os.path.normpath(DOWNLOAD_DIR)

        try:
            rng = f.readline().split("'")
            DOWNLOAD_FILE = os.path.normpath(rnf[1].strip())
        except Exception:
            DOWNLOAD_FILE = os.path.normpath(DOWNLOAD_FILE)

        try:
            rnh = f.readline().split("'")
            PLAYLIST_FILE = os.path.normpath(rnf[1].strip())
        except Exception:
            PLAYLIST_FILE = os.path.normpath(DOWNLOAD_FILE)

        rni = f.readline().split("'")
        rnj = f.readline().split("'")

        try:
            rnk = f.readline().split("'")
            PROCESS_FILE = os.path.normpath(rnf[1].strip())
        except Exception:
            PROCESS_FILE = os.path.normpath(DOWNLOAD_FILE)

        try:
            rnl = f.readline().split("'")
            PROCESS_DIR = os.path.normpath(rnf[1].strip())
        except Exception:
            PROCESS_DIR = os.path.normpath(DOWNLOAD_FILE)
    return redirect(url_for('config'))

def configBackground():
    with open('config.txt', 'r', encoding='utf-8') as f:
        try:
            rnf = f.readline().split("'")
            DOWNLOAD_DIR = os.path.normpath(rnf[1].strip())
            DOWNLOAD_DIR = DOWNLOAD_DIR + os.sep if not DOWNLOAD_DIR.endswith(os.sep) else DOWNLOAD_DIR
        except Exception:
            DOWNLOAD_DIR = os.path.normpath(DOWNLOAD_DIR)

        try:
            rng = f.readline().split("'")
            DOWNLOAD_FILE = os.path.normpath(rnf[1].strip())
        except Exception:
            DOWNLOAD_FILE = os.path.normpath(DOWNLOAD_FILE)

        try:
            rnh = f.readline().split("'")
            PLAYLIST_FILE = os.path.normpath(rnf[1].strip())
        except Exception:
            PLAYLIST_FILE = os.path.normpath(DOWNLOAD_FILE)


        rni = f.readline().split("'")
        rnj = f.readline().split("'")

        try:
            rnk = f.readline().split("'")
            PROCESS_FILE = os.path.normpath(rnf[1].strip())
        except Exception:
            PROCESS_FILE = os.path.normpath(DOWNLOAD_FILE)

        try:
            rnl = f.readline().split("'")
            PROCESS_DIR = os.path.normpath(rnf[1].strip())
        except Exception:
            PROCESS_DIR = os.path.normpath(DOWNLOAD_FILE)

if __name__ == '__main__':
    try:
        with open('config.txt', 'x', encoding='utf-8') as f:
            f.write('''Download To  ' ~/Downloads
            Download File  ' download.txt
            Playlist File  ' playlist.txt
            Download full log ' log_download.txt
            Playlist full log ' log_download.txt
            Process (do not change) ' process.txt
            Playlist Processed (do not change) ' playlist_processed.txt
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