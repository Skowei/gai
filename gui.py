#!/usr/bin/env python3
"""
==============================================================================
AI Memory Chat GUI - rozmowa z AI w oknie tkinter (Ecosystem V2.0)
Domyślnie łączy się z backendem Flask (app.py): http://localhost:5000/api/chat
Uruchomienie:  python3 gui.py
==============================================================================
"""

import os
import threading
from datetime import datetime

import requests
import tkinter as tk
from tkinter import ttk, scrolledtext

API_URL = os.getenv("CHAT_API_URL", "http://localhost:5000/api/chat")
REQUEST_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "120"))


class AIChatApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Ecosystem V2.0 — Chat")
        self.root.geometry("720x520")
        self.root.minsize(480, 360)

        self.busy = False
        self._status_label = None
        self.setup_ui()
        self.check_backend()
        self.show_welcome()

    # ------------------------------------------------------------------ UI --
    def setup_ui(self):
        # Góra: status
        top = ttk.Frame(self.root, padding="6")
        top.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Sprawdzam połączenie...")
        self._status_label = ttk.Label(top, textvariable=self.status_var)
        self._status_label.pack(anchor=tk.W)

        # Środek: okno rozmowy (tylko do czytania)
        chat_frame = ttk.Frame(self.root, padding="6")
        chat_frame.pack(fill=tk.BOTH, expand=True)
        self.chat = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, font=("Consolas", 10),
            state=tk.DISABLED,
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        self.chat.tag_config("sys", foreground="#666666")
        self.chat.tag_config("user", foreground="#0057d8")
        self.chat.tag_config("ai", foreground="#007a33")
        self.chat.tag_config("err", foreground="#c62828")
        self.chat.tag_config("ts", foreground="#999999")

        # Dół: pole inputu + przyciski
        bottom = ttk.Frame(self.root, padding="6")
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.entry = ttk.Entry(bottom)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda _e: self.send_message())
        self.entry.bind("<KP_Enter>", lambda _e: self.send_message())
        self.entry.focus_set()

        self.send_btn = ttk.Button(
            bottom, text="Wyślij ▶", command=self.send_message)
        self.send_btn.pack(side=tk.LEFT)

        clear_btn = ttk.Button(bottom, text="Wyczyść", command=self.clear_chat)
        clear_btn.pack(side=tk.LEFT, padx=(6, 0))

    # ------------------------------------------------------------ Pomocnicze --
    def append(self, text: str, tag: str = "ai") -> None:
        """Bezpieczne (wątki!) dopisanie linii do okna rozmowy."""
        def _do():
            self.chat.configure(state=tk.NORMAL)
            ts = datetime.now().strftime("%H:%M")
            self.chat.insert(tk.END, f"[{ts}] ", "ts")
            self.chat.insert(tk.END, text.rstrip() + "\n\n", tag)
            self.chat.see(tk.END)
            self.chat.configure(state=tk.DISABLED)
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        color = "#c62828" if error else "#007a33"
        self._status_label.configure(foreground=color)

    def check_backend(self):
        """Sprawdzenie /health backendu Flask."""
        base = API_URL.rsplit("/api/chat", 1)[0]

        def _check():
            try:
                r = requests.get(f"{base}/health", timeout=5)
                data = r.json()
                if r.status_code == 200 and data.get("ollama"):
                    msg = "🟢 Backend ONLINE — Ollama gotowa"
                    err = False
                else:
                    msg = "🟠 Backend działa, ale Ollama offline"
                    err = True
            except Exception:
                msg = f"🔴 Backend offline ({API_URL}) — uruchom: python3 app.py"
                err = True
            self.root.after(0, lambda: self.set_status(msg, error=err))

        threading.Thread(target=_check, daemon=True).start()

    def send_message(self):
        query = self.entry.get().strip()
        if not query or self.busy:
            return
        self.busy = True
        try:
            self.send_btn.state(["disabled"])
        except tk.TclError:
            pass
        self.append(f"[JA] {query}", "user")
        self.entry.delete(0, tk.END)
        self.append("[AI] ⏳ myślę...", "sys")
        threading.Thread(target=self._worker, args=(query,), daemon=True).start()

    def _worker(self, query: str):
        try:
            response = requests.post(
                API_URL,
                json={"query": query},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                answer = data.get("response", "(pusta odpowiedź)")
                tag = "ai"
            else:
                answer = f"[BŁĄD] {data.get('error', 'nieznany')}"
                tag = "err"
        except Exception as exc:
            answer = f"[BŁĄD] Połączenie nieudane: {exc}"
            tag = "err"
        self.root.after(0, lambda: self._finish(answer, tag))

    def _finish(self, answer: str, tag: str):
        # Usuń linię "[AI] ⏳ myślę..." i wstaw prawdziwą odpowiedź
        self.chat.configure(state=tk.NORMAL)
        content = self.chat.get("1.0", tk.END)
        idx = content.rfind("⏳ myślę...")
        if idx != -1:
            line_start = content.rfind("\n", 0, max(idx - 8, 0))
            start_index = "1.0" if line_start == -1 else f"1.0+{line_start + 1}c"
            self.chat.delete(start_index, tk.END)
        self.chat.configure(state=tk.DISABLED)
        self.append(answer, tag)
        self.busy = False
        try:
            self.send_btn.state(["!disabled"])
        except tk.TclError:
            pass
        self.entry.focus_set()

    def clear_chat(self):
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
        self.show_welcome()

    def show_welcome(self):
        self.append(
            "[SYSTEM] AI Ecosystem V2.0 — Chat gotowy!\n"
            f"Backend: {API_URL}\n"
            "Napisz wiadomość i naciśnij ENTER lub kliknij „Wyślij”.\n"
            "Routing modeli: kod → qwen2.5-coder | logika/tekst → qwen3.5",
            "sys",
        )

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AIChatApp()
    app.run()
