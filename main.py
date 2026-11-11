from app.dashboard.routes import app, socketio
from config import Config
import subprocess, threading, time, webbrowser

def open_browser():
    time.sleep(2)
    try:
        subprocess.run(["open", "-a", "Google Chrome", f"http://localhost:{Config.PORT}"])
    except:
        webbrowser.open(f"http://localhost:{Config.PORT}")

if __name__ == '__main__':
    print("="*55)
    print("🚦  Road Safety Violation Detection System")
    print("="*55)
    print(f"🌐  Dashboard : http://localhost:{Config.PORT}")
    print("="*55)
    threading.Thread(target=open_browser, daemon=True).start()
    socketio.run(app, host=Config.HOST, port=Config.PORT, debug=False)
