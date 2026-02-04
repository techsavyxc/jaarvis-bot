#!/usr/bin/env python3
"""
Voice Utilities - Supports multiple TTS engines
Automatically picks the best available option.
"""

import subprocess
import os
import shutil

def speak(text: str, engine: str = "auto"):
    """
    Speak text using the best available TTS engine.
    
    engine options: "auto", "piper", "espeak"
    """
    if engine == "auto":
        # Check what's available
        if shutil.which("piper") or os.path.exists(os.path.expanduser("~/piper/piper")):
            engine = "piper"
        else:
            engine = "espeak"
    
    try:
        if engine == "piper":
            piper_path = shutil.which("piper") or os.path.expanduser("~/piper/piper")
            model_path = os.path.expanduser("~/piper-voices/en_US-lessac-medium.onnx")
            
            if os.path.exists(model_path):
                # Generate and play
                cmd = f'echo "{text}" | {piper_path} --model {model_path} --output-raw | aplay -r 22050 -f S16_LE -t raw - 2>/dev/null'
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Fallback to espeak
                subprocess.Popen(['espeak', '-s', '150', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # espeak
            subprocess.Popen(['espeak', '-s', '150', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Speech failed: {e}")


if __name__ == "__main__":
    speak("Hello! Testing voice output.")
