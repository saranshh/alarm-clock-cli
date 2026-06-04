import os
import subprocess
from typing import Optional

DEFAULT_SOUNDS = [
    "/System/Library/Sounds/Glass.aiff",
    "/System/Library/Sounds/Ping.aiff",
    "/System/Library/Sounds/Submarine.aiff",
    "/System/Library/Sounds/Tink.aiff"
]

def get_default_sound() -> str:
    """Finds the first existing default macOS sound."""
    for path in DEFAULT_SOUNDS:
        if os.path.exists(path):
            return path
    return ""

class AlarmPlayer:
    """
    Handles playback of alarm sounds using the macOS native 'afplay' tool.
    Spawns 'afplay' as a subprocess, allowing it to run asynchronously.
    """
    def __init__(self, sound_path: Optional[str] = None):
        if sound_path and os.path.exists(sound_path):
            self.sound_path = sound_path
        else:
            self.sound_path = get_default_sound()
            
        self.process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        """Starts playing the sound. If already playing, does nothing."""
        if self.process and self.process.poll() is None:
            return

        if not self.sound_path:
            # Fallback to terminal bell if no audio file available
            print("\a", end="", flush=True)
            return

        try:
            # Spawn afplay process
            self.process = subprocess.Popen(
                ["afplay", self.sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            # Fallback: trigger system beep if afplay is not available
            print(f"Warning: Failed to play sound via afplay ({e}). Triggering terminal bell.", flush=True)
            print("\a", end="", flush=True)

    def is_playing(self) -> bool:
        """Checks if the sound is currently playing."""
        if not self.process:
            return False
        return self.process.poll() is None

    def stop(self) -> None:
        """Stops the sound playback if it is running."""
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
        self.process = None
