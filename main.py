import os
import sys
import threading
import webview
from backend.api import AppAPI

def main():
    # Setup API
    api = AppAPI()
    
    # Resolve frontend path
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    frontend_path = os.path.join(base_dir, 'frontend', 'index.html')
    
    # Create Window
    window = webview.create_window(
        'VoeNote Desktop',
        url=frontend_path,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
        background_color='#0f172a'
    )
    
    # Assign window to API for callbacks
    api.set_window(window)
    
    # Start app
    webview.start(debug=True)

if __name__ == '__main__':
    main()
