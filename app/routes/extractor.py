import os

import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse, urljoin

from flask import render_template, url_for, request, redirect,Blueprint, Response, stream_with_context
from yt_dlp import YoutubeDL

from app.config_loader import (FILE_CONFIG, DOWNLOAD_DIR, PLAYLIST_PROCESS_FILE, DOWNLOAD_FILE,
                               HIERARCHY_DIR, CONFIG_FILE, PROCESS_FILE, DEFAULT_CONFIG_FILE, DATA_DIR)
from ..config_loader import config_background

bp = Blueprint('extractor', __name__)

extractor_data = {}

@bp.route('/extractor')
def extractor():
    installOpts = []
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            installOpts.append(item['file'])

    return render_template("extractor.html", sites=[], system_theme=config_background(), installOpts=installOpts)

@bp.route('/extractor/setExtractor', methods=('GET', 'POST'))
def setExtractor():
    global extractor_data
    if request.method == 'POST':
        extractor_data['url'] = request.form['extract_url']
        max_pages = request.form.get('max_pages',10)
        try:
            extractor_data['max_pages'] = int(max_pages) +1
        except Exception:
            extractor_data['max_pages'] = 10
        p = request.form['install']
        extractor_data['download_to'] = os.path.join(DATA_DIR, p)
    installOpts = []
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            installOpts.append(item['file'])
    return render_template("extractor.html", system_theme=config_background(), installOpts=installOpts,
                           default=p, install=True)


@bp.route('/extractor/extract')
def extractor_extract():
    def generate():
        def resolve_redirect(url, base_url=None):
            try:
                full_url = urljoin(base_url, url) if base_url else url
                response = requests.get(full_url, allow_redirects=True, timeout=5)
                return response.url
            except requests.RequestException:
                return ''

        global extractor_data
        if extractor_data['url']:
            url = extractor_data['url']
            max_pages = extractor_data['max_pages']
            download_to = extractor_data['download_to']

            headers = {"User-Agent": "Mozilla/5.0"}

            responses = []

            yield f"data: Extracting {url}\n\n"

            for page in range(1,max_pages):
                yield f"data: indexing page {page}/{max_pages - 1}\n\n"
                formated_url = url.format(page=page)
                print(formated_url)
                response = requests.get(formated_url, headers=headers)
                if response.status_code == 200:
                    responses.append(response)

            links = []
            for response in responses:
                soup = BeautifulSoup(response.text, "html.parser")

                video_keywords = ["watch", "video", "clip", "media", "embed", "out"]
                raw_links = [
                    a['href'] for a in soup.find_all('a', href=True)
                    if any(keyword in a['href'].lower() for keyword in video_keywords)
                ]
                resolve = False
                for link in raw_links:
                    if '/out/' in link:
                        resolve = True
                if resolve:
                    resov_index = 0
                    resov_max = len(raw_links)
                    for href in raw_links:
                        resov_index += 1
                        if '/out/' in href:
                            yield f"data: Resolving link {resov_index}/{resov_max} {href[:140]}{'...' if len(href) > 140 else ''}\n\n"
                            resolved = resolve_redirect(href, base_url=url)
                            yield f"data: Resolving link {resov_index}/{resov_max} {resolved}\n\n"
                            links.append(resolved)
                        else:
                            links.append(urljoin(url, href))
                else:
                    links.extend(raw_links)

            entries = []
            if os.path.exists(download_to):
                with open(download_to, 'r', encoding='utf-8') as f:
                    try:
                        entries = json.load(f)
                        if not isinstance(entries, list):
                            entries = []
                    except json.JSONDecodeError:
                        entries = []

            existing_urls = {entry.get('url') for entry in entries}
            length_links = len(links)

            for link in links:
                parsed = urlparse(link)
                last_segment = parsed.path.rstrip('/').split('/')[-1] or 'untitled'
                video_title = last_segment
                idx = links.index(link) if link in links else None

                yield f"data: Adding metadata for {link} {idx}/{length_links}\n\n"

                ydl_opts = {
                    'skip_download': True,
                    'quiet': True
                }

                with YoutubeDL(ydl_opts) as ydl:
                    def Get_Metadata(blob):
                        url = blob["url"]  # filename URL
                        name = blob["file"] if blob["file"] else "unnamed"
                        ret = {'url': url, 'name': name}
                        ydl_opts = {
                            'skip_download': True,
                            'quiet': True
                        }
                        with YoutubeDL(ydl_opts) as ydl:
                            try:
                                info = ydl.extract_info(url, download=False)
                                print("3")
                                try:
                                    ret["thumbnail"] = info.get('thumbnail')
                                except Exception:
                                    ret["thumbnail"] = ''
                                try:
                                    ret["duration"] = info.get('duration')
                                except Exception as e:
                                    if "private" in str(e).lower():
                                        ret["duration"] = 'PRIVATE VIDEO'
                                    else:
                                        ret["duration"] = 'None'
                                try:
                                    ret["description"] = info.get('description')
                                except Exception:
                                    ret["description"] = ''
                            except Exception as e:
                                if "private" in str(e).lower():
                                    ret["duration"] = 'PRIVATE VIDEO'
                                else:
                                    ret["duration"] = 'None'
                                ret["description"] = ''
                                ret["thumbnail"] = ''
                        return ret
                    try:
                        info = ydl.extract_info(link, download=False)
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
                if link not in existing_urls:
                    entries.append({
                        "file": video_title,
                        "url": link,
                        'duration': duration,
                        'description': description,
                        'thumbnail': thumbnail,
                    })
                    existing_urls.add(link)

                for entry in entries:
                    if not entry['duration'] or not entry['thumbnail']:
                        entry_meta = Get_Metadata(entry)
                        entry['duration'] = entry_meta['duration']
                        entry['thumbnail'] = entry_meta['thumbnail']
                        entry['description'] = entry_meta['description']

                with open(download_to, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, indent=4)
            extractor = {}
    return Response(stream_with_context(generate()), content_type='text/event-stream')

