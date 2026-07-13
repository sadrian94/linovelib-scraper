import os
import sys
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
        conn.execute("PRAGMA journal_mode=DELETE")
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

    def set_progress(self, val: int):
        with self.lock:
            self.progress = val
        self.broadcast({"type": "progress", "value": val})

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
        self.input_needed_prompt = prompt
        self.input_options = options
        self.set_status("input_required")
        self.broadcast({
            "type": "input_prompt", 
            "message": prompt, 
            "options": options
        })
        self.input_received_event.clear()
        self.input_value = ""
        # Block calling thread until submit_input REST endpoint releases it
        success = self.input_received_event.wait(timeout=300)
        if not success:
            self.set_status("failed")
            self.write_log("Input prompt timed out.")
            raise RuntimeError("Input timed out")
        return self.input_value

    def broadcast(self, data: dict):
        if self.loop and self.ws_clients:
            asyncio.run_coroutine_threadsafe(self._send_ws(data), self.loop)

    async def _send_ws(self, data: dict):
        msg = json.dumps(data)
        for ws in list(self.ws_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                self.ws_clients.remove(ws)

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
            ("headless_mode", "True")
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
            try:
                if epub and os.path.exists(epub):
                    os.remove(epub)
                if cache and os.path.exists(cache):
                    import shutil
                    shutil.rmtree(cache)
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
    if session.status != "input_required":
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
        await websocket.send_text(json.dumps({
            "type": "init",
            "logs": session.get_logs_copy(),
            "progress": session.progress,
            "status": session.status,
            "input_prompt": session.input_needed_prompt if session.status == "input_required" else ""
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        session.ws_clients.discard(websocket)

# Static assets routing for reader images and texts
@app.get("/api/reader/asset")
def get_reader_asset(path: str):
    # Resolve requested path
    resolved_path = Path(path).resolve()
    
    # Resolve current workspace path & out path
    workspace_path = Path(__file__).resolve().parent.parent
    
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

    # Safety checks
    if not (resolved_path.is_relative_to(workspace_path) or resolved_path.is_relative_to(dl_path)):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
        
    from fastapi.responses import FileResponse
    return FileResponse(str(resolved_path))

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="127.0.0.1", port=port)
