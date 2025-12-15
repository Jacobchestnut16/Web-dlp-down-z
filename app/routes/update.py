import logging
import os
import json
import time

from flask import render_template, Response, stream_with_context, Blueprint
import requests
from ..config_loader import config_background, SYSTEM_FILE


bp = Blueprint('update', __name__)

def fetch_remote_json(url):
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def fetch_remote_file(url):
    res = requests.get(url)
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
    with open(SYSTEM_FILE, 'r', encoding='utf-8') as f:
        version = json.load(f)['version']
    ulr = BASE_URL+'system.json'
    remote_version = fetch_remote_json(ulr)["version"]
    if version != remote_version:
        return ("Update required", remote_version)
    else:
        return ("Up to date", version)

@bp.route('/update/start')
def update_now():
    def generate():
        PROJECT_SOURCE = os.path.abspath(os.path.join(__file__, "../../../"))
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

        with open(SYSTEM_FILE, 'r', encoding='utf-8') as f:
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
        for f in add_files:
            if f not in updated['add']:
                time.sleep(1)
                try:
                    dir_path = os.path.dirname(f)
                    dir_path = os.path.join(PROJECT_SOURCE, dir_path)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)

                    content = fetch_remote_file(BASE_URL + f)

                    try:
                        with open(os.path.join(PROJECT_SOURCE, f), 'x', encoding='utf-8') as file:
                            file.write(content)
                    except FileExistsError:
                        with open(os.path.join(PROJECT_SOURCE, f), 'w', encoding='utf-8') as file:
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
                        merge_json_files(os.path.join(PROJECT_SOURCE, f), fetch_remote_json(BASE_URL + f))
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
                        os.remove(os.path.join(PROJECT_SOURCE, f))
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
            with open(SYSTEM_FILE, 'r', encoding='utf-8') as f:
                system_features = json.load(f)
            system_features['version'] = remote_json['version']
            with open(SYSTEM_FILE, 'w', encoding='utf-8') as f:
                json.dump(system_features, f, indent=4)
            if app_need_update:
                with open(os.path.join(PROJECT_SOURCE, 'app.py'), 'w', encoding='utf-8') as f:
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



@bp.route('/update')
def update():
    from flask import current_app
    debug_mode = current_app.config.get('USE_RELOADER', False)
    with open(SYSTEM_FILE, 'r', encoding='utf-8') as f:
        current = json.load(f)['version']
    update = check_for_updates()
    if update[0] == "Update required":
        return render_template('update.html', updateTxt=update[0], updateVersion=update[1], current=current,
                               system_theme=config_background(), update_desc=fetch_remote_file(BASE_URL+'update_desc'), warning=debug_mode)
    else:
        return render_template('update.html', updateTxt=update[0], current=current,
                               system_theme=config_background(), update_desc=fetch_remote_file(BASE_URL+'update_desc'))

