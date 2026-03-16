import sys
import os
import threading
import webbrowser
import time

if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
    os.chdir(sys._MEIPASS)

import uvicorn
import backend

def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:8000")

threading.Thread(target=open_browser, daemon=True).start()
uvicorn.run(backend.app, host="127.0.0.1", port=8000)