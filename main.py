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

'''pyinstaller --onefile --name
InterviewSimulator --add-data
"index.html;." --add-data
"backend.py;." --hidden-import
backend --hidden-import
uvicorn.logging --hidden-import
uvicorn.loops --hidden-import
uvicorn.loops.auto --hidden-import
uvicorn.protocols --hidden-import
uvicorn.protocols.http --hidden-import
uvicorn.protocols.http.auto --hidden-import
uvicorn.lifespan --hidden-import
uvicorn.lifespan.on --collect-all
uvicorn --collect-all fastapi main.py'''


#uvicorn backend:app --reload --port 8000
#http://localhost:8000