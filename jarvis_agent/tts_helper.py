#!/usr/bin/env python3
"""
TTS Helper - Uses Piper for natural voice
"""

import subprocess
import os

def speak(text: str):
    """Speak text using Piper TTS."""
    try:
        piper_path = os.path.expanduser("~/piper/piper")
        model_path = os.path.expanduser("~/piper-voices/en_US-lessac-medium.onnx")
        
        cmd = f'echo "{text}" | {piper_path} --model {model_path} --output-raw | aplay -r 22050 -f S16_LE -t raw - 2>/dev/null'
        subprocess.Popen(cmd, shell=True)
    except Exception as e:
        # Fallback to espeak
        subprocess.Popen(['espeak', '-s', '150', text], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    speak("Hello! I am Jarvis with my new natural voice!")
