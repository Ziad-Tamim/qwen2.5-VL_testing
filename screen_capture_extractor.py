import base64
import csv
import io
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple, List

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont

from PIL import Image, ImageGrab, ImageTk


@dataclass
class ExtractionResult:
    user_name: Optional[str] = None
    follower_count: Optional[str] = None
    following_count: Optional[str] = None
    posts_count: Optional[str] = None
    summary: Optional[str] = None


def ensure_parent_dir(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def append_row_to_csv(csv_path: str, row: Dict[str, str]) -> None:
    ensure_parent_dir(csv_path)
    exists = os.path.exists(csv_path)
    fieldnames = list(row.keys())
    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def remove_last_row_from_csv(csv_path: str) -> bool:
    """Remove the last data row from the CSV (keep header). Returns True if a row was removed."""
    if not os.path.isfile(csv_path):
        return False
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    if not rows:
        return False
    rows = rows[:-1]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return True


def sync_header_and_append(csv_path: str, row: Dict[str, str]) -> None:
    """Ensure CSV header matches union of existing columns and the row keys, then append the row.

    If headers differ, rewrite the CSV with the expanded header and existing rows padded with blanks.
    """
    ensure_parent_dir(csv_path)
    if not os.path.isfile(csv_path):
        append_row_to_csv(csv_path, row)
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_fields = reader.fieldnames or []
        rows = list(reader)

    # Union of old headers and new row keys, preserving order
    new_fields = list(old_fields)
    for k in row.keys():
        if k not in new_fields:
            new_fields.append(k)

    if new_fields == old_fields:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=new_fields)
            writer.writerow({k: row.get(k, "") for k in new_fields})
        return

    # Rewrite with expanded header
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in new_fields})
        writer.writerow({k: row.get(k, "") for k in new_fields})


def sync_header_and_append_many(csv_path: str, rows: List[Dict[str, str]]) -> None:
    """Like sync_header_and_append but for multiple rows in one shot."""
    ensure_parent_dir(csv_path)
    if not os.path.isfile(csv_path):
        if not rows:
            return
        fieldnames = list({k for r in rows for k in r.keys()})
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in fieldnames})
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_fields = reader.fieldnames or []
        existing_rows = list(reader)

    new_fields_set = set(old_fields)
    for r in rows:
        new_fields_set.update(r.keys())
    new_fields = list(old_fields) + [k for k in new_fields_set if k not in old_fields]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        for r in existing_rows:
            writer.writerow({k: r.get(k, "") for k in new_fields})
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in new_fields})


def parse_json_lenient(text: str) -> Dict:
    """Extract the first JSON object from text; fallback to empty dict."""
    try:
        return json.loads(text)
    except Exception:
        # Try to find braces substring
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return {}
        return {}


