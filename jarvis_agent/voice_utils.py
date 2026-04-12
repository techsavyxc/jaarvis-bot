#!/usr/bin/env python3
"""
Voice Utilities - Supports multiple TTS engines.
Automatically picks the best available option.

IMPORTANT: all TTS invocations go through this module to ensure user-
provided text is never interpolated into a shell command string.  The
previous approach (``echo "{text}" | piper ... | aplay`` with shell=True)
allowed command injection via the ``say`` intent.
"""

import os
import shutil
import subprocess


def speak(text: str, engine: str = "auto"):
    """Speak *text* asynchronously using the best available TTS engine.

    Engine options: ``"auto"``, ``"piper"``, ``"espeak"``.

    The function returns immediately (audio plays in a background process).
    Text is passed via stdin or as a list argument — never through a shell
    interpolation — so it is safe even if *text* contains shell meta-characters.
    """
    if engine == "auto":
        if shutil.which("piper") or os.path.exists(os.path.expanduser("~/piper/piper")):
            engine = "piper"
        else:
            engine = "espeak"

    try:
        if engine == "piper":
            _speak_piper(text)
        else:
            _speak_espeak(text)
    except Exception as e:
        print(f"Speech failed: {e}")


def _speak_piper(text: str):
    """Pipe text into Piper TTS -> aplay, with no shell=True."""
    piper_path = shutil.which("piper") or os.path.expanduser("~/piper/piper")
    model_path = os.path.expanduser("~/piper-voices/en_US-lessac-medium.onnx")

    if not os.path.exists(model_path):
        # Piper model not installed — fall back to espeak.
        _speak_espeak(text)
        return

    # Build the pipeline with explicit Popen pipes.
    # piper reads text from stdin and writes raw audio to stdout.
    # aplay reads that raw audio from its stdin and plays it.
    piper_proc = subprocess.Popen(
        [piper_path, '--model', model_path, '--output-raw'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    subprocess.Popen(
        ['aplay', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-'],
        stdin=piper_proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Allow aplay to receive SIGPIPE if piper exits.
    piper_proc.stdout.close()
    # Feed the text through stdin so it never touches a shell.
    piper_proc.stdin.write(text.encode('utf-8'))
    piper_proc.stdin.close()


def _speak_espeak(text: str):
    """Speak via espeak with list args (no shell)."""
    subprocess.Popen(
        ['espeak', '-s', '150', text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    speak("Hello! Testing voice output.")
