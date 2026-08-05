"""Tests for streaming LLM response -> TTS speaker pipeline."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.speech.streaming_llm import _should_feed


class TestStreamingLLM(unittest.TestCase):

    def test_should_feed_sentence_end(self):
        self.assertTrue(_should_feed("Hello sir.", "."))
        self.assertTrue(_should_feed("What is next?", "?"))
        self.assertTrue(_should_feed("Done!", "!"))

    def test_should_feed_incomplete(self):
        self.assertFalse(_should_feed("Hello sir", "r"))
        self.assertFalse(_should_feed("Processing data", "a"))
        self.assertFalse(_should_feed("Short phrase,", ","))

    def test_should_feed_long_comma_clause(self):
        long_buf = "I have finished analyzing the primary parameters and dependencies, "
        self.assertTrue(_should_feed(long_buf, ","))


if __name__ == "__main__":
    unittest.main()
