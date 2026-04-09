"""
Smart Folder Organiser — Flask Edition
New features over Tkinter: SSE streaming, Duplicate Detector,
File Watcher, Bulk Rename Engine, Undo via Manifest, Stats API,
Zip-before-move, Min/Max size filters, Extension whitelist/blacklist.
"""

import os, re, shutil, hashlib, json, threading, time, uuid, zipfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from queue import Queue, Empty

from flask import Flask, render_template, request, jsonify, Response, stream_with_context

# ── optional watchdog (gracefully degraded) ───────────────────────────────
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False

app = Flask(__name__)
app.secret_key = "folder-organiser-2025"

# ══════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════
CATEGORIES = {
    "Images":      [".jpg",".jpeg",".png",".gif",".bmp",".svg",".webp",
                    ".ico",".tiff",".tif",".heic",".raw",".psd",".ai"],
    "Videos":      [".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",
                    ".m4v",".mpeg",".mpg",".3gp",".ts",".vob"],
    "Audio":       [".mp3",".wav",".aac",".flac",".ogg",".m4a",".wma",
                    ".opus",".aiff",".mid",".midi"],
    "Documents":   [".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",
                    ".odt",".ods",".odp",".txt",".rtf",".csv",".epub",
                    ".md",".pages",".numbers",".key"],
    "Code":        [".py",".js",".ts",".html",".css",".java",".c",".cpp",
                    ".cs",".php",".rb",".go",".rs",".swift",".kt",".sh",
                    ".bat",".sql",".json",".xml",".yaml",".yml",".toml",
                    ".ini",".cfg",".jsx",".tsx",".vue"],
    "Archives":    [".zip",".rar",".7z",".tar",".gz",".bz2",".xz",
                    ".iso",".dmg",".pkg",".tgz"],
    "Executables": [".exe",".msi",".apk",".app",".deb",".rpm",".bin"],
    "Fonts":       [".ttf",".otf",".woff",".woff2",".eot"],
    "Data":        [".db",".sqlite",".sql",".bak",".dat",".log",".csv",
                    ".parquet",".feather"],
    "3D_CAD":      [".stl",".obj",".fbx",".blend",".dae",".3ds",".max"],
    "Misc":        [],
}

SIZE_BUCKETS = [
    ("Tiny",   "< 10 KB",    0,              10*1024),
    ("Small",  "10–100 KB",  10*1024,        100*1024),
    ("Medium", "100KB–1MB",  100*1024,       1*1024**2),
    ("Large",  "1–100 MB",   1*1024**2,      100*1024**2),
    ("Huge",   "> 100 MB",   100*1024**2,    float("inf")),
]

MANIFEST_FILE = Path.home() / ".folder_organiser_manifest.json"

# ══════════════════════════════════════════════════════════════════════════
#  IN-MEMORY JOB STORE
# ══════════════════════════════════════════════════════════════════════════
jobs: dict[str, dict] = {}       # job_id → {queue, status, stats}
watchers: dict[str, object] = {} # path → Observer

# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════
def get_category(ext: str) -> str:
    ext = ext.lower()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "Misc"

def get_bucket(size: int) -> str:
    for name, label, lo, hi in SIZE_BUCKETS:
        if lo <= size < hi:
            return name
    return "Huge"

