import os
import time
import logging
import threading

logger = logging.getLogger("jarvis.speech.playback")

_lock = threading.Lock()
_playback_event = threading.Event()
_playback_event.set()  # starts in "not playing" state (set = done)
_is_playing = False
_playing_files: list = []


def stop_sound() -> None:
    """Immediately stop any playing sound and schedule temporary WAV cleanup."""
    global _is_playing
    try:
        import sounddevice as sd
        sd.stop()
    except Exception as e:
        logger.debug("Error stopping sounddevice: %s", e)

    with _lock:
        _is_playing = False
        files_to_clean = list(_playing_files)
        _playing_files.clear()

    # Signal waiters that playback is done
    _playback_event.set()

    # Clean up temp files
    for path in files_to_clean:
        if os.path.exists(path):
            for _ in range(5):
                try:
                    os.remove(path)
                    break
                except OSError:
                    time.sleep(0.05)


def play_wav_async(path: str) -> None:
    """Play a WAV file asynchronously. The event is cleared BEFORE the thread
    starts so wait_for_playback() is safe to call immediately after this."""
    global _is_playing

    # Stop any currently playing sound first
    stop_sound()

    try:
        import soundfile as sf
        abs_path = os.path.abspath(path)
        data, fs = sf.read(abs_path)

        with _lock:
            _playing_files.append(abs_path)
            _is_playing = True

        # Clear BEFORE spawning the thread — eliminates the TOCTOU race
        _playback_event.clear()

        def _play_thread():
            global _is_playing
            try:
                import sounddevice as sd
                sd.play(data, fs)
                sd.wait()
            except Exception as e:
                logger.debug("Playback interrupted: %s", e)
            finally:
                with _lock:
                    _is_playing = False
                    files_to_clean = list(_playing_files)
                    _playing_files.clear()
                _playback_event.set()
                for p in files_to_clean:
                    if os.path.exists(p):
                        for _ in range(5):
                            try:
                                os.remove(p)
                                break
                            except OSError:
                                time.sleep(0.05)

        threading.Thread(target=_play_thread, daemon=True).start()

    except Exception as e:
        logger.warning("Failed to play sound asynchronously: %s", e)
        with _lock:
            _is_playing = False
        _playback_event.set()


def wait_for_playback(timeout: float = 60.0) -> None:
    """Block until the currently playing sound finishes.

    Safe against the TOCTOU race: the event is cleared before the playback
    thread starts, so calling this immediately after play_wav_async() always
    waits for the full audio duration.

    Args:
        timeout: Maximum seconds to wait (default 60s safety cap).
    """
    _playback_event.wait(timeout=timeout)
