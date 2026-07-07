import os
import PyInstaller.__main__

def build():
    """Create the listener application"""
    basepath = os.path.abspath(os.path.dirname(__file__))
    PyInstaller.__main__.run([
        os.path.join(basepath, "listener.py"),
        "-w",  # windowed: the listener is a tkinter app, no console needed
        "-F",
        "-i",
        os.path.join(basepath, "app_icon.ico")
    ])


if __name__ == "__main__":
    build()