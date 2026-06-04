import subprocess
import sys

def send_notification(title: str, message: str) -> None:
    """
    Triggers a native macOS desktop notification.
    Falls back to stdout printing on other operating systems.
    """
    # Escape double quotes to avoid AppleScript syntax errors
    title_escaped = title.replace('"', '\\"')
    message_escaped = message.replace('"', '\\"')
    
    # AppleScript payload
    applescript_cmd = f'display notification "{message_escaped}" with title "{title_escaped}"'
    
    # We only run osascript if we are on macOS
    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["osascript", "-e", applescript_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            return
        except Exception:
            pass
            
    # Fallback/Stdout logging if not macOS or if command fails
    print(f"\n[NOTIFICATION] {title.upper()}: {message}\n", flush=True)
