import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import 'backend.server' etc.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import sqlite3
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# CORS configuration for local Tauri access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "bili-config.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
    finally:
        conn.close()

# Global State for Active Download Task
class DownloadSession:
    def __init__(self):
        self.active = False
        self.logs = []
        self.progress = 0
        self.status = "idle" # idle, downloading, input_required, completed, failed
        self.input_needed_prompt = ""
        self.input_options = []
        self.input_received_event = threading.Event()
        self.input_value = ""
        self.ws_clients = set()
        self.loop = None
        self.lock = threading.Lock()

    def write_log(self, text: str):
        with self.lock:
            self.logs.append(text)
        self.broadcast({"type": "log", "message": text})

    def get_logs_copy(self):
        with self.lock:
            return list(self.logs)

    def set_progress(self, val: Any):
        with self.lock:
            if val == "start":
                self.progress = 0
            elif val == "end":
                self.progress = 100
            else:
                try:
                    self.progress = int(val)
                except Exception:
                    pass
        self.broadcast({"type": "progress", "value": self.progress})

    def get_state_snapshot(self) -> dict:
        with self.lock:
            return {
                "active": self.active,
                "progress": self.progress,
                "status": self.status,
                "input_prompt": self.input_needed_prompt if self.status == "input_required" else "",
                "input_options": self.input_options if self.status == "input_required" else []
            }

    def set_status(self, stat: str):
        with self.lock:
            self.status = stat
        self.broadcast({"type": "status", "status": stat})

    def start_download_safe(self) -> bool:
        with self.lock:
            if self.active:
                return False
            self.active = True
            self.logs = []
            self.progress = 0
            self.status = "downloading"
            return True

    def request_input(self, prompt: str, options: list = []) -> str:
        with self.lock:
            self.input_needed_prompt = prompt
            self.input_options = options
            self.input_received_event.clear()
            self.input_value = ""
        
        self.set_status("input_required")
        self.broadcast({
            "type": "input_prompt", 
            "message": prompt, 
            "options": options
        })
        
        try:
            # Block calling thread until submit_input REST endpoint releases it
            if not self.input_received_event.wait(timeout=300):
                self.set_status("failed")
                self.write_log("Input prompt timed out.")
                raise RuntimeError("Input timed out")
            return self.input_value
        finally:
            with self.lock:
                self.input_needed_prompt = ""
                self.input_options = []

    def broadcast(self, data: dict):
        if self.loop and self.ws_clients:
            try:
                asyncio.run_coroutine_threadsafe(self._send_ws(data), self.loop)
            except Exception:
                pass

    async def _send_ws(self, data: dict):
        msg = json.dumps(data)
        for ws in list(self.ws_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                self.ws_clients.discard(ws)

session = DownloadSession()

def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            KEY TEXT PRIMARY KEY,
            VALUE TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS shelf (
            book_id TEXT,
            volume_id INTEGER,
            title TEXT,
            volume_name TEXT,
            author TEXT,
            publisher TEXT,
            cover_path TEXT,
            epub_path TEXT,
            cache_path TEXT,
            download_date TEXT,
            reading_progress_chapter INTEGER DEFAULT 0,
            reading_progress_scroll REAL DEFAULT 0.0,
            PRIMARY KEY (book_id, volume_id)
        );
        """)
        # Default config seed
        defaults = [
            ("download_path", "./out"),
            ("theme", "Dark"),
            ("interval", "500"),
            ("numthread", "4"),
            ("headless_mode", "True"),
            ("app_language", "zh-TW"),
            ("conversion_mode", "traditional")
        ]
        for k, v in defaults:
            conn.execute("INSERT OR IGNORE INTO config (KEY, VALUE) VALUES (?, ?)", (k, v))
        conn.commit()

init_db()

# Redirect standard outputs to WebSocket logs
class WSStream:
    def __init__(self, stream):
        self.stream = stream
        self.encoding = stream.encoding if stream else "utf-8"
        self.errors = stream.errors if stream else "strict"
    def write(self, text):
        if text.strip():
            session.write_log(text.strip())
        if self.stream:
            self.stream.write(text)
    def flush(self):
        if self.stream:
            self.stream.flush()
    def isatty(self):
        return False

sys.stdout = WSStream(sys.__stdout__)
sys.stderr = WSStream(sys.__stderr__)

# REST APIs
class ConfigModel(BaseModel):
    download_path: str
    theme: str
    interval: str
    numthread: str
    headless_mode: str
    app_language: Optional[str] = None
    conversion_mode: Optional[str] = None

@app.get("/api/config")
def get_config():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT KEY, VALUE FROM config")
        res = dict(cursor.fetchall())
    return res

@app.post("/api/config")
def save_config(cfg: ConfigModel):
    with get_db() as conn:
        for k, v in cfg.dict().items():
            if v is not None:
                conn.execute("INSERT OR REPLACE INTO config (KEY, VALUE) VALUES (?, ?)", (k, v))
        conn.commit()
    return {"status": "success"}

@app.get("/api/shelf")
def get_shelf():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT book_id, volume_id, title, volume_name, author, publisher, 
                   cover_path, epub_path, cache_path, download_date,
                   reading_progress_chapter, reading_progress_scroll 
            FROM shelf
        """)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return rows

