"""
netmap: real-time network map for the 21 Sunpassion / SUNSU fleet.

  - Draws the topology once (collector skeleton) and overlays LIVE status.
  - Background poller refreshes the cache every POLL_SECONDS.
  - Front-end polls /api/topology and recolors nodes/edges in place.

Read-only: never writes to any device. ASCII-only comments.
"""

import os
import threading
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import collector

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))

_lock = threading.Lock()
_cache = {"data": None}

app = FastAPI(title="netmap")


def _refresh():
    data = collector.collect()
    with _lock:
        _cache["data"] = data
    return data


@app.get("/api/topology")
async def topology():
    with _lock:
        data = _cache["data"]
    if data is None:
        data = _refresh()
    return JSONResponse(data)


@app.post("/api/refresh")
async def refresh():
    return JSONResponse(_refresh())


@app.get("/api/health")
async def health():
    return {"ok": True, "collector": os.environ.get("COLLECTOR", "mock"),
            "poll": POLL_SECONDS}


@app.get("/api/diag")
async def diag(tool: str = "fortigate_status"):
    """Probe the MCP once and report exactly where it breaks."""
    return JSONResponse(collector.diag(tool))


def _loop():
    while True:
        try:
            _refresh()
        except Exception as e:
            print(f"[netmap] refresh failed: {e}", flush=True)
        time.sleep(max(POLL_SECONDS, 5))


@app.on_event("startup")
async def _start():
    _refresh()
    threading.Thread(target=_loop, daemon=True).start()


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
