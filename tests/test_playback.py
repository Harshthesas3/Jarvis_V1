import sys
import os
import unittest
import time

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

try:
    from jarvis.speech.playback import play_wav_async, stop_sound, wait_for_playback
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

class TestPlayback(unittest.TestCase):
    @unittest.skipUnless(HAS_AUDIO, "Audio dependencies (soundfile/sounddevice) not installed in system Python environment")
    def test_wait_when_not_playing(self):
        # Should return immediately without hanging
        wait_for_playback(timeout=1.0)
        self.assertTrue(True)

    @unittest.skipUnless(HAS_AUDIO, "Audio dependencies (soundfile/sounddevice) not installed in system Python environment")
    def test_stop_sound(self):
        stop_sound()
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