def image_to_base64_jpeg(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class RegionSelector(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-alpha", 0.2)
        self.attributes("-topmost", True)
        self.state("zoomed")  # Fullscreen on Windows

        self.canvas = tk.Canvas(self, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.result_bbox: Optional[Tuple[int, int, int, int]] = None

        self.bind("<Escape>", lambda e: self._cancel())
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.deiconify()

    def _on_press(self, event):
        self.start_x, self.start_y = event.x_root, event.y_root
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = None

    def _on_drag(self, event):
        if self.start_x is None or self.start_y is None:
            return
        x0, y0 = self.start_x, self.start_y
        x1, y1 = event.x_root, event.y_root
        self._draw_rect_on_canvas(x0, y0, x1, y1)

    def _on_release(self, event):
        if self.start_x is None or self.start_y is None:
            return
        x0, y0 = self.start_x, self.start_y
        x1, y1 = event.x_root, event.y_root
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        self.result_bbox = (left, top, right, bottom)
        self.destroy()

    def _draw_rect_on_canvas(self, x0, y0, x1, y1):
        self.canvas.delete(self.rect) if self.rect else None
        self.rect = self.canvas.create_rectangle(
            x0, y0, x1, y1, outline="red", width=2
        )

    def _cancel(self):
        self.result_bbox = None
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Screen Capture Extractor - Qwen2.5-VL (Ollama)")
        self.geometry("1100x720")
        self.configure(bg="#0f0f14")

        self._setup_style()

        # State
        self.captured_image: Optional[Image.Image] = None
        self.captured_thumbnail: Optional[ImageTk.PhotoImage] = None
        self.last_bbox: Optional[Tuple[int, int, int, int]] = None

        # Controls
        self._build_controls()

    def _build_controls(self):
        purple = "#8b5cf6"

        # Header + model badge (top-right)
        header = ttk.Label(self, text="Screen Capture Extractor", style="Header.TLabel")
        header.grid(row=0, column=0, sticky="w", padx=18, pady=(14, 8))
        # Hidden model entry persisted for config
        self.model_entry = ttk.Entry(self)
        self.model_entry.insert(0, "qwen2.5vl:3b")
        self.model_badge_var = tk.StringVar(value=self.model_entry.get())
        model_badge = ttk.Label(self, textvariable=self.model_badge_var, style="Badge.TLabel")
        model_badge.grid(row=0, column=1, sticky="e", padx=18, pady=(16, 8))

        # Main single-column content area (prompt, data, log stacked)
        left = tk.Frame(self, bg="#0f0f14")
        left.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=18, pady=(0, 10))
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # Left: Promte card
        prompt_card = tk.Frame(left, bg="#15151c", highlightbackground=purple, highlightthickness=2, bd=0)
        prompt_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        ttk.Label(prompt_card, text="Promte", style="Caption.TLabel").pack(anchor="w", padx=10, pady=(8, 4))
        self.prompt_text = tk.Text(prompt_card, height=5, wrap="word", bg="#11131a", fg="#eaeaf0", insertbackground="#eaeaf0", bd=0, highlightthickness=0)
        self.prompt_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Hidden server entry and CSV path with defaults
        self.server_entry = ttk.Entry(self)
        self.server_entry.insert(0, "http://localhost:11434")
        self.csv_entry = ttk.Entry(self)
        self.csv_entry.insert(0, os.path.abspath("captures.csv"))

        # No image preview per request
        left.grid_rowconfigure(0, weight=0)
        left.grid_columnconfigure(0, weight=1)

        # Data table under prompt
        data_card = tk.Frame(left, bg="#15151c", highlightbackground=purple, highlightthickness=2, bd=0)
        data_card.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        ttk.Label(data_card, text="data", style="Caption.TLabel").pack(anchor="w", padx=10, pady=(8, 4))
        # Start with no columns; will be configured after first save or when CSV exists
        self.table = ttk.Treeview(data_card, columns=(), show="headings", style="Data.Treeview")
        self.table.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Log under data
        log_card = tk.Frame(left, bg="#15151c", highlightbackground=purple, highlightthickness=2, bd=0)
        log_card.grid(row=2, column=0, sticky="nsew")
        ttk.Label(log_card, text="log", style="Caption.TLabel").pack(anchor="w", padx=10, pady=(8, 4))
        self.log_text = tk.Text(log_card, height=8, wrap="word", bg="#11131a", fg="#eaeaf0", insertbackground="#eaeaf0", bd=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left.grid_rowconfigure(1, weight=2)
        left.grid_rowconfigure(2, weight=1)

        # Bottom action row
        bottom = tk.Frame(self, bg="#0f0f14")
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 14))
        # Removed standalone capture and save buttons; keep capture+save and quick save
        ttk.Button(bottom, text="capture+save", style="Accent.TButton", command=self._capture_and_save).pack(side="left", padx=(18, 6))
        ttk.Button(bottom, text="quick save", style="Accent.TButton", command=self._quick_save_last_region).pack(side="left", padx=6)
        ttk.Button(bottom, text="remove last", style="Danger.TButton", command=self._remove_last).pack(side="left", padx=6)
        ttk.Button(bottom, text="Clear", style="Tertiary.TButton", command=self._clear).pack(side="left", padx=6)

        # Load table initially
        self._load_data_table()

    def _browse_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.csv_entry.delete(0, tk.END)
            self.csv_entry.insert(0, path)

    def _capture_region(self):
        # Raise app then hide to avoid capturing the app itself
        self.withdraw()
        self.update()
        time.sleep(0.1)
        selector = RegionSelector(self)
        self.wait_window(selector)
        self.deiconify()
        bbox = selector.result_bbox
        if not bbox:
            self._log("Capture canceled.")
            return
        try:
            img = ImageGrab.grab(bbox=bbox)
            self.captured_image = img
            self.last_bbox = bbox
            w, h = self.captured_image.size
            self._log(f"Captured region: {bbox} (size: {w}x{h})")
        except Exception as e:
            messagebox.showerror("Capture Error", str(e))
            self._log(f"Capture error: {e}")

    def _extract_and_save(self):
        if self.captured_image is None:
            messagebox.showwarning("No Image", "Please capture a region first.")
            return
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("No Prompt", "Please enter a prompt.")
            return
        self._run_save_worker(self.captured_image, prompt)

    def _capture_and_save(self):
        # Trigger region selection then immediately save
        self.withdraw(); self.update(); time.sleep(0.05)
        selector = RegionSelector(self)
        self.wait_window(selector)
        self.deiconify()
        bbox = selector.result_bbox
        if not bbox:
            self._log("Capture canceled.")
            return
        try:
            img = ImageGrab.grab(bbox=bbox)
            self.captured_image = img
            self.last_bbox = bbox
            w, h = self.captured_image.size
            self._log(f"Captured region: {bbox} (size: {w}x{h}); saving...")
            prompt = self.prompt_text.get("1.0", tk.END).strip()
            if not prompt:
                messagebox.showwarning("No Prompt", "Please enter a prompt.")
                return
            self._run_save_worker(self.captured_image, prompt)
        except Exception as e:
            messagebox.showerror("Capture Error", str(e))
            self._log(f"Capture error: {e}")

    def _quick_save_last_region(self):
        # Re-capture the last region and save, without showing selector
        if not self.last_bbox:
            messagebox.showwarning("No Region", "Capture a region once before using quick save.")
            return
        try:
            img = ImageGrab.grab(bbox=self.last_bbox)
            self.captured_image = img
            w, h = self.captured_image.size
            self._log(f"Re-captured last region (size: {w}x{h}); saving...")
            prompt = self.prompt_text.get("1.0", tk.END).strip()
            if not prompt:
                messagebox.showwarning("No Prompt", "Please enter a prompt.")
                return
            self._run_save_worker(self.captured_image, prompt)
        except Exception as e:
            messagebox.showerror("Quick Save Error", str(e))
            self._log(f"Quick save error: {e}")

    def _run_save_worker(self, image: Image.Image, prompt: str):
        csv_path = self.csv_entry.get().strip()
        model = self.model_entry.get().strip() or "qwen2.5vl:3b"
        server_url = self.server_entry.get().strip() or "http://localhost:11434"

        def worker():
            try:
                result = self._run_ollama_extraction(
                    image=image, prompt=prompt, model=model, server_url=server_url
                )
                # Accept either flat dict or structured summary+transactions
                if isinstance(result, dict) and "transactions" in result and "summary" in result:
                    flat_rows: List[Dict[str, str]] = []
                    summary = result.get("summary", {}) or {}
                    txs = result.get("transactions", []) or []
                    for tx in txs:
                        flat = {}
                        # Prefix summary fields for clarity
                        for k, v in summary.items():
                            flat[f"summary_{k}"] = "" if v is None else str(v)
                        for k, v in tx.items():
                            flat[str(k)] = "" if v is None else str(v)
                        flat_rows.append(flat)
                    if flat_rows:
                        sync_header_and_append_many(csv_path, flat_rows)
                    else:
                        # If no transactions, store just one row with summary
                        flat = {f"summary_{k}": ("" if v is None else str(v)) for k, v in summary.items()}
                        sync_header_and_append(csv_path, flat)
                elif isinstance(result, dict):
                    sync_header_and_append(csv_path, result)
                else:
                    sync_header_and_append(csv_path, asdict(result))
                self._log(f"Saved row to: {csv_path}")
                self._load_data_table()
            except Exception as e:
                messagebox.showerror("Extraction Error", str(e))
                self._log(f"Extraction error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _run_ollama_extraction(
        self, image: Image.Image, prompt: str, model: str, server_url: str
    ) -> Dict[str, str]:
        try:
            import ollama
            client = ollama.Client(host=server_url)
        except Exception as exc:
            raise RuntimeError("Please install the 'ollama' package: pip install ollama") from exc

        sys_prompt = (
            "You are an information extraction assistant. Return ONLY compact JSON with keys: "
            "user_name, follower_count, following_count, posts_count, summary. Do not include markdown."
        )

        img_b64 = image_to_base64_jpeg(image)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt, "images": [img_b64]},
            ],
            "options": {"num_predict": 512},
        }

        self._log(f"Calling Ollama: model={model} server={server_url}")
        resp = client.chat(**payload)
        text = resp.get("message", {}).get("content", "")
        self._log(f"Raw model output: {text[:500]}{'...' if len(text)>500 else ''}")

        data = parse_json_lenient(text)
        # Normalize to a simple dict[str,str]
        normalized: Dict[str, str] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    normalized[str(k)] = json.dumps(v, ensure_ascii=False)
                else:
                    normalized[str(k)] = "" if v is None else str(v)
        return normalized

    def _clear(self):
        self.captured_image = None
        self.captured_thumbnail = None
        self._log("Cleared.")

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)

    def _remove_last(self):
        csv_path = self.csv_entry.get().strip() or os.path.abspath("captures.csv")
        if not os.path.isfile(csv_path):
            messagebox.showinfo("Remove last", "No CSV found to modify.")
            return
        if remove_last_row_from_csv(csv_path):
            self._log("Removed last row from CSV.")
            self._load_data_table()
        else:
            self._log("No rows to remove.")

    def _load_data_table(self):
        # Populate table dynamically using current CSV header
        if not hasattr(self, "table"):
            return
        for iid in self.table.get_children():
            self.table.delete(iid)
        csv_path = self.csv_entry.get().strip() or os.path.abspath("captures.csv")
        if not os.path.isfile(csv_path):
            return
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                # Reconfigure treeview columns to match CSV headers
                self.table.configure(columns=headers)
                for col in self.table["columns"]:
                    self.table.heading(col, text=col)
                    # Wider columns for common fields
                    width = 120
                    if col.lower() in {"description"}:
                        width = 260
                    self.table.column(col, width=width, anchor="w")
                for row in reader:
                    values = [row.get(h, "") for h in headers]
                    self.table.insert("", "end", values=values)
        except Exception as e:
            self._log(f"Failed to load table: {e}")

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Fonts and colors
        try:
            tkfont.nametofont("TkDefaultFont").configure(size=10)
            tkfont.nametofont("TkTextFont").configure(size=10)
        except Exception:
            pass

        # Dark palette
        bg = "#0f0f14"
        text = "#eaeaf0"
        caption = "#b9b6d3"
        purple = "#8b5cf6"
        card_bg = "#15151c"

        # Labels
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Header.TLabel", background=bg, foreground=text, font=("Segoe UI", 18, "bold"))
        style.configure("Caption.TLabel", background=bg, foreground=caption, font=("Segoe UI", 10))

        # Buttons
        style.configure("Accent.TButton", background=purple, foreground="#ffffff", padding=(14, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#7c3aed")])
        style.configure("Danger.TButton", background="#ef4444", foreground="#ffffff", padding=(14, 8), borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#dc2626")])

        # Treeview dark style
        style.configure("Data.Treeview", background=card_bg, fieldbackground=card_bg, foreground=text, borderwidth=0, rowheight=24)
        style.configure("Treeview.Heading", background=card_bg, foreground=caption)

        # Badge label (pill look)
        style.configure("Badge.TLabel", background="#2a2538", foreground=purple, padding=(10, 2))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()


