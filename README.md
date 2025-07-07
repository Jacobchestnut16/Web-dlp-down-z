# Web-dlp-down-z

**Web-dlp-down-z** is a media scraping and management tool that leverages `yt-dlp` to download 
various types of media from different sources. It supports downloading individual media files as
well as full playlists, and organizes logs for better control and recovery. Created using Flask-python

---

## ⚙️ Setup

Before starting, configure your download path in the `config` file, this can be done manually or by using the config tab after running `app.py`:

- **Windows**:  
  `C:\Users\<your-username>\Downloads`
- **Linux/macOS**:  
  `~/Downloads`

---

## ✍️ Using the Tool – Editing Links

Navigate to the `edit` section. You'll find two files:

- **downloads**:  
  Contains individual media links to be downloaded.  
  - You can **remove**, **reorder**, or **add** links as needed.
  - Links will be processed in the order they appear.

- **playlist**:  
  Contains URLs to playlists.  
  - Must be valid playlist links with downloadable media.
  >WARNING:
  >Each entry includes a **namespace** (a descriptive name or label). This is for logging and readability only; it does not affect the actual filenames.

---

## ▶️ Using the Tool – Executing Downloads

In the `execute` section, you'll find two processes:

- **process_playlist**:
  - Breaks each playlist URL from the `playlist` file into individual media links.
  - Each item is auto-named in the namespace based on its web link title.
  - Does **not** display a progress bar — rely on the log output to check status.
  
- **downloads**:
  - Downloads all individual links listed in the `downloads` file (latest saved version).
  - Displays an ETA and progress bar for each download.
  - Log output shows the progress and completion status.
  - Names all files with the original name
  - Will add in the metadata if provided from the source

---

## 📄 Viewing Logs

The `view` section contains log files for both playlist and individual downloads:

- These logs are essential for tracking what has been downloaded or failed.
- **Logs must remain in the project folder** — they are hard coded so altering the location will restult in a crash or error.
- Even if a download fails, its attempt is logged.
- You can re-add failed or lost links from the logs back into the `downloads` file as needed (currently this is a failsafe, so you may have to copy and paste).

---

## ✅ Features

- Supports individual and playlist-based downloads
- Reorderable queue system
- Automatic file naming from source titles
- Logs for tracking success/failure and recovery
- Cross-platform support (Windows, Linux, macOS)

---

## 📌 Requirements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Python 3.6+
- Internet connection
