import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pathlib
import subprocess
import threading
import queue
import os
import sys

# ====================== CORE LOGIC (same as before) ======================
def list_directory(path: str | pathlib.Path):
    p = pathlib.Path(path).expanduser().resolve()
    if not p.is_dir():
        raise NotADirectoryError(str(p))
    # Return sorted list of (name, is_dir, full_path)
    items = []
    for item in p.iterdir():
        items.append((item.name, item.is_dir(), str(item)))
    return sorted(items, key=lambda x: (not x[1], x[0].lower()))  # dirs first


# ====================== FILE MANAGER PANEL ======================
class FileManagerFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.current_path = pathlib.Path.cwd()

        # Address bar
        self.path_var = tk.StringVar(value=str(self.current_path))
        self.path_entry = ttk.Entry(self, textvariable=self.path_var)
        self.path_entry.pack(fill="x", padx=5, pady=5)
        self.path_entry.bind("<Return>", lambda e: self.navigate_to(self.path_var.get()))

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=5)
        ttk.Button(toolbar, text="↑ Up", command=self.go_up).pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=5)

        # Treeview (the actual file list)
        columns = ("name", "type")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("name", width=300)
        self.tree.column("type", width=80)
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Double-click to open folder or file
        self.tree.bind("<Double-1>", self.on_double_click)

        self.refresh()  # initial load

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())  # clear
        try:
            items = list_directory(self.current_path)
            for name, is_dir, full_path in items:
                item_type = "📁 Folder" if is_dir else "📄 File"
                self.tree.insert("", "end", values=(name, item_type), tags=(full_path,))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh(self):
        self.populate_tree()
        self.path_var.set(str(self.current_path))

    def navigate_to(self, new_path):
        try:
            p = pathlib.Path(new_path).resolve()
            if p.is_dir():
                self.current_path = p
                self.refresh()
            else:
                messagebox.showinfo("Info", "Selected item is a file (add open logic here!)")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def go_up(self):
        parent = self.current_path.parent
        if parent != self.current_path:
            self.current_path = parent
            self.refresh()

    def on_double_click(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        item = self.tree.item(selection[0])
        full_path = item["tags"][0]  # we stored the full path in tags
        if pathlib.Path(full_path).is_dir():
            self.current_path = pathlib.Path(full_path)
            self.refresh()
        else:
            # Optional: open file with default app
            if sys.platform == "win32":
                os.startfile(full_path)
            else:
                subprocess.run(["xdg-open", full_path])


# ====================== TERMINAL PANEL ======================
class TerminalFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.output_queue = queue.Queue()

        # Output area (scrollable terminal-like text)
        self.output = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=20, bg="#1e1e1e", fg="#ffffff", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, padx=5, pady=5)
        self.output.config(state="disabled")  # read-only

        # Input bar
        input_frame = ttk.Frame(self)
        input_frame.pack(fill="x", padx=5, pady=5)
        self.cmd_entry = ttk.Entry(input_frame, font=("Consolas", 10))
        self.cmd_entry.pack(side="left", fill="x", expand=True)
        self.cmd_entry.bind("<Return>", self.run_command)

        ttk.Button(input_frame, text="Run", command=self.run_command).pack(side="right", padx=5)

        # Start polling the queue
        self.after(100, self.process_queue)

    def run_command(self, event=None):
        command = self.cmd_entry.get().strip()
        if not command:
            return
        self.cmd_entry.delete(0, tk.END)

        # Show command in output
        self._insert_text(f"> {command}\n", "command")

        # Run in background thread (prevents GUI freeze)
        threading.Thread(target=self._execute, args=(command,), daemon=True).start()

    def _execute(self, command):
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,   # line buffered
            )
            for line in process.stdout:
                self.output_queue.put(line)
            process.wait()
            self.output_queue.put(f"[Process exited with code {process.returncode}]\n")
        except Exception as e:
            self.output_queue.put(f"Error: {e}\n")

    def _insert_text(self, text: str, tag: str = None):
        self.output.config(state="normal")
        if tag:
            self.output.insert(tk.END, text, tag)
        else:
            self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.config(state="disabled")

    def process_queue(self):
        """Safely move output from background thread to GUI"""
        try:
            while True:
                line = self.output_queue.get_nowait()
                self._insert_text(line)
        except queue.Empty:
            pass
        self.after(100, self.process_queue)  # check again soon


# ====================== MAIN APP (OOP glue) ======================
class PyFileTerminalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PyFile + Terminal — Modern Desktop App")
        self.geometry("1200x700")

        # Modern styling
        style = ttk.Style(self)
        style.theme_use("clam")  # clean built-in theme

        # Split window: File manager | Terminal
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        self.file_manager = FileManagerFrame(paned)
        paned.add(self.file_manager, weight=1)

        self.terminal = TerminalFrame(paned)
        paned.add(self.terminal, weight=1)

        # Status bar
        status = ttk.Label(self, text="Ready — Built with pure Tkinter + OOP", relief="sunken", anchor="w")
        status.pack(side="bottom", fill="x")


if __name__ == "__main__":
    app = PyFileTerminalApp()
    app.mainloop()