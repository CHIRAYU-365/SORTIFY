import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
#  FILE CATEGORY MAP
# ─────────────────────────────────────────────
CATEGORIES = {
    "🖼️ Images":     [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg",
                      ".webp", ".ico", ".tiff", ".tif", ".heic", ".raw"],
    "🎬 Videos":     [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
                      ".webm", ".m4v", ".mpeg", ".mpg", ".3gp"],
    "🎵 Audio":      [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a",
                      ".wma", ".opus", ".aiff"],
    "📄 Documents":  [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
                      ".pptx", ".odt", ".ods", ".odp", ".txt", ".rtf",
                      ".csv", ".epub", ".pages", ".numbers", ".key"],
    "💻 Code":       [".py", ".js", ".ts", ".html", ".css", ".java",
                      ".c", ".cpp", ".cs", ".php", ".rb", ".go", ".rs",
                      ".swift", ".kt", ".sh", ".bat", ".sql", ".json",
                      ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg"],
    "🗜️ Archives":   [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2",
                      ".xz", ".iso", ".dmg", ".pkg"],
    "🖥️ Executables":[".exe", ".msi", ".apk", ".app", ".deb", ".rpm"],
    "🔤 Fonts":      [".ttf", ".otf", ".woff", ".woff2", ".eot"],
    "🗄️ Data":       [".db", ".sqlite", ".sql", ".bak", ".dat", ".log"],
    "📦 Misc":       [],   # catch-all
}

# ─────────────────────────────────────────────
#  SIZE BUCKETS
# ─────────────────────────────────────────────
SIZE_BUCKETS = [
    ("🔹 Tiny   (<10 KB)",    0,             10 * 1024),
    ("🟢 Small  (10–100 KB)", 10 * 1024,     100 * 1024),
    ("🟡 Medium (100 KB–1 MB)",100 * 1024,   1 * 1024 * 1024),
    ("🟠 Large  (1–100 MB)",  1 * 1024 * 1024, 100 * 1024 * 1024),
    ("🔴 Huge   (>100 MB)",   100 * 1024 * 1024, float("inf")),
]

def get_category(ext: str) -> str:
    ext = ext.lower()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "📦 Misc"

def get_size_bucket(size: int) -> str:
    for label, lo, hi in SIZE_BUCKETS:
        if lo <= size < hi:
            return label
    return SIZE_BUCKETS[-1][0]

def safe_folder_name(name: str) -> str:
    """Strip emoji + special chars for actual folder creation."""
    import re
    cleaned = re.sub(r"[^\w\s\-().<>]", "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Other"

# ─────────────────────────────────────────────
#  ORGANISER LOGIC
# ─────────────────────────────────────────────
def organise_folder(source: str, dest: str, move: bool,
                    log_cb, progress_cb, done_cb,
                    dry_run: bool = False):
    source_path = Path(source)
    dest_path   = Path(dest)
    files = [f for f in source_path.iterdir()
             if f.is_file() and not f.name.startswith(".")]

    total   = len(files)
    moved   = 0
    skipped = 0
    errors  = 0
    log_cb(f"{'[DRY RUN] ' if dry_run else ''}Found {total} file(s) in {source_path.name}\n")

    for i, file in enumerate(files, 1):
        try:
            size     = file.stat().st_size
            cat      = get_category(file.suffix)
            bucket   = get_size_bucket(size)
            cat_dir  = safe_folder_name(cat)
            buck_dir = safe_folder_name(bucket)
            target_dir = dest_path / cat_dir / buck_dir
            target     = target_dir / file.name

            # Handle duplicates
            stem = file.stem
            suffix = file.suffix
            counter = 1
            while target.exists():
                target = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
                if move:
                    shutil.move(str(file), str(target))
                else:
                    shutil.copy2(str(file), str(target))

            action = "→" if move else "⎘"
            log_cb(f"  {action} {file.name}  [{file.suffix or 'no ext'}]"
                   f"  {_fmt_size(size)}  →  {cat_dir}/{buck_dir}/\n")
            moved += 1

        except Exception as e:
            log_cb(f"  ✗ ERROR  {file.name}: {e}\n")
            errors += 1
            skipped += 1

        progress_cb(int(i / total * 100))

    summary = (f"\n{'─'*50}\n"
               f"  ✅ Processed : {moved}\n"
               f"  ⚠️  Errors    : {errors}\n"
               f"  📁 Destination: {dest_path}\n"
               f"{'─'*50}\n")
    log_cb(summary)
    done_cb()

def _fmt_size(b: int) -> str:
    for unit in ("B","KB","MB","GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
class FolderOrganiserApp(tk.Tk):
    ACCENT   = "#6C63FF"
    BG       = "#1E1E2E"
    SURFACE  = "#2A2A3E"
    SURFACE2 = "#313145"
    TEXT     = "#CDD6F4"
    SUBTEXT  = "#A6ADC8"
    GREEN    = "#A6E3A1"
    RED      = "#F38BA8"
    YELLOW   = "#F9E2AF"
    BORDER   = "#45475A"

    def __init__(self):
        super().__init__()
        self.title("⚡ Smart Folder Organiser")
        self.geometry("900x680")
        self.minsize(760, 560)
        self.configure(bg=self.BG)
        self._build_style()
        self._build_ui()

    # ── STYLE ────────────────────────────────
    def _build_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",        background=self.BG)
        s.configure("Card.TFrame",   background=self.SURFACE)
        s.configure("TLabel",        background=self.BG,      foreground=self.TEXT, font=("Segoe UI",10))
        s.configure("Card.TLabel",   background=self.SURFACE, foreground=self.TEXT, font=("Segoe UI",10))
        s.configure("Head.TLabel",   background=self.BG,      foreground=self.TEXT, font=("Segoe UI",14,"bold"))
        s.configure("Sub.TLabel",    background=self.BG,      foreground=self.SUBTEXT, font=("Segoe UI",9))
        s.configure("TButton",       font=("Segoe UI",10,"bold"), padding=6)
        s.configure("Accent.TButton",background=self.ACCENT,  foreground="white",   font=("Segoe UI",11,"bold"), padding=8)
        s.map("Accent.TButton",      background=[("active","#574FCC")])
        s.configure("TEntry",        fieldbackground=self.SURFACE2, foreground=self.TEXT,
                    insertcolor=self.TEXT, bordercolor=self.BORDER, padding=6)
        s.configure("TCheckbutton",  background=self.BG, foreground=self.TEXT, font=("Segoe UI",10))
        s.configure("TProgressbar",  troughcolor=self.SURFACE2, background=self.ACCENT, thickness=10)
        s.configure("Treeview",      background=self.SURFACE2, foreground=self.TEXT,
                    fieldbackground=self.SURFACE2, rowheight=22, font=("Segoe UI",9))
        s.configure("Treeview.Heading", background=self.SURFACE, foreground=self.ACCENT,
                    font=("Segoe UI",9,"bold"))
        s.map("Treeview", background=[("selected", self.ACCENT)], foreground=[("selected","white")])

    # ── UI LAYOUT ────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=self.SURFACE, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚡ Smart Folder Organiser", bg=self.SURFACE,
                 fg=self.TEXT, font=("Segoe UI",18,"bold")).pack(side="left", padx=20)
        tk.Label(hdr, text="Sort by type · then by size", bg=self.SURFACE,
                 fg=self.SUBTEXT, font=("Segoe UI",10)).pack(side="left", padx=4)

        # Body
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=18, pady=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(2, weight=1)

        # ── Paths card ────────────────────────
        self._card_paths(body)

        # ── Options card ──────────────────────
        self._card_options(body)

        # ── Log ───────────────────────────────
        self._card_log(body)

        # ── Preview tree ──────────────────────
        self._card_preview(body)

        # ── Progress + buttons ────────────────
        self._card_footer(body)

    def _card_paths(self, parent):
        card = tk.LabelFrame(parent, text=" 📂 Paths ", bg=self.SURFACE,
                             fg=self.ACCENT, font=("Segoe UI",10,"bold"),
                             bd=1, relief="flat", pady=8, padx=10)
        card.grid(row=0, column=0, sticky="nsew", padx=(0,8), pady=(0,8))
        card.columnconfigure(1, weight=1)

        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()

        for row, (label, var, cmd) in enumerate([
            ("Source Folder:", self.src_var, self._browse_src),
            ("Destination:  ", self.dst_var, self._browse_dst),
        ]):
            tk.Label(card, text=label, bg=self.SURFACE, fg=self.SUBTEXT,
                     font=("Segoe UI",9)).grid(row=row, column=0, sticky="w", pady=4)
            e = tk.Entry(card, textvariable=var, bg=self.SURFACE2, fg=self.TEXT,
                         insertbackground=self.TEXT, relief="flat", font=("Segoe UI",10),
                         bd=4)
            e.grid(row=row, column=1, sticky="ew", padx=6)
            tk.Button(card, text="Browse", bg=self.ACCENT, fg="white",
                      relief="flat", font=("Segoe UI",9,"bold"),
                      activebackground="#574FCC", activeforeground="white",
                      command=cmd, cursor="hand2").grid(row=row, column=2, padx=(0,2))

    def _card_options(self, parent):
        card = tk.LabelFrame(parent, text=" ⚙️ Options ", bg=self.SURFACE,
                             fg=self.ACCENT, font=("Segoe UI",10,"bold"),
                             bd=1, relief="flat", pady=8, padx=10)
        card.grid(row=0, column=1, sticky="nsew", pady=(0,8))

        self.move_var    = tk.BooleanVar(value=True)
        self.dry_var     = tk.BooleanVar(value=False)
        self.same_dst    = tk.BooleanVar(value=False)

        for text, var in [
            ("Move files (uncheck = Copy)", self.move_var),
            ("Dry Run (preview only)",      self.dry_var),
            ("Organise in-place (src=dst)", self.same_dst),
        ]:
            cb = tk.Checkbutton(card, text=text, variable=var, bg=self.SURFACE,
                                fg=self.TEXT, selectcolor=self.SURFACE2,
                                activebackground=self.SURFACE, activeforeground=self.TEXT,
                                font=("Segoe UI",10), cursor="hand2",
                                command=self._on_inplace if var is self.same_dst else None)
            cb.pack(anchor="w", pady=3)

        # Legend
        sep = tk.Frame(card, bg=self.BORDER, height=1)
        sep.pack(fill="x", pady=6)
        tk.Label(card, text="Size buckets:", bg=self.SURFACE,
                 fg=self.SUBTEXT, font=("Segoe UI",8,"bold")).pack(anchor="w")
        for label, lo, hi in SIZE_BUCKETS:
            txt = label.split("(")[1].rstrip(")")
            tk.Label(card, text=f"  {label.split()[0]} {txt}",
                     bg=self.SURFACE, fg=self.SUBTEXT,
                     font=("Courier",8)).pack(anchor="w")

    def _card_log(self, parent):
        card = tk.LabelFrame(parent, text=" 📋 Activity Log ", bg=self.SURFACE,
                             fg=self.ACCENT, font=("Segoe UI",10,"bold"),
                             bd=1, relief="flat", pady=6, padx=8)
        card.grid(row=2, column=0, sticky="nsew", padx=(0,8), pady=(0,8))
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        self.log_text = tk.Text(card, bg=self.SURFACE2, fg=self.TEXT,
                                font=("Courier New",9), relief="flat",
                                state="disabled", wrap="none", bd=0,
                                insertbackground=self.TEXT)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(card, command=self.log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_text["yscrollcommand"] = sb.set

        # colour tags
        self.log_text.tag_config("ok",  foreground=self.GREEN)
        self.log_text.tag_config("err", foreground=self.RED)
        self.log_text.tag_config("sep", foreground=self.YELLOW)

        btn_frame = tk.Frame(card, bg=self.SURFACE)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="e", pady=(4,0))
        tk.Button(btn_frame, text="Clear Log", bg=self.SURFACE2, fg=self.SUBTEXT,
                  relief="flat", font=("Segoe UI",8), cursor="hand2",
                  command=self._clear_log).pack(side="right", padx=2)
        tk.Button(btn_frame, text="Save Log", bg=self.SURFACE2, fg=self.SUBTEXT,
                  relief="flat", font=("Segoe UI",8), cursor="hand2",
                  command=self._save_log).pack(side="right", padx=2)

    def _card_preview(self, parent):
        card = tk.LabelFrame(parent, text=" 🗂️ Expected Structure ", bg=self.SURFACE,
                             fg=self.ACCENT, font=("Segoe UI",10,"bold"),
                             bd=1, relief="flat", pady=6, padx=8)
        card.grid(row=2, column=1, sticky="nsew", pady=(0,8))
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(card, show="tree", selectmode="none")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tsb = ttk.Scrollbar(card, command=self.tree.yview)
        tsb.grid(row=0, column=1, sticky="ns")
        self.tree["yscrollcommand"] = tsb.set

        tk.Button(card, text="↻ Refresh Preview", bg=self.ACCENT, fg="white",
                  relief="flat", font=("Segoe UI",9,"bold"), cursor="hand2",
                  activebackground="#574FCC", activeforeground="white",
                  command=self._refresh_preview).grid(row=1, column=0,
                  columnspan=2, sticky="e", pady=(4,0))

    def _card_footer(self, parent):
        foot = tk.Frame(parent, bg=self.BG)
        foot.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0,4))
        foot.columnconfigure(1, weight=1)

        self.status_lbl = tk.Label(foot, text="Ready", bg=self.BG,
                                   fg=self.SUBTEXT, font=("Segoe UI",9))
        self.status_lbl.grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(foot, mode="determinate",
                                        style="TProgressbar", length=200)
        self.progress.grid(row=0, column=1, sticky="ew", padx=10)

        btn_row = tk.Frame(foot, bg=self.BG)
        btn_row.grid(row=0, column=2, sticky="e")

        self.run_btn = tk.Button(btn_row, text="▶  Run Organiser",
                                 bg=self.ACCENT, fg="white",
                                 relief="flat", font=("Segoe UI",11,"bold"),
                                 activebackground="#574FCC", activeforeground="white",
                                 padx=16, pady=8, cursor="hand2",
                                 command=self._run)
        self.run_btn.pack(side="right", padx=(6,0))

        tk.Button(btn_row, text="✕ Quit", bg=self.SURFACE2, fg=self.TEXT,
                  relief="flat", font=("Segoe UI",10), cursor="hand2",
                  activebackground=self.RED, activeforeground="white",
                  padx=10, pady=8, command=self.quit).pack(side="right")

    # ── ACTIONS ──────────────────────────────
    def _browse_src(self):
        d = filedialog.askdirectory(title="Select Source Folder")
        if d:
            self.src_var.set(d)
            if not self.dst_var.get() or self.same_dst.get():
                self.dst_var.set(d)
            self._refresh_preview()

    def _browse_dst(self):
        d = filedialog.askdirectory(title="Select Destination Folder")
        if d:
            self.dst_var.set(d)

    def _on_inplace(self):
        if self.same_dst.get():
            self.dst_var.set(self.src_var.get())

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        tag = "err" if "ERROR" in msg or "✗" in msg else \
              "sep" if "─" in msg or "✅" in msg or "⚠️" in msg else "ok"
        self.log_text.insert("end", msg, tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text File","*.txt")],
            initialfile=f"organiser_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        if path:
            content = self.log_text.get("1.0", "end")
            Path(path).write_text(content, encoding="utf-8")
            messagebox.showinfo("Saved", f"Log saved to:\n{path}")

    def _set_progress(self, val: int):
        self.progress["value"] = val
        self.status_lbl.config(text=f"Processing… {val}%")
        self.update_idletasks()

    def _done(self):
        self.run_btn.config(state="normal")
        self.status_lbl.config(text="✅ Done!")
        self.progress["value"] = 100

    def _refresh_preview(self):
        src = self.src_var.get()
        self.tree.delete(*self.tree.get_children())
        if not src or not Path(src).is_dir():
            self.tree.insert("", "end", text="← Select a source folder")
            return

        files = [f for f in Path(src).iterdir()
                 if f.is_file() and not f.name.startswith(".")]
        if not files:
            self.tree.insert("", "end", text="No files found")
            return

        structure: dict[str, dict[str, list[str]]] = {}
        for f in files:
            cat    = get_category(f.suffix)
            bucket = get_size_bucket(f.stat().st_size)
            structure.setdefault(cat, {}).setdefault(bucket, []).append(f.name)

        root_node = self.tree.insert("", "end",
                                     text=f"📁 {Path(src).name}  ({len(files)} files)",
                                     open=True)
        for cat, buckets in sorted(structure.items()):
            cat_count = sum(len(v) for v in buckets.values())
            cat_node  = self.tree.insert(root_node, "end",
                                         text=f"{cat}  ({cat_count})",
                                         open=True)
            for bucket in [b[0] for b in SIZE_BUCKETS]:
                if bucket in buckets:
                    flist = buckets[bucket]
                    b_node = self.tree.insert(cat_node, "end",
                                              text=f"{bucket.split()[0]} {bucket.split('(')[1].rstrip(')')}  ({len(flist)})",
                                              open=False)
                    for fname in flist[:12]:
                        self.tree.insert(b_node, "end", text=f"  {fname}")
                    if len(flist) > 12:
                        self.tree.insert(b_node, "end",
                                         text=f"  … and {len(flist)-12} more")

    def _run(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()

        if not src or not Path(src).is_dir():
            messagebox.showerror("Error", "Please select a valid source folder.")
            return
        if not dst:
            messagebox.showerror("Error", "Please select a destination folder.")
            return

        dry = self.dry_var.get()
        move = self.move_var.get()

        if not dry and move and src == dst:
            if not messagebox.askyesno(
                    "Confirm In-Place",
                    "Source and destination are the same.\n"
                    "Files will be moved within the same folder.\nContinue?"):
                return

        self._clear_log()
        self.run_btn.config(state="disabled")
        self.progress["value"] = 0
        self.status_lbl.config(text="Starting…")

        thread = threading.Thread(
            target=organise_folder,
            args=(src, dst, move,
                  lambda m: self.after(0, self._log, m),
                  lambda v: self.after(0, self._set_progress, v),
                  lambda:   self.after(0, self._done),
                  dry),
            daemon=True
        )
        thread.start()


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = FolderOrganiserApp()
    app.mainloop()