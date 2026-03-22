"""HiveCenter Computer Use: Fiziksel fare, klavye ve masaüstü kontrolü sağlar."""
import os
import subprocess

def take_desktop_screenshot(out_path: str) -> bool:
    try:
        import pyautogui
        img = pyautogui.screenshot()
        img.save(out_path)
        return True
    except ImportError:
        # Fallback to linux scrot
        res = subprocess.run(["scrot", out_path], capture_output=True)
        return res.returncode == 0

def desktop_click(x: str, y: str) -> str:
    try:
        import pyautogui
        pyautogui.click(int(x), int(y))
        return f"Desktop clicked exactly on ({x}, {y})"
    except ImportError:
        return "ERROR: 'pyautogui' is not installed. Use [SHELL: pip install pyautogui] or [SHELL: sudo apt install xdotool]"
    except Exception as e:
        return f"Desktop click error: {str(e)}"

def desktop_type(text: str) -> str:
    try:
        import pyautogui
        pyautogui.write(text, interval=0.01)
        return f"Desktop typed: '{text}'"
    except ImportError:
        return "ERROR: 'pyautogui' is not installed. Needs [SHELL: pip install pyautogui]"

def desktop_key(key: str) -> str:
    try:
        import pyautogui
        pyautogui.press(key.strip())
        return f"Desktop pressed key: '{key}'"
    except ImportError:
        return "ERROR: 'pyautogui' is not installed."
