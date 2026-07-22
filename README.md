# 嗶哩輕小說下載器 · BiliNovel Downloader

A desktop application for downloading and reading light novels from **嗶哩輕小說 (BiliNovel)**.  
Built with **Tauri + React + TypeScript** on the frontend and **Python (FastAPI)** on the server.

---

## ✨ Features

- 📥 **Novel Download** — Download novels by Book ID and volume range, with real-time log output and progress tracking
- 📚 **Local Shelf** — Browse downloaded books in a cover-grid library view with search support
- 📖 **In-App Reader** — Read downloaded novels directly inside the app, with chapter navigation, font size control, and scroll progress auto-saved
- 🔄 **Chinese Font Conversion** — Convert novel text between Traditional Chinese, Simplified Chinese, or keep original on download or post-download from the shelf
- 🌐 **Multilingual UI** — Interface available in 繁體中文, 简体中文, and English
- 🌙 **Headless Browser Mode** — Optionally run the browser in the background (headless) or visible window for manual CAPTCHA bypass

---

## 🖥️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop Shell | [Tauri v2](https://tauri.app) (Rust) |
| Frontend | React 18 + TypeScript + Tailwind CSS |
| Backend API | Python FastAPI + Uvicorn |
| Scraping | Playwright / nodriver |
| EPUB Generation | Custom XHTML + zipfile |
| Database | SQLite (local library index) |
| Font Conversion | zhconv |

---

## 🚀 Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) ≥ 18
- [Rust](https://www.rust-lang.org/tools/install) (stable toolchain)
- Python ≥ 3.10

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/linovelib-scraper.git
cd linovelib-scraper

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Node dependencies
npm install

# 4. Run in development mode
npm run tauri dev
```

> **Windows shortcut:** Double-click `BiliNovel-Download.bat` to launch the app without opening a terminal.

---

## 📂 Project Structure

```
linovelib-scraper/
├── server/                 # Python FastAPI server
│   ├── bilinovel/          # Novel scraper & EPUB engine
│   ├── app.py              # FastAPI server & REST API
│   └── browser_utils.py    # Browser initialization helpers
├── src/                    # React frontend source
│   ├── components/         # UI components (Downloader, Shelf, Reader, Settings)
│   └── utils/i18n.ts       # Multilingual translation dictionary
├── src-tauri/              # Tauri (Rust) shell & build config
│   └── binaries/           # Generated Python sidecar for release builds
├── dist/                   # Generated Vite frontend assets (not committed)
├── BiliNovel-Download.bat  # Windows one-click launcher
├── requirements.txt        # Python dependencies
└── package.json
```

`src/` and `server/` are source directories. `dist/` is recreated by Vite and
is consumed by Tauri only when producing the desktop bundle.

### Release build (Windows)

The installed application runs a bundled Python sidecar; it does not depend on
a system Python installation. Install the one release-only dependency once,
then run:

```bash
pip install -r requirements-build.txt
npm run tauri:build
```

---

## 📋 Roadmap

| Priority | Feature |
|----------|---------|
| 🔜 | **Amazon Kindle Integration** — Send downloaded EPUBs directly to your Kindle via Send-to-Kindle or USB |
| 🔜 | **AI Language Translation** — Translate novel content to other languages using LLM APIs |
| 🔜 | **Multi-Source Support** — Extend scraper support to additional light novel platforms beyond 嗶哩輕小說 |

---

## 🙏 Credits

This project was inspired by and built upon the original scraping work from:

- **[ShqWW/bilinovel-download](https://github.com/ShqWW/bilinovel-download)** — The original 嗶哩輕小說 downloader that laid the foundation for this project. We are grateful for the open-source contribution.

---

## ⚠️ Disclaimer

This project is intended for **personal, educational, and archival purposes only**.  
Please respect the copyright of all content creators and publishers.  
Do not use this tool to distribute or commercialize downloaded content.

---

## 📄 License

[MIT](LICENSE)
