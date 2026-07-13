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

DB_PATH = Path("./bili-config.db")

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

    def write_log(self, text: str):
        self.logs.append(text)
        self.broadcast({"type": "log", "message": text})

    def set_progress(self, val: int):
        self.progress = val
        self.broadcast({"type": "progress", "value": val})

    def set_status(self, stat: str):
        self.status = stat
        self.broadcast({"type": "status", "status": stat})

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
        self.input_received_event.wait()
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

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn

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
    def __init__(self):
        self.encoding = sys.__stdout__.encoding if sys.__stdout__ else "utf-8"
        self.errors = sys.__stdout__.errors if sys.__stdout__ else "strict"
    def write(self, text):
        if text.strip():
            session.write_log(text.strip())
    def flush(self):
        pass
    def isatty(self):
        return False

sys.stdout = WSStream()
sys.stderr = WSStream()

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

def run_download_thread(book_id: str, volume_id: str, config: dict):
    try:
        from backend.bilinovel.bilinovel_router import downloader_router
        session.set_status("downloading")
        session.write_log(f"Starting download for Book: {book_id}, Volume: {volume_id}")
        downloader_router(
            root_path=config.get("download_path", "./out"),
            book_no=book_id,
            volume_no=volume_id,
            interval=int(config.get("interval", 500)),
            num_thread=int(config.get("numthread", 1)),
            is_gui=True # Forces custom hang inputs
        )
        session.set_status("completed")
    except Exception as e:
        session.write_log(f"Download thread crashed: {e}")
        session.set_status("failed")
    finally:
        session.active = False

@app.post("/api/download")
def start_download(req: DownloadRequest):
    if session.active:
        raise HTTPException(status_code=400, detail="Another download is already in progress")
    session.active = True
    session.logs = []
    session.progress = 0
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
    session.loop = asyncio.get_event_loop()
    # Send initial state
    await websocket.send_text(json.dumps({
        "type": "init",
        "logs": session.logs,
        "progress": session.progress,
        "status": session.status,
        "input_prompt": session.input_needed_prompt if session.status == "input_required" else ""
    }))
    try:
        while True:
            await websocket.receive_text() # Keep connection alive
    except WebSocketDisconnect:
        session.ws_clients.remove(websocket)

# Static assets routing for reader images and texts
@app.get("/api/reader/asset")
def get_reader_asset(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Asset not found")
    # Serve HTML or images directly
    from fastapi.responses import FileResponse
    return FileResponse(path)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="127.0.0.1", port=port)
