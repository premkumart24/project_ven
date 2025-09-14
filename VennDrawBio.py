# vendrawbio.py
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from venn import venn
import io
import base64
import re
from itertools import combinations
from pathlib import Path
from typing import Dict, Any
import logging

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vendrawbio")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="VennDraw (static-folder)")

# ---------- CORS: allow your Netlify frontend + localhost for testing ----------
# Replace or add origins as needed. Using "*" is easier for debugging but NOT recommended in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://projectvenn.netlify.app",   # your Netlify frontend
        "http://localhost:8000",             # local test (when serving frontend from backend)
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from /static (index.html, logo.png, css, js can live here)
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")

# Serve index.html at root
@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        logger.error("index.html not found at %s", index_path)
        return HTMLResponse("<h3>index.html not found</h3>", status_code=404)
    return FileResponse(index_path, media_type="text/html")

# Health endpoint
@app.get("/health")
def health():
    return PlainTextResponse("ok")

# Venn API
@app.post("/venn")
async def venn_diagram(values: Dict[str, Any] = Body(...)):
    try:
        logger.info("Received venn request: keys=%s", list((values or {}).keys()))
        sets = {}
        case_map = {}
        for k, v in (values or {}).items():
            if isinstance(v, str):
                items = [x.strip() for x in re.split(r"[,\s;]+", v) if x.strip()]
            elif isinstance(v, (list, tuple, set)):
                items = [str(x).strip() for x in v if str(x).strip()]
            else:
                items = [str(v).strip()]

            normed = set(i.lower() for i in items)
            sets[str(k)] = normed
            for orig in items:
                case_map.setdefault(orig.lower(), orig)

        if not sets:
            return JSONResponse(status_code=400, content={"error": "No sets provided"})

        # draw venn
        plt.figure(figsize=(6, 6))
        venn(sets)
        buf = io.BytesIO()
        plt.savefig(buf, bbox_inches="tight", format="png", transparent=True, dpi=150)
        plt.close()
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode("ascii")
        data_uri = f"data:image/png;base64,{img_b64}"

        # compute intersections
        membership = {}
        for label, s in sets.items():
            for elem in s:
                membership.setdefault(elem, set()).add(label)

        all_labels = list(sets.keys())
        n = len(all_labels)
        combo_map = {}

        for r in range(2, n + 1):
            for combo in combinations(all_labels, r):
                combo_set = set(combo)
                key = " and ".join(combo)
                items = []
                for elem_lower, labels_for_elem in membership.items():
                    if labels_for_elem.issuperset(combo_set):
                        items.append(case_map.get(elem_lower, elem_lower))
                if items:
                    combo_map[key] = sorted(set(items), key=lambda s: s.lower())

        return {"image": data_uri, "intersections": combo_map}

    except Exception as e:
        logger.exception("Error generating venn: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
