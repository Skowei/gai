#!/usr/bin/env python3
"""
==============================================================================
AI Chat TUI - Terminalowy klient rozmowy z AI (Ecosystem V2.0)
Łączy się z lokalną Ollamą przez wspólnego klienta (src.llm).
Uruchomienie:  python3 ai_chat.py
Wyjście:       Ctrl+C lub /quit
==============================================================================
"""

import curses
import locale
import sys
from datetime import datetime

locale.setlocale(locale.LC_ALL, "")

sys.path.insert(0, "/home/maciei/dev/ai")

from src.llm import ollama_chat, is_healthy, OLLAMA_BASE_URL  # noqa: E402

HISTORY_LINES = []


def format_time() -> str:
    return datetime.now().strftime("%H:%M")


def append_history(win, width, text: str, color_pair: int) -> None:
    """Dodaje linię do historii z zawijaniem i odrysowuje okno."""
    max_rows = win.getmaxyx()[0] - 2
    avail = max(4, width - 4)
    while len(text) > 0:
        HISTORY_LINES.append((text[:avail], color_pair))
        text = text[avail:]
    start = max(0, len(HISTORY_LINES) - max_rows)
    win.erase()
    win.border()
    row = 1
    for line, cpair in HISTORY_LINES[start:]:
        try:
            win.addnstr(row, 2, line, width - 4, curses.color_pair(cpair))
        except curses.error:
            pass
        row += 1
    win.refresh()


def chat_tui(stdscr) -> None:
    """Główna pętla TUI."""
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)   # użytkownik
    curses.init_pair(2, curses.COLOR_GREEN, -1)   # AI
    curses.init_pair(3, curses.COLOR_YELLOW, -1)  # system
    curses.init_pair(4, curses.COLOR_CYAN, -1)    # input

    stdscr.keypad(True)
    height, width = stdscr.getmaxyx()

    hist_win = curses.newwin(height - 3, width, 0, 0)
    inp_win = curses.newwin(3, width, height - 3, 0)
    inp_win.border()
    hist_win.scrollok(True)

    online = is_healthy()
    status = "ONLINE ✅" if online else "OFFLINE ❌ (uruchom: ollama serve)"
    append_history(hist_win, width,
                   f"[SYSTEM] AI Chat V2.0 | {OLLAMA_BASE_URL} | {status}", 3)
    append_history(hist_win, width,
                   "[SYSTEM] Wpisz wiadomość i ENTER aby wysłać. /quit = wyjście.", 3)

    input_text = ""
    history = []          # pełna historia rozmowy (role/content)
    cursor_visible = True

    while True:
        inp_win.erase()
        inp_win.border()
        prefix = f" {format_time()} ▶ "
        try:
            inp_win.addnstr(1, 1, prefix + input_text, width - 3,
                            curses.color_pair(4))
        except curses.error:
            pass
        inp_win.refresh()
        try:
            stdscr.move(height - 2, min(len(prefix) + len(input_text) + 1, width - 2))
            if cursor_visible:
                curses.curs_set(1)
        except curses.error:
            pass

        try:
            key = stdscr.get_wch()
        except KeyboardInterrupt:
            break

        if key in ("\n", "\r", chr(10), chr(13)):
            query = input_text.strip()
            input_text = ""
            if not query:
                continue
            if query.lower() in ("/quit", "/exit", "/q"):
                break

            append_history(hist_win, width, f"{format_time()} [JA] {query}", 1)
            history.append({"role": "user", "content": query})

            if not online:
                append_history(hist_win, width,
                               "[SYSTEM] Ollama niedostępna - nie mogę odpowiedzieć.", 3)
                continue

            append_history(hist_win, width,
                           f"{format_time()} [AI] ⏳ myślę...", 3)

            try:
                answer = ollama_chat(history)
            except Exception as exc:
                answer = f"[BŁĄD] {exc}"
            history.append({"role": "assistant", "content": answer})
            append_history(hist_win, width, f"{format_time()} [AI] {answer}", 2)

        elif key in (chr(127), "\b", curses.KEY_BACKSPACE):
            input_text = input_text[:-1]
        elif isinstance(key, str) and key.isprintable():
            input_text += key
        elif key == curses.KEY_RESIZE:
            height, width = stdscr.getmaxyx()
            hist_win.resize(max(3, height - 3), width)
            inp_win.mvwin(max(3, height - 3), 0)
            append_history(hist_win, width, "", 3)

    curses.curs_set(0)


def main() -> None:
    try:
        curses.wrapper(chat_tui)
    except curses.error as exc:
        print(f"Terminal error: {exc}")
        sys.exit(1)
    print("Do zobaczenia! 👋")


if __name__ == "__main__":
    main()