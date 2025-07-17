import json
import os
import logging


DOWNLOAD_DIR = '~/Downloads'
HIERARCHY_DIR = False
SYSTEM_THEME = 'default'


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SYSTEM_DIR = os.path.join(os.path.dirname(__file__), 'instance')
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')

CONFIG_FILE = os.path.join(SYSTEM_DIR, 'config.json')
FILE_CONFIG = os.path.join(SYSTEM_DIR, 'file_config.json')
PLAYLIST_FILE = os.path.join(DATA_DIR, 'default-playlist.json')
DOWNLOAD_FILE = os.path.join(DATA_DIR, 'default-download.json')
DEFAULT_CONFIG_FILE = os.path.join(DATA_DIR, 'default-config.json')
PROCESS_FILE = os.path.join(LOG_DIR, 'process.txt')
PLAYLIST_PROCESS_FILE = os.path.join(LOG_DIR, 'playlist_processed.txt')
SYSTEM_FILE = os.path.join(SYSTEM_DIR, 'system.json')


def configBackground():
    global DOWNLOAD_DIR, DOWNLOAD_FILE, PROCESS_FILE, DOWNLOAD_FILE, PROCESS_FILE, HIERARCHY_DIR, SYSTEM_THEME
    with open('instance/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    logfile = config['web-dlp-down-z Log file']
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    config_background()

    with open('../system.json', 'r', encoding='utf-8') as f:
        system = json.load(f)
    try:
        SYSTEM_THEME = system['theme']
    except Exception as e:
        system['theme'] = 'default'
        with open('../system.json', 'w', encoding='utf-8') as f:
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

def config_background():
    system_file = os.path.join(SYSTEM_DIR, 'system.json')
    with open(system_file, 'r', encoding='utf-8') as f:
        system = json.load(f)
    try:
        SYSTEM_THEME = system['theme']
    except Exception as e:
        system['theme'] = 'default'
        with open('../system.json', 'w', encoding='utf-8') as f:
            json.dump(system, f, ensure_ascii=False, indent=4)
    logging.info(f"web setConfigSettings: SYSTEM theme: {SYSTEM_THEME}")
    print('config_background', SYSTEM_THEME)
    return SYSTEM_THEME

def set_background(theme):
    global SYSTEM_THEME
    SYSTEM_THEME = theme
    system_file = os.path.join(SYSTEM_DIR, 'system.json')
    with open(system_file, 'r', encoding='utf-8') as f:
        system = json.load(f)
    system['theme'] = theme
    with open(system_file, 'w', encoding='utf-8') as f:
        json.dump(system, f, indent=4)