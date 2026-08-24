#!/usr/bin/env python3
"""AI Chat TUI - Terminalowy klient rozmowy z AI"""

import curses
import curses.textwidget
import time
import json
import sys

def format_time():
    return time.strftime("%H:%M")

def chat_tui(stdscr):
    """Main TUI application"""
    
    # Initialize colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)  # User message
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # AI response
    curses.init_pair(3, curses.COLOR_YELLOW, -1)  # System info
    curses.init_pair(4, curses.COLOR_CYAN, -1)    # Loading
    
    # Get terminal size
    height, width = stdscr.getmaxyx()
    
    # Create scrolling window for chat
    win_y = height - 25
    win_x = width - 60
    
    try:
        chat_win = curses.newwin(win_y, win_x, 1, (width - win_x)//2)
        status_win = curses.newwin(2, width, win_y + 2, 0)
    except curses.error:
        stdscr.addstr(0, 0, "Terminal zbyt mały")
        return
    
    chat_win.border(curses.A_REVERSE)
    chat_win.keypad(True)
    
    # Display welcome message
    welcome = """[SYSTEM] AI Chat - rozmowa z naszym produktem AI!""" + "="*56 + """

Wpisz wiadomość i naciśnij ENTER aby wysłać.
Naciśnij Ctrl+C aby wyjść."""
    chat_win.addstr(0, 0, welcome[:width-1])
    chat_win.refresh()
    
    status_str = "Gotowy... Wpisz 'quit' aby zakończyć | URL: http://localhost:8420"
    status_win.addstr(0, 0, status_str[:width-1])
    status_win.refresh()
    
    messages = []
    current_msg = ""
    api_key = ""
    
    while True:
        try:
            key = chat_win.getch()
            
            if key == -1:
                break
            
            # Handle quit command
            if key == ord('q'):
                break
            
            # Handle Enter (send message)
            if key == 10 or key == curses.KEY_ENTER:
                if current_msg.strip():
                    msg = current_msg.strip()
                    
                    # Add user message to chat
                    chat_win.addstr(chat_win.getmaxyx()[0]-2, 2, format_time() + " [JA] " + msg[:width-5])
                    messages.append(("JA", msg))
                    
                    # Clear input
                    current_msg = ""
                else:
                    chat_win.addstr(1, 1, c

"Brak wiadomości...")
            
            # Handle escape
            elif key == 27:
                break
            
            # Add character to input (printable ASCII)
            elif 32 <= key < 127 or key == curses.KEY_BACKSPACE or key == 127 or key == curses.KEY_DC:
                if key == curses.KEY_BACKSPACE or key == 127 or key == curses.KEY_DC:
                    current_msg = current_msg[:-1]
                else:
                    current_msg += chr(key)
            
            # Add text to input line (for multi-char inputs like arrows)
            elif curses.is_a_key(key):
                c = curses.keyname(key)[:1].decode('utf-8')
                if c:
                    current_msg += c
            
        except Exception as e:
            continue
        
        # Update status window
        status_str = f"GOTOWY... Wpisz 'quit' aby zakończyć"
        status_win.addstr(0, 0, status_str[:width-1])
        status_win.refresh()
        
        # Refresh chat window (scroll if needed)
        try:
            chat_win.scroll()
            chat_win.move(chat_win.getmaxyx()[0]-1, 0)
            chat_win.refresh()
        except curses.error:
            pass
    
    curses.endwin()

def main():
    """Main entry point"""
    stdscr = curses.initscr()
    curses.curs_set(0)  # Hide cursor
    chat_tui(stdscr)
    curses.endwin()

if __name__ == "__main__":
    main()