def fmt_size(b: int) -> str:
    for u in ("B","KB","MB","GB","TB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"

def file_hash(path: Path, algo="md5") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_name(s: str) -> str:
    return re.sub(r"[^\w\s\-().]", "", s).strip().replace(" ","_") or "Other"

def load_manifest() -> list:
    if MANIFEST_FILE.exists():
        try: return json.loads(MANIFEST_FILE.read_text())
        except: pass
    return []

def save_manifest(records: list):
    MANIFEST_FILE.write_text(json.dumps(records, indent=2))

def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

# ══════════════════════════════════════════════════════════════════════════
#  CORE ORGANISE WORKER
# ══════════════════════════════════════════════════════════════════════════
def organise_worker(job_id: str, cfg: dict):
    q    = jobs[job_id]["queue"]
    src  = Path(cfg["source"])
    dst  = Path(cfg["dest"])
    move = cfg.get("move", True)
    dry  = cfg.get("dry_run", False)
    compress   = cfg.get("compress", False)
    min_size   = cfg.get("min_size", 0)
    max_size   = cfg.get("max_size", float("inf"))
    whitelist  = [e.lower() for e in cfg.get("whitelist", []) if e]
    blacklist  = [e.lower() for e in cfg.get("blacklist", []) if e]
    dedupe     = cfg.get("dedupe_on_copy", False)

    def emit(msg, level="info", progress=None):
        payload = {"msg": msg, "level": level, "ts": datetime.now().strftime("%H:%M:%S")}
        if progress is not None: payload["progress"] = progress
        q.put(payload)

    emit(f"{'[DRY RUN] ' if dry else ''}Job {job_id} started", "system")
    emit(f"Source  : {src}", "system")
    emit(f"Dest    : {dst}", "system")
    emit(f"Mode    : {'MOVE' if move else 'COPY'} | Compress={compress}", "system")
    emit("─"*54, "sep")

    try:
        all_files = [f for f in src.rglob("*") if f.is_file()
                     and not f.name.startswith(".")]
    except Exception as e:
        emit(f"Cannot read source: {e}", "error")
        jobs[job_id]["status"] = "error"
        q.put({"done": True})
        return

    # Apply size filter
    files = []
    for f in all_files:
        try:
            sz = f.stat().st_size
            if sz < min_size or sz > max_size: continue
            ext = f.suffix.lower()
            if whitelist and ext not in whitelist: continue
            if blacklist and ext in blacklist: continue
            files.append(f)
        except: pass

    total = len(files)
    emit(f"Matched {total} file(s) after filters", "info")

    manifest = []
    seen_hashes = set()
    ok = err = skipped = 0

    for i, file in enumerate(files, 1):
        try:
            sz   = file.stat().st_size
            cat  = get_category(file.suffix)
            buck = get_bucket(sz)
            tdir = dst / safe_name(cat) / safe_name(buck)
            name = file.name

            # Dedupe check
            if dedupe:
                fhash = file_hash(file)
                if fhash in seen_hashes:
                    emit(f"  SKIP (dup)  {name}", "warn")
                    skipped += 1
                    q.put({"progress": int(i/total*100)})
                    continue
                seen_hashes.add(fhash)

            # Compress option
            if compress and not dry:
                tdir.mkdir(parents=True, exist_ok=True)
                zpath = tdir / (file.stem + ".zip")
                counter = 1
                while zpath.exists():
                    zpath = tdir / f"{file.stem}_{counter}.zip"
                    counter += 1
                with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(file, file.name)
                manifest.append({"src": str(file), "dst": str(zpath), "op": "compress"})
                if move: file.unlink()
                emit(f"  ZIP  {name}  →  {cat}/{buck}/", "ok")
            else:
                target = tdir / name
                c = 1
                while target.exists():
                    target = tdir / f"{file.stem}_{c}{file.suffix}"
                    c += 1
                if not dry:
                    tdir.mkdir(parents=True, exist_ok=True)
                    if move:
                        shutil.move(str(file), str(target))
                        manifest.append({"src": str(file), "dst": str(target), "op": "move"})
                    else:
                        shutil.copy2(str(file), str(target))
                        manifest.append({"src": str(file), "dst": str(target), "op": "copy"})
                sym = "→" if move else "⎘"
                emit(f"  {sym}  {name}  [{fmt_size(sz)}]  →  {cat}/{buck}/", "ok")

            ok += 1
        except Exception as e:
            emit(f"  ✗ ERROR  {file.name}: {e}", "error")
            err += 1

        q.put({"progress": int(i/total*100)})

    if not dry:
        prev = load_manifest()
        save_manifest(prev + [{"job_id": job_id,
                               "ts": datetime.now().isoformat(),
                               "records": manifest}])

    emit("─"*54, "sep")
    emit(f"✅ Processed : {ok}", "ok")
    emit(f"⚠️  Errors    : {err}", "warn" if err else "ok")
    emit(f"⏭️  Skipped   : {skipped}", "info")
    jobs[job_id]["status"] = "done"
    jobs[job_id]["stats"]  = {"ok": ok, "err": err, "skipped": skipped, "total": total}
    q.put({"done": True, "progress": 100})

# ══════════════════════════════════════════════════════════════════════════
#  WATCHDOG HANDLER
# ══════════════════════════════════════════════════════════════════════════
class AutoOrganiseHandler:
    def __init__(self, cfg): self.cfg = cfg; self.pending = set()
    def on_created(self, event):
        if not event.is_directory:
            time.sleep(1)
            cfg = dict(self.cfg)
            cfg["source"] = str(Path(event.src_path).parent)
            job_id = str(uuid.uuid4())[:8]
            jobs[job_id] = {"queue": Queue(), "status": "running", "stats": {}}
            threading.Thread(target=organise_worker, args=(job_id, cfg), daemon=True).start()

if WATCHDOG_OK:
    class WatchHandler(FileSystemEventHandler, AutoOrganiseHandler):
        def __init__(self, cfg): AutoOrganiseHandler.__init__(self, cfg)

# ══════════════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html", watchdog_ok=WATCHDOG_OK)


@app.route("/api/scan", methods=["POST"])
def scan():
    src = request.json.get("source","").strip()
    p = Path(src)
    if not p.is_dir():
        return jsonify({"error": "Invalid directory"}), 400

    cats = defaultdict(lambda: defaultdict(int))
    buckets = defaultdict(int)
    total_size = 0
    exts = defaultdict(int)
    count = 0

    for f in p.iterdir():
        if not f.is_file() or f.name.startswith("."): continue
        try:
            sz  = f.stat().st_size
            cat = get_category(f.suffix)
            bk  = get_bucket(sz)
            cats[cat][bk] += 1
            buckets[bk]   += 1
            total_size     += sz
            exts[f.suffix.lower() or "(none)"] += 1
            count += 1
        except: pass

    top_exts = sorted(exts.items(), key=lambda x:-x[1])[:10]
    return jsonify({
        "total": count,
        "total_size": fmt_size(total_size),
        "total_size_bytes": total_size,
        "categories": {c: dict(b) for c,b in cats.items()},
        "buckets": dict(buckets),
        "top_exts": top_exts,
    })


@app.route("/api/organise", methods=["POST"])
def start_organise():
    cfg = request.json
    if not cfg.get("source") or not cfg.get("dest"):
        return jsonify({"error": "source and dest required"}), 400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"queue": Queue(), "status": "running", "stats": {}}
    threading.Thread(target=organise_worker, args=(job_id, cfg), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/stream/<job_id>")
def stream(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Unknown job"}), 404
    q = jobs[job_id]["queue"]
    def generate():
        yield sse({"msg": f"Connected to job {job_id}", "level": "system"})
        while True:
            try:
                item = q.get(timeout=30)
                yield sse(item)
                if item.get("done"):
                    break
            except Empty:
                yield sse({"heartbeat": True})
    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@app.route("/api/duplicates", methods=["POST"])
def find_duplicates():
    src     = request.json.get("source","").strip()
    algo    = request.json.get("algo","md5")
    recurse = request.json.get("recurse", False)
    p = Path(src)
    if not p.is_dir():
        return jsonify({"error": "Invalid directory"}), 400

    hashes = defaultdict(list)
    glob = p.rglob("*") if recurse else p.iterdir()
    for f in glob:
        if f.is_file() and not f.name.startswith("."):
            try:
                h = file_hash(f, algo)
                hashes[h].append({
                    "path": str(f),
                    "name": f.name,
                    "size": fmt_size(f.stat().st_size),
                    "size_bytes": f.stat().st_size,
                })
            except: pass

    groups = [v for v in hashes.values() if len(v) > 1]
    wasted = sum(g[0]["size_bytes"] * (len(g)-1) for g in groups)
    return jsonify({
        "groups": groups,
        "count": sum(len(g)-1 for g in groups),
        "wasted": fmt_size(wasted),
    })


@app.route("/api/duplicates/delete", methods=["POST"])
def delete_duplicates():
    paths = request.json.get("paths", [])
    deleted = []
    errors  = []
    for p in paths:
        try:
            Path(p).unlink()
            deleted.append(p)
        except Exception as e:
            errors.append({"path": p, "error": str(e)})
    return jsonify({"deleted": len(deleted), "errors": errors})


@app.route("/api/rename", methods=["POST"])
def bulk_rename():
    src      = request.json.get("source","").strip()
    pattern  = request.json.get("pattern","")    # regex match
    replace  = request.json.get("replace","")    # replacement string
    prefix   = request.json.get("prefix","")
    suffix_s = request.json.get("suffix","")
    numbering= request.json.get("numbering", False)
    dry      = request.json.get("dry_run", True)
    case_op  = request.json.get("case","none")  # upper/lower/title/none
    ext_filt = request.json.get("ext_filter","").lower().strip()

    p = Path(src)
    if not p.is_dir(): return jsonify({"error":"Invalid directory"}),400

    files = sorted([f for f in p.iterdir()
                    if f.is_file() and not f.name.startswith(".")])
    if ext_filt:
        files = [f for f in files if f.suffix.lower() == ext_filt]

    results = []
    for i, f in enumerate(files, 1):
        stem = f.stem
        ext  = f.suffix

        if pattern:
            try: stem = re.sub(pattern, replace, stem)
            except: pass

        if case_op == "upper":   stem = stem.upper()
        elif case_op == "lower": stem = stem.lower()
        elif case_op == "title": stem = stem.title()

        new_name = f"{prefix}{stem}{suffix_s}"
        if numbering: new_name = f"{new_name}_{i:04d}"
        new_name += ext

        new_path = p / new_name
        results.append({"old": f.name, "new": new_name, "changed": f.name != new_name})
        if not dry and f.name != new_name:
            try: f.rename(new_path)
            except Exception as e: results[-1]["error"] = str(e)

    changed = sum(1 for r in results if r["changed"])
    return jsonify({"results": results, "changed": changed, "dry_run": dry})


@app.route("/api/undo", methods=["POST"])
def undo():
    manifests = load_manifest()
    if not manifests: return jsonify({"error":"No operations to undo"}),400

    last = manifests[-1]
    records = last.get("records", [])
    restored = errors = 0

    for rec in reversed(records):
        try:
            op  = rec["op"]
            src = Path(rec["src"])
            dst = Path(rec["dst"])
            if op in ("move","copy") and dst.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                if op == "move":
                    shutil.move(str(dst), str(src))
                    restored += 1
                elif op == "copy":
                    dst.unlink()
                    restored += 1
            elif op == "compress" and dst.exists():
                with zipfile.ZipFile(dst) as zf:
                    zf.extractall(src.parent)
                dst.unlink()
                restored += 1
        except Exception as e:
            errors += 1

    save_manifest(manifests[:-1])
    return jsonify({
        "restored": restored,
        "errors":   errors,
        "job_id":   last.get("job_id"),
        "ts":       last.get("ts"),
    })


@app.route("/api/undo/history", methods=["GET"])
def undo_history():
    manifests = load_manifest()
    summary = []
    for m in reversed(manifests[-10:]):
        records = m.get("records",[])
        summary.append({
            "job_id":  m.get("job_id"),
            "ts":      m.get("ts"),
            "count":   len(records),
        })
    return jsonify({"history": summary})


@app.route("/api/watch/start", methods=["POST"])
def watch_start():
    if not WATCHDOG_OK:
        return jsonify({"error":"watchdog not installed. Run: pip install watchdog"}),400
    cfg = request.json
    src = cfg.get("source","").strip()
    if not Path(src).is_dir():
        return jsonify({"error":"Invalid directory"}),400
    if src in watchers:
        return jsonify({"error":"Already watching"}),400

    handler  = WatchHandler(cfg)
    observer = Observer()
    observer.schedule(handler, src, recursive=False)
    observer.start()
    watchers[src] = observer
    return jsonify({"watching": src})


@app.route("/api/watch/stop", methods=["POST"])
def watch_stop():
    src = request.json.get("source","").strip()
    obs = watchers.pop(src, None)
    if obs:
        obs.stop(); obs.join()
        return jsonify({"stopped": src})
    return jsonify({"error":"Not watching"}),400


@app.route("/api/watch/list", methods=["GET"])
def watch_list():
    return jsonify({"watching": list(watchers.keys())})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def job_status(job_id):
    j = jobs.get(job_id)
    if not j: return jsonify({"error":"Not found"}),404
    return jsonify({"status": j["status"], "stats": j["stats"]})


if __name__ == "__main__":
    app.run(debug=True, port=5050, threaded=True)