class ProgressModel(BaseModel):
    book_id: str
    volume_id: int
    chapter_index: int
    scroll_position: float

@app.post("/api/shelf/progress")
def update_progress(prog: ProgressModel):
    with get_db() as conn:
        conn.execute("""
            UPDATE shelf 
            SET reading_progress_chapter = ?, reading_progress_scroll = ? 
            WHERE book_id = ? AND volume_id = ?
        """, (prog.chapter_index, prog.scroll_position, prog.book_id, prog.volume_id))
        conn.commit()
    return {"status": "success"}

@app.delete("/api/shelf/{book_id}/{volume_id}")
def delete_book(book_id: str, volume_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT epub_path, cache_path FROM shelf WHERE book_id = ? AND volume_id = ?", (book_id, volume_id))
        row = cursor.fetchone()
        if row:
            epub, cache = row
            
            # Load download path config
            dl_path_str = "./out"
            try:
                cursor.execute("SELECT VALUE FROM config WHERE KEY = 'download_path'")
                db_dl = cursor.fetchone()
                if db_dl:
                    dl_path_str = db_dl[0]
            except Exception:
                pass
            dl_path = Path(dl_path_str).resolve()
            
            try:
                if epub:
                    epub_path = Path(epub).resolve()
                    if epub_path.is_relative_to(dl_path) and epub_path != dl_path:
                        if epub_path.is_file():
                            os.remove(str(epub_path))
                if cache:
                    cache_path = Path(cache).resolve()
                    if cache_path.is_relative_to(dl_path) and cache_path != dl_path:
                        if cache_path.is_dir():
                            import shutil
                            shutil.rmtree(str(cache_path))
                        # Remove the parent .library dir if now empty
                        library_dir = cache_path.parent
                        if library_dir.is_dir() and not any(library_dir.iterdir()):
                            library_dir.rmdir()
                # Remove parent book dir if now empty (no more volumes)
                if epub:
                    book_dir = Path(epub).resolve().parent
                    if book_dir.is_relative_to(dl_path) and book_dir != dl_path:
                        if book_dir.is_dir() and not any(f for f in book_dir.iterdir() if f.suffix == '.epub'):
                            import shutil
                            shutil.rmtree(str(book_dir))
            except Exception as e:
                print(f"Error deleting files: {e}")

        conn.execute("DELETE FROM shelf WHERE book_id = ? AND volume_id = ?", (book_id, volume_id))
        conn.commit()
    return {"status": "success"}

class DownloadRequest(BaseModel):
    book_id: str
    volume_id: str

class MockEditLine:
    def __init__(self):
        self._is_hidden = True
        self._text = ""
        self.options = []

    def isHidden(self):
        return self._is_hidden

    def text(self):
        return self._text

    def clear(self):
        self._text = ""
        self.options = []

    def addItems(self, items):
        self.options = list(items)

    def setCurrentIndex(self, idx):
        pass

class MockSignal:
    def __init__(self, name="", edit_line=None):
        self.name = name
        self.edit_line = edit_line

    def emit(self, val):
        if self.name == "progress":
            session.set_progress(val)
        elif self.name == "hang" and self.edit_line:
            self.edit_line._is_hidden = False
            logs = session.get_logs_copy()
            prompt = session.input_needed_prompt or (logs[-1] if logs else "请输入所需資訊：")
            user_input = session.request_input(prompt, self.edit_line.options)
            self.edit_line._text = user_input
            self.edit_line._is_hidden = True
        elif self.name == "cover":
            session.write_log(f"Cover generated: {val[0]}")
        else:
            session.write_log(f"Signal {self.name} emitted: {val}")

def run_download_thread(book_id: str, volume_id: str, config: dict):
    try:
        from backend.bilinovel.bilinovel_router import downloader_router
        session.set_status("downloading")
        session.write_log(f"Starting download for Book: {book_id}, Volume: {volume_id}")
        edit_line = MockEditLine()
        downloader_router(
            root_path=config.get("download_path", "./out"),
            book_no=book_id,
            volume_no=volume_id,
            interval=int(config.get("interval", 500)),
            num_thread=int(config.get("numthread", 1)),
            is_gui=True,
            hang_signal=MockSignal("hang", edit_line),
            progressring_signal=MockSignal("progress"),
            cover_signal=MockSignal("cover"),
            edit_line_hang=edit_line
        )
        session.set_status("completed")
    except Exception as e:
        session.write_log(f"Download thread crashed: {e}")
        session.set_status("failed")
    finally:
        with session.lock:
            session.active = False

@app.post("/api/download")
def start_download(req: DownloadRequest):
    if not session.start_download_safe():
        raise HTTPException(status_code=400, detail="Another download is already in progress")
    cfg = get_config()
    thread = threading.Thread(target=run_download_thread, args=(req.book_id, req.volume_id, cfg), daemon=True)
    thread.start()
    return {"status": "started"}

class InputSubmission(BaseModel):
    value: str

@app.post("/api/download/submit_input")
def submit_input(submission: InputSubmission):
    state = session.get_state_snapshot()
    if state["status"] != "input_required":
        raise HTTPException(status_code=400, detail="No input is required at this time")
    session.input_value = submission.value
    session.set_status("downloading")
    session.input_received_event.set()
    return {"status": "submitted"}

@app.websocket("/api/download/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session.ws_clients.add(websocket)
    session.loop = asyncio.get_running_loop()
    try:
        # Send initial state
        state = session.get_state_snapshot()
        await websocket.send_text(json.dumps({
            "type": "init",
            "logs": session.get_logs_copy(),
            "progress": state["progress"],
            "status": state["status"],
            "input_prompt": state["input_prompt"],
            "input_options": state["input_options"]
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        session.ws_clients.discard(websocket)

@app.get("/api/reader/asset")
def get_reader_asset(path: str):
    resolved_path = Path(path).resolve()
    
    # Load download_path from DB config if exists, otherwise default to "./out"
    dl_path_str = "./out"
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT VALUE FROM config WHERE KEY = 'download_path'")
            row = cursor.fetchone()
            if row:
                dl_path_str = row[0]
    except Exception:
        pass
    dl_path = Path(dl_path_str).resolve()

    # Safety checks: Must be strictly inside dl_path
    if not (resolved_path.is_relative_to(dl_path) and resolved_path != dl_path):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
        
    from fastapi.responses import FileResponse
    return FileResponse(str(resolved_path))

@app.post("/api/shelf/convert/{book_id}/{volume_id}")
def convert_shelf_book(book_id: str, volume_id: int):
    import zhconv
    import zipfile
    import shutil

    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Query conversion_mode config value
        cursor.execute("SELECT VALUE FROM config WHERE KEY = 'conversion_mode'")
        row_mode = cursor.fetchone()
        conversion_mode = row_mode[0] if row_mode else "none"
        
        if conversion_mode == "none":
            return {"status": "success", "message": "Conversion mode is none, no action taken."}
            
        # Determine locale
        if conversion_mode == "traditional":
            locale = "zh-hant"
        elif conversion_mode == "simplified":
            locale = "zh-hans"
        else:
            return {"status": "success", "message": f"Unknown conversion mode '{conversion_mode}', no action taken."}
            
        # 2. Retrieve book metadata paths (epub_path, cache_path)
        cursor.execute("""
            SELECT title, volume_name, author, publisher, epub_path, cache_path 
            FROM shelf 
            WHERE book_id = ? AND volume_id = ?
        """, (book_id, volume_id))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Book not found in shelf")
            
        title, volume_name, author, publisher, epub_path, cache_path = row
        
        # Load download path config
        dl_path_str = "./out"
        cursor.execute("SELECT VALUE FROM config WHERE KEY = 'download_path'")
        db_dl = cursor.fetchone()
        if db_dl:
            dl_path_str = db_dl[0]
        dl_path = Path(dl_path_str).resolve()
        
        # Path Safety Guards
        if not epub_path or not cache_path:
            raise HTTPException(status_code=400, detail="Missing epub_path or cache_path in database")
            
        resolved_epub_path = Path(epub_path).resolve()
        resolved_cache_path = Path(cache_path).resolve()
        
        if not (resolved_epub_path.is_relative_to(dl_path) and resolved_epub_path != dl_path):
            raise HTTPException(status_code=403, detail="Access denied: epub_path outside download directory")
        if not (resolved_cache_path.is_relative_to(dl_path) and resolved_cache_path != dl_path):
            raise HTTPException(status_code=403, detail="Access denied: cache_path outside download directory")
            
        if not resolved_cache_path.exists() or not resolved_cache_path.is_dir():
            raise HTTPException(status_code=404, detail="Cache directory not found")
            
        # 3. Convert metadata fields in database
        conv_title = zhconv.convert(title, locale) if title else title
        conv_volume_name = zhconv.convert(volume_name, locale) if volume_name else volume_name
        conv_author = zhconv.convert(author, locale) if author else author
        conv_publisher = zhconv.convert(publisher, locale) if publisher else publisher
        
        cursor.execute("""
            UPDATE shelf 
            SET title = ?, volume_name = ?, author = ?, publisher = ? 
            WHERE book_id = ? AND volume_id = ?
        """, (conv_title, conv_volume_name, conv_author, conv_publisher, book_id, volume_id))
        
        # 4. Walk cache_path and convert all .xhtml, .opf, and .ncx files using zhconv.convert
        # Ensure all path operations are protected under strict subpath checks.
        for root, dirs, files in os.walk(resolved_cache_path):
            for file in files:
                file_path = Path(root) / file
                # Ensure the resolved file path is inside resolved_cache_path
                if not file_path.resolve().is_relative_to(resolved_cache_path):
                    continue
                if file.lower().endswith(('.xhtml', '.opf', '.ncx')):
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        converted_content = zhconv.convert(content, locale)
                        file_path.write_text(converted_content, encoding="utf-8")
                    except Exception as e:
                        print(f"Error converting file {file_path}: {e}")
                        raise HTTPException(status_code=500, detail=f"Failed to convert file {file}: {e}")
                        
        # 5. Recreate/re-zip the .epub file using the converted cache path files
        # (mimetype and container.xml should be preserved)
        mimetype_content = b"application/epub+zip"
        container_content = None
        
        if resolved_epub_path.exists():
            try:
                with zipfile.ZipFile(str(resolved_epub_path), "r") as zf:
                    if "mimetype" in zf.namelist():
                        mimetype_content = zf.read("mimetype")
                    if "META-INF/container.xml" in zf.namelist():
                        container_content = zf.read("META-INF/container.xml")
            except Exception as e:
                print(f"Failed to read original epub: {e}")
                
        if not container_content:
            container_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
   </rootfiles>
</container>"""

        # Re-zip to a temporary file
        temp_epub_path = Path(str(resolved_epub_path) + ".tmp")
        try:
            with zipfile.ZipFile(str(temp_epub_path), "w", zipfile.ZIP_DEFLATED) as zf:
                # mimetype MUST be first and ZIP_STORED (not compressed)
                zf.writestr("mimetype", mimetype_content, compress_type=zipfile.ZIP_STORED)
                zf.writestr("META-INF/container.xml", container_content)
                
                # Walk the cache path / "OEBPS" directory and write everything to the zip
                oebps_dir = resolved_cache_path / "OEBPS"
                if oebps_dir.exists() and oebps_dir.is_dir():
                    for root, dirs, files in os.walk(oebps_dir):
                        for file in files:
                            file_path = Path(root) / file
                            if not file_path.resolve().is_relative_to(oebps_dir):
                                continue
                            # e.g., relative to resolved_cache_path (which starts with OEBPS/...)
                            rel_path = file_path.relative_to(resolved_cache_path)
                            zf.write(str(file_path), str(rel_path).replace("\\", "/"))
                            
            # Safely replace the old epub atomically
            os.replace(str(temp_epub_path), str(resolved_epub_path))
        except Exception as e:
            if temp_epub_path.exists():
                try:
                    os.remove(str(temp_epub_path))
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to rebuild EPUB: {e}")
            
        conn.commit()
        return {"status": "success"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="127.0.0.1", port=port)
