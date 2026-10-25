"""
check_audio.py  —  find out why a spoken answer is not being transcribed.

Run in the backend folder with the venv active:
    python check_audio.py                      checks data/audio/last_failed.* (saved by main.py)
    python check_audio.py path\\to\\file.webm    checks any audio file

It tests, one by one: the speech libraries, the Whisper model, reading the audio file,
the loudness of the recording, and the transcription itself.
"""

import glob
import os
import sys
import time

OK, BAD = "  [OK]  ", "  [FAIL]"


def find_file():
    if len(sys.argv) > 1:
        return sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    matches = sorted(glob.glob(os.path.join(here, "data", "audio", "last_failed.*")), key=os.path.getmtime)
    return matches[-1] if matches else None


def main():
    print("1/5  Speech libraries")
    try:
        import av  # noqa: F401
        import faster_whisper
        print(OK, f"faster-whisper {getattr(faster_whisper, '__version__', '')} and PyAV are installed")
    except Exception as exc:
        print(BAD, f"missing library: {exc}")
        print("        Fix: pip install -r requirements.txt  (inside the venv)")
        return

    print("2/5  Whisper model")
    import interview
    start = time.time()
    if interview.whisper_ready():
        print(OK, f"model '{interview.WHISPER_MODEL}' loaded in {time.time() - start:.1f} s")
    else:
        print(BAD, "model could not load. Turn Wi-Fi on once and run this again so it can download (~150 MB).")
        return

    path = find_file()
    print("3/5  Audio file")
    if not path or not os.path.exists(path):
        print(BAD, "no audio file found.")
        print("        Record one spoken answer in the app first (a failed one is saved automatically),")
        print("        or run:  python check_audio.py path\\to\\recording.webm")
        return
    size = os.path.getsize(path)
    print(OK if size >= 2000 else BAD, f"{path}  ({size} bytes)")
    if size < 2000:
        print("        The browser sent an almost empty recording: the microphone captured nothing.")
        print("        Fix: pick your real microphone in the Microphone list under the record button.")
        return

    print("4/5  Reading the audio")
    try:
        import av
        print(OK, f"PyAV version {av.__version__}")
        audio = interview.decode_audio_file(path)
    except Exception as exc:
        print(BAD, f"could not decode: {exc}")
        print("        Fix: record again in Chrome or Edge (they save webm/opus, which this reads).")
        return
    seconds = len(audio) / 16000
    peak = float(abs(audio).max()) if len(audio) else 0.0
    print(OK, f"{seconds:.1f} seconds of audio")
    if peak < 0.01:
        print(BAD, f"the recording is SILENT (peak level {peak:.4f}).")
        print("        The wrong microphone is selected (often a virtual one), or the mic is muted.")
        print("        Fix: Windows Settings > System > Sound > Input: choose your laptop microphone and speak -")
        print("        the bar must move. Then pick the same microphone in the app's Microphone list.")
        return
    quality = "good" if peak > 0.1 else "quiet - speak closer or raise the input volume"
    print(OK, f"peak level {peak:.3f} ({quality})")

    print("5/5  Transcribing")
    start = time.time()
    result = interview.transcribe(path)
    took = time.time() - start
    if result.get("transcript"):
        print(OK, f"done in {took:.1f} s")
        print(f"        Text:   {result['transcript'][:300]}")
        print(f"        Speech: {result['speech']}")
        print("\nSpeech-to-text works on this file.")
    else:
        print(BAD, f"{result.get('error')}: {result.get('detail')}")


if __name__ == "__main__":
    main()
