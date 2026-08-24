#!/usr/bin/env python3
"""AI Memory Chat GUI - rozmowa z AI w oknie tkinter"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import json
import threading
import datetime

class AIChatApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Chat Client")
        self.root.geometry("600x450")
        self.root.minsize(400, 300)
        
        self.api_key = ""
        self.setup_ui()
        self.show_welcome()
    
    def setup_ui(self):
        # Frame góra
        settings_frame = ttk.Frame(self.root, padding="4")
        settings_frame.pack(fill=tk.X)
        
        self.status_var = tk.StringVar(value="Połączone z AI!")
        ttk.Label(settings_frame, textvariable=self.status_var, fg="green").pack(anchor=tk.W)
        
        self.key_var = tk.StringVar()
        key_entry = ttk.Entry(settings_frame, textvariable=self.key_var, width=25)
        key_entry.pack(side=tk.LEFT, padx=3)
        
        save_btn = ttk.Button(
            settings_frame, 
            text="Save", 
            command=self.save_api_key
        )
        save_btn.pack(side=tk.RIGHT)
        
        # Frame środek
        chat_frame = ttk.Frame(self.root, padding="5")
        chat_frame.pack(fill=tk.BOTH, expand=True)
        
        self.text = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=True)
        
        # Frame dół
        btn_frame = ttk.Frame(self.root, padding="4")
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        send_btn = ttk.Button(btn_frame, text="SEND", command=self.send_message)
        send_btn.pack(side=tk.LEFT, padx=3)
        
        clear_btn = ttk.Button(btn_frame, text="Clear", command=self.clear_chat)
        clear_btn.pack(side=tk.LEFT, padx=3)
    
    def save_api_key(self):
        key = self.key_var.get().strip()
        if key:
            self.api_key = f"Bearer {key}"
            self.status_var.set(f"Połączone | Key: {key[:8]}...")
    
    def send_message(self):
        content = self.text.get('1.0', tk.END).strip()
        lines = content.split('\n')
        
        last_user_msg = ""
        for line in reversed(lines):
            if "[JA]" in line:
                last_user_msg = line.replace("[JA]", "").strip()
                break
        
        if not last_user_msg:
            return
        
        timestamp = datetime.datetime.now().strftime("%H:%M")
        self.text.insert(tk.END, f"\n{timestamp}\n[JA] {last_user_msg}")
        
        self.text.insert(tk.END, f"\n{timestamp}\n[AI] 💭 Myślę...\n\n")
        
        threading.Thread(target=self.process_message, args=(last_user_msg,), daemon=True).start()
    
    def process_message(self, message):
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = self.api_key
            
            response = requests.post(
                "http://localhost:8420/v3/skill/list",
                json={"query": message},
                headers={**headers, "x-tdai-service-id": "test-team", "Content-Type": "application/json"},
                timeout=20
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    self.root.after(0, lambda: self.update_response(data))
                else:
                    self.root.after(0, lambda msg=data.get('message', 'Brak odpowiedzi'): self.update_response(msg))
            else:
                self.root.after(0, lambda err=str(response.json()): self.update_response(err))
        except Exception as e:
            self.root.after(0, lambda err=str(e): self.update_response(f"Błąd: {err}"))
    
    def update_response(self, response):
        ts = datetime.datetime.now().strftime("%H:%M")
        self.text.insert(tk.END, f"\n{ts}\n[AI] {response}")
    
    def clear_chat(self):
        self.text.delete('1.0', tk.END)
        self.status_var.set("Połączone z AI!")
    
    def show_welcome(self):
        welcome = """[SYSTEM]""" + "="*50 + """
AI Chat Client jest gotowy!

API: http://localhost:8420
Status: ✅ Połączone

Instrukcja:
1. Napisz wiadomość
2. Kliknij SEND lub Enter
3. Odbierz odpowiedź od AI

Opcjonalnie: wpisz API KEY i kliknij Save""" + "="*50 + """"""
        self.text.insert(tk.END, welcome)
        self.text.tag_config("sys", foreground="gray", background="#f0f0f0")
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = AIChatApp()
    app.run()
