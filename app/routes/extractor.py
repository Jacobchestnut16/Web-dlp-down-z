import os

import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse

from flask import render_template, url_for, request, redirect,Blueprint
from yt_dlp import YoutubeDL

from app.config_loader import (FILE_CONFIG, DOWNLOAD_DIR, PLAYLIST_PROCESS_FILE, DOWNLOAD_FILE,
                               HIERARCHY_DIR, CONFIG_FILE, PROCESS_FILE, DEFAULT_CONFIG_FILE, DATA_DIR)
from ..config_loader import config_background

bp = Blueprint('extractor', __name__)

@bp.route('/extractor')
def extractor():
    installOpts = []
    with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
        files = json.load(f)
        for item in files:
            installOpts.append(item['file'])

    return render_template("extractor.html", sites=[], system_theme=config_background(), installOpts=installOpts)

@bp.route('/extractor/extract', methods=['GET', 'POST'])
def extractor_extract():
    if request.method == 'POST':
        url = request.form['extract_url']
        max_pages = request.form.get('max_pages',10)
        try:
            max_pages = int(max_pages) +1
        except Exception:
            max_pages = 10
        download_to = os.path.join(DATA_DIR, request.form['install'])
        headers = {"User-Agent": "Mozilla/5.0"}

        responses = []

        for page in range(1,max_pages):
            formated_url = url.format(page=page)
            print(formated_url)
            response = requests.get(formated_url, headers=headers)
            if response.status_code == 200:
                responses.append(response)

        links = []
        for response in responses:
            soup = BeautifulSoup(response.text, "html.parser")

            video_keywords = ["watch", "video", "clip", "media", "embed"]
            page_links = [
                a['href'] for a in soup.find_all('a', href=True)
                if any(keyword in a['href'].lower() for keyword in video_keywords)
                     ]
            links.extend(page_links)

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

        for link in links:
            parsed = urlparse(link)
            last_segment = parsed.path.rstrip('/').split('/')[-1] or 'untitled'
            video_title = last_segment

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
            if link not in existing_urls:
                entries.append({
                    "file": video_title,
                    "url": link,
                    'duration': duration,
                    'description': description,
                    'thumbnail': thumbnail,
                })
                existing_urls.add(link)
            with open(download_to, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=4)
        installOpts = []
        with open(FILE_CONFIG, 'r', encoding='utf-8') as f:
            files = json.load(f)
            for item in files:
                installOpts.append(item['file'])
        return render_template("extractor.html", sites=links, system_theme=config_background(), installOpts=installOpts, default=request.form['install'])

