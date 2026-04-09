# ⚡ SORTIFY — Flask Folder Organiser

A web-based, real-time folder organisation tool built with Flask.
Additive successor to the Tkinter desktop app.

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
python app.py

# 3. Open browser
http://localhost:5050
```

---

## ✨ New Features (Flask Edition vs Tkinter)

| Feature | Tkinter | Flask |
|---|---|---|
| Real-time log streaming | polling | **SSE (push)** |
| Duplicate Detector | ✗ | **✓ MD5 / SHA-256** |
| File Watcher | ✗ | **✓ watchdog** |
| Bulk Rename Engine | ✗ | **✓ regex + prefix/suffix/case** |
| Undo via Manifest | ✗ | **✓ full history** |
| ZIP Compression | ✗ | **✓ per job** |
| Min/Max size filters | ✗ | **✓** |
| Extension whitelist/blacklist | ✗ | **✓** |
| Skip duplicates on copy | ✗ | **✓** |
| Stats dashboard | basic | **✓ bar charts** |
| Recursive source scan | ✗ | **✓** |
| 3D/CAD category | ✗ | **✓** |

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/scan` | Scan a folder for stats |
| POST | `/api/organise` | Start an organise job |
| GET  | `/api/stream/<job_id>` | SSE log stream |
| GET  | `/api/jobs/<job_id>` | Job status |
| POST | `/api/duplicates` | Find duplicate files |
| POST | `/api/duplicates/delete` | Delete selected duplicates |
| POST | `/api/rename` | Bulk rename (dry or live) |
| POST | `/api/undo` | Undo last operation |
| GET  | `/api/undo/history` | Operation history |
| POST | `/api/watch/start` | Start folder watcher |
| POST | `/api/watch/stop` | Stop folder watcher |
| GET  | `/api/watch/list` | List active watchers |

---

## 📁 Folder Structure Output

```
destination/
├── Images/
│   ├── Tiny/        # < 10 KB
│   ├── Small/       # 10–100 KB
│   ├── Medium/      # 100 KB–1 MB
│   ├── Large/       # 1–100 MB
│   └── Huge/        # > 100 MB
├── Videos/
├── Audio/
├── Documents/
├── Code/
├── Archives/
├── Executables/
├── Fonts/
├── Data/
├── 3D_CAD/
└── Misc/
```

---

## 🗂 Manifest & Undo

Every non-dry-run job writes to `~/.folder_organiser_manifest.json`.
The Undo tab reads this to reverse operations (move-back or unzip).