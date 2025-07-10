# Web-dlp-down-z

**Web-dlp-down-z** is a media scraping and management tool that leverages `yt-dlp` to download 
various types of media from different sources. It supports downloading individual media files as
well as full playlists, and organizes logs for better control and recovery. Created using Flask-python

---

## ⚙️ Setup

Make sure to set your download path in the `settings` tab default is linux:
- **Windows**:  
  `C:\Users\<your-username>\Downloads`
- **Linux/macOS**:  
  `~/Downloads`

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
  - `Playlist` installs to its pared download list
  - `Download` installs to the default location set in the `config file: edit this in teh  settings tab`
- Each can be set to install to seperate locations:
  - `Playlist` is required to install to an existing download file
  - `Download` is required to install to an existing directory or folder
  >        WARNING:
  >        Each entry includes a **namespace** (a descriptive name or label). This is for logging and readability only; it does not affect the actual filenames.

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
- Reorderable queue system
- Automatic file naming from source titles
- Automatic metadata generation if provided by the source
- Logs for tracking success/failure and recovery
- Cross-platform support (Windows, Linux, macOS)

---

## Whats New v1.3.2:

- Execute tab is replaced with a Queue list.
- Save now has an option to save an execute in the edit page
- Groups: this groups the download and playlist pages together
  - Installation location is still determined by the user
  - Default for playlist is the groups download page
  - Default install for downloads is the directory based in the config file
- After a download starts it is no longer removed from the list if it fails
- Downloads will now retry to download something 3 time before it quits
  - Retries happen at the end of the process

---

## 📌 Requirements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Python 3.6+
- Internet connection
