# Web-dlp-down-z

**Web-dlp-down-z** is a media scraping and management tool that leverages `yt-dlp` to download 
various types of media from different sources. It supports downloading individual media files as
well as full playlists, and organizes logs for better control and recovery. Created using Flask-python

---

# Web-dlp-down-z

**Web-dlp-down-z** is a media scraping and management tool that leverages `yt-dlp` to download 
various types of media from different sources. It supports downloading individual media files as
well as full playlists, and organizes logs for better control and recovery. Created using Flask-python

---

🐍 New to Python?
No problem! You don’t need to write any Python code to use this tool.

📦 **Quick Start**:
1. Download the latest .zip file of the project.

2. Extract it to a folder that’s easy to access (e.g., Desktop or Documents).

3. Install Python (if it’s not already installed):

   - Download from: https://www.python.org/downloads/

   - Make sure to check the box that says “Add Python to PATH” during installation.

Install dependencies:

Open a terminal or command prompt in the folder you extracted, then run:
`pip install -r requirements.txt`

Start the app:
`python app.py`

Open your browser and go to:
`http://localhost:8080` or if you know your ip address `http://<ip>:8080`

That’s it! You’re now running Web-dlp-down-z on your local machine.

>💡 Tip: If you're unfamiliar with terminal commands, just ask! This tool is made to work with zero programming experience.
---

## ⚙️ Setup

Make sure to set your download path in the `settings` tab default is linux:
- **Windows**:  
  `C:\Users\<your-username>\Downloads`
- **Linux/macOS**:  
  `~/Downloads`

Recommended: leave all `logs` and `files` in their default location. You can move them with the config settings.
- download file is the default downloads list
- playlist file is the default playlist list
- logs are the yt-dlp logs ~ currently not active will contain nothing
- processed are the log files of all downloaded content and all playlists flattened

### Hierarchy
This setting is important for users who want to sort their files automatically. By default this setting is turned off, to enable this enter `true`.
- The hierarchy setting is configured to use `yt-dlp`'s metadata and sort files as follows `download_to/webpage_url_domain/uploader/<files>)`.
  - `download_to` - the location you configured your download locations to go
  - `webpage_url` - the name of the website you are downloading the video from
  - `uploader` - the *creator* or *uploader* of the file your downloading

Future plans for this setting are going to help umbrella videos more:
- Custom tagging: `download_to/tag/`, `download_to/tag/webpage_url`, `download_to/tag/uploader`,  `download_to/tag/webpage_url/uploader`.   

---

## ✍️ Using the Tool – Editing Links

Navigate to the `edit` section. Here you'll find groups:
- When you select your group you will see the playlist list by default
- Press 'View Downloadable files' to see the list of download video links

Saving:
- Save will only save the file
- Save and execute will save the file and order you chose then it will execute a flatten or install
  - Flatten: flattens the playlist to the individual links so that you can remove and reorder how its downloaded
  - Install: downloads all of the links in the select download list

Setting install locations:
- Each new group has default install locations:
  - `Playlist` installs to its paired download list
  - `Download` installs to the default location set in the `config file: edit this in the  settings tab`
- Each can be set to install to seperate locations:
  - `Playlist` is required to install to an existing download file
  - `Download` is required to install to an existing directory or folder
> WARNING: Each entry includes a **namespace** (a descriptive name or label). This is for logging and readability only; it does not affect the actual filenames.

---

## ▶️ Using the Tool – Executing Downloads

In the `execute` section:
>WARNNING: Execute is still in development
- You will see a queue to download everything and or flatten everything at once.
  - Make sure to set all of the playlists in the queue before its set install location or else these will not download and only get added to the download list
---

## 📄 Viewing Logs

The `view` section can be found in the settings tab with the top menu
- `playlist log` logs all playlists flattened in DATE NAMESPACE URL format
- `download log`logs all downloads in DATE NAMESPACE URL (Success|Error) format
---

## ✅ Features

- Supports individual and playlist-based downloads
- Editable queue with save-and-execute option
- Auto-retry for failed downloads
- Choosing download formats
  - `3gp`, `aac`, `flv`, `m4a`, `mp3`, `mp4`, `ogg`, `wav`, `webm`
- Automatic file naming from source titles
- Automatic metadata generation if provided by the source
- Logs and grouping for better management
- Cross-platform support (Windows, Linux, macOS)
- Web themes
  - default - blue and white
  - evergreen - green and white
  - evergreen dark - green and black
  - code - code like theme
  - code dark - dark code like theme

---

# Upgrade compatibility:
- v1.3.6 → direct
- v1.3.5 → partial / manual change required
- < v1.3.5 → legacy / needs multiple configurations and changes to update. best option is to download the newest version and follow the below instructions.

follow the directions in the `Backup recovery` issue to complete all changes.
this is a major structure update and this update may not have all of the tools to move files where they need to go.

---

## Whats New v2.0.0:

- System-wide restructure. This is for updates alone, instead of changes to app.py changes now appear in places like `routes` which is the source of all app functions:
  - all files in `static` and `templates` should now be found inside of the app folder
  - config files are now located in `instance` folder
  - log files are in the `logs` folder
  - the `data` folder houses all the lists .json files
- New features:
  - Styles:
    - Now indexes the `static/css` folder so that drag and drop can work
  - Cookies:
    - You can now download Private and payed content that you can access from your account
    - use a tool like Cookie editor to copy the cookies. go to `web-dlp-down-z/app/data` add a file call it `cookies.json`
    - not all cookies work to get past these walls, and not all websites work with yt-dlp
---

## 📌 Requirements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Python 3.6+
- Internet connection

---