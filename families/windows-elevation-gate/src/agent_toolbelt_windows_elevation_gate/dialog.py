"""A readable, keyboard-accessible explanation before the native UAC dialog."""
from __future__ import annotations

import subprocess

BG = "#f1f4fa"
INK = "#14213a"
MUTED = "#34445c"
ACCENT = "#1458bd"
LINE = "#c7d2e0"


class ExplanationDialog:
    def __init__(self, request, *, preview=False):
        import tkinter as tk
        from tkinter import ttk

        self.preview = preview
        self.answer = {"accepted": False, "feedback": ""}
        root = self.root = tk.Tk()
        root.title(("Preview - " if preview else "Administrator request - ") + request["thread_name"])
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        width = min(850, root.winfo_screenwidth() - 64)
        height = min(890, root.winfo_screenheight() - 100)
        root.geometry(f"{width}x{height}+{max(0, (root.winfo_screenwidth()-width)//2)}+40")
        root.minsize(min(600, width), min(500, height))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Gate.Vertical.TScrollbar", background=LINE, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED)

        header = tk.Frame(root, bg=INK, padx=24, pady=18)
        header.grid(row=0, column=0, sticky="ew")
        shield = tk.Canvas(header, width=46, height=48, bg=INK, highlightthickness=0)
        shield.pack(side="left", padx=(0, 16))
        shield.create_polygon(23, 3, 42, 10, 39, 29, 23, 44, 7, 29, 4, 10,
                              fill=ACCENT, outline="#a8c9ff", width=2)
        shield.create_line(23, 12, 23, 27, fill="white", width=3)
        shield.create_oval(21, 32, 25, 36, fill="white", outline="white")
        title = tk.Frame(header, bg=INK)
        title.pack(side="left", fill="x", expand=True)
        tk.Label(title, text="Administrator access", bg=INK, fg="white",
                 font=("Segoe UI", 20, "bold"), anchor="w").pack(fill="x")
        subtitle = "DESIGN PREVIEW - rate the layout; no command or UAC will run" if preview else "Review the action before Windows asks for permission"
        subtitle_label = tk.Label(title, text=subtitle, bg=INK, fg="#d8e6ff",
                                  font=("Segoe UI", 10), anchor="w", wraplength=width-150)
        subtitle_label.pack(fill="x", pady=(5, 0))

        middle = tk.Frame(root, bg=BG)
        middle.grid(row=1, column=0, sticky="nsew")
        canvas = self.canvas = tk.Canvas(middle, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(middle, orient="vertical", command=canvas.yview,
                                   style="Gate.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=BG, padx=24, pady=18)
        window = canvas.create_window(0, 0, window=body, anchor="nw")
        self.wrap_labels = []

        def resize(event):
            canvas.itemconfigure(window, width=event.width)
            for label in self.wrap_labels:
                label.configure(wraplength=max(100, event.width - 88))

        canvas.bind("<Configure>", resize)
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        def wheel(event):
            if not isinstance(event.widget, tk.Text):
                canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

        root.bind_all("<MouseWheel>", wheel)

        def label(parent, text, *, color=INK, size=12, bold=False, bg="white"):
            item = tk.Label(parent, text=text, bg=bg, fg=color, justify="left", anchor="w",
                            font=("Segoe UI", size, "bold" if bold else "normal"), wraplength=width-88)
            item.pack(fill="x", anchor="w")
            self.wrap_labels.append(item)
            return item

        def card(heading):
            outer = tk.Frame(body, bg="white", highlightbackground=LINE, highlightthickness=1,
                             padx=16, pady=10)
            outer.pack(fill="x", pady=(0, 10))
            label(outer, heading, color=ACCENT, size=10, bold=True).pack_configure(pady=(0, 6))
            return outer

        task = card("REQUESTED ACTION")
        label(task, request["task"], size=15, bold=True)
        label(task, "Thread: " + request["thread_name"], color=MUTED, size=10).pack_configure(pady=(5, 0))
        why = card("WHY ADMINISTRATOR RIGHTS?")
        label(why, request["reason"])
        changes = card("WHAT WILL CHANGE")
        label(changes, request["changes"])
        label(changes, "Targets: " + "; ".join(request["targets"]), color=MUTED, size=10).pack_configure(pady=(7, 0))
        details = card("EXACT COMMAND")
        command_frame = tk.Frame(details, bg="#f4f7f8", highlightbackground=LINE, highlightthickness=1)
        command_frame.pack(fill="x", pady=(0, 8))
        self.command = tk.Text(command_frame, height=2, width=1, wrap="word", bd=0,
                               padx=10, pady=10, bg="#f4f7f8", fg=INK,
                               font=("Cascadia Mono", 11), selectbackground="#c5daff", takefocus=True)
        self.command.insert("1.0", subprocess.list2cmdline(request["command"]))
        self.command.configure(state="disabled")
        command_scroll = ttk.Scrollbar(command_frame, orient="vertical", command=self.command.yview)
        self.command.configure(yscrollcommand=command_scroll.set)
        command_scroll.pack(side="right", fill="y")
        self.command.pack(side="left", fill="x", expand=True)
        label(details, "Working folder: " + request["cwd"], color=MUTED, size=9)
        label(details, "Windows prompt will name: " + request["elevation_host"], color=MUTED, size=9).pack_configure(pady=(4, 0))
        note = card("FEEDBACK TO THE TASK  /  OPTIONAL")
        feedback_hint = ("What should be improved? Add feedback and choose Needs Changes." if preview else
                         "Want something changed? Cancel and explain below. Feedback never changes this command.")
        label(note, feedback_hint,
              color=MUTED, size=10).pack_configure(pady=(0, 8))
        self.feedback = tk.Text(note, height=2, width=1, wrap="word", bg="#f9fbfc", fg=INK,
                                font=("Segoe UI", 11), bd=1, relief="solid", padx=10, pady=8,
                                highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)
        self.feedback.pack(fill="x")
        label(note, "First 4,000 characters are returned to the requesting task.", color=MUTED, size=9).pack_configure(pady=(5, 0))

        footer = self.footer = tk.Frame(root, bg="white", padx=24, pady=16, highlightbackground=LINE, highlightthickness=1)
        footer.grid(row=2, column=0, sticky="ew")
        message = "Both buttons only rate this design.\nNo command or UAC will run." if preview else "Accept continues to Windows UAC.\nOnly Windows can grant administrator rights."
        footer_label = tk.Label(footer, text=message, bg="white", fg=MUTED, justify="left",
                                font=("Segoe UI", 9), wraplength=max(180, width-395))
        footer_label.pack(side="left", fill="x", expand=True)
        self.accept = tk.Button(footer, text="Looks Good" if preview else "Accept & Continue", command=lambda: self.finish(True),
                                bg=ACCENT, fg="white", activebackground="#0d3f8d", activeforeground="white",
                                font=("Segoe UI", 11, "bold"), padx=18, pady=10, bd=0,
                                highlightthickness=2, highlightbackground=ACCENT, highlightcolor=INK)
        self.accept.pack(side="right", padx=(10, 0))
        self.cancel = tk.Button(footer, text="Needs Changes" if preview else "Cancel",
                                command=lambda: self.finish(False), font=("Segoe UI", 11),
                                bg="white", fg=INK, activebackground="#e5edfa", padx=18, pady=10,
                                bd=0, highlightthickness=2, highlightbackground="#8091ab", highlightcolor=ACCENT)
        self.cancel.pack(side="right")

        def reflow(event):
            if event.widget is root:
                subtitle_label.configure(wraplength=max(180, event.width - 150))
                footer_label.configure(wraplength=max(160, event.width - 395))

        def reveal(widget, card):
            top = card.winfo_y() + widget.winfo_y()
            visible_top = canvas.canvasy(0)
            if top < visible_top or top + widget.winfo_height() > visible_top + canvas.winfo_height():
                canvas.yview_moveto(max(0, top - 20) / max(1, body.winfo_height()))

        root.bind("<Configure>", reflow)
        self.command.bind("<FocusIn>", lambda event: reveal(self.command, details))
        self.feedback.bind("<FocusIn>", lambda event: reveal(self.feedback, note))
        root.protocol("WM_DELETE_WINDOW", lambda: self.finish(False))
        root.bind("<Escape>", lambda event: self.finish(False))
        root.update_idletasks()
        root.lift()
        self.cancel.focus_set()

    def finish(self, accepted):
        self.answer.update(accepted=accepted and not self.preview,
                           feedback=self.feedback.get("1.0", "end-1c")[:4000])
        if self.preview:
            self.answer["preview_approved"] = accepted
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.answer


def explain(request, *, preview=False):
    return ExplanationDialog(request, preview=preview).show()
