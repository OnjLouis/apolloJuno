import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1]/'addon/synthDrivers/apolloJuno/_text.py'
spec = importlib.util.spec_from_file_location('apollo_text', PATH)
text = importlib.util.module_from_spec(spec)
spec.loader.exec_module(text)


class TextTests(unittest.TestCase):
    def test_default_controls_match_reference(self):
        self.assertEqual(text.native_rate(50), 3)
        self.assertEqual(text.native_pitch(50), 8)
        self.assertEqual(text.native_intonation(43), 3)

    def test_controls_are_bounded_and_monotonic(self):
        for function, low, high in ((text.native_rate, 1, 9), (text.native_pitch, 0, 15),
                                    (text.native_intonation, 0, 7)):
            values = [function(v) for v in range(-5, 106)]
            self.assertEqual(values, sorted(values))
            self.assertEqual((values[0], values[-1]), (low, high))

    def test_numbers_and_punctuation_preserved(self):
        value = '1. First item. 23:06:03! Anna may know?'
        self.assertEqual(list(text.chunks(value)), [value])

    def test_plain_text_cannot_inject_engine_commands(self):
        value = text.clean_text('@F0 _M_EE_M \x1b\x00')
        self.assertNotIn('@', value)
        self.assertNotIn('_', value)
        self.assertTrue(all(32 <= ord(c) <= 126 for c in value))

    def test_smart_punctuation_does_not_become_question_marks(self):
        self.assertEqual(text.clean_text('caf\u00e9\u2019s\u2014test\u2026'), "cafe's-test...")

    def test_long_text_retains_all_words(self):
        value = ' '.join('word'+str(i) for i in range(300))
        parts = list(text.chunks(value))
        self.assertEqual(' '.join(parts), value)
        self.assertTrue(all(len(p.encode('ascii')) <= text.MAX_TEXT_BYTES for p in parts))

    def test_long_unbroken_text_is_not_truncated(self):
        value = 'a'*(text.MAX_TEXT_BYTES*3+1)
        parts = list(text.chunks(value))
        self.assertEqual(''.join(parts), value)
        self.assertTrue(all(len(p) <= text.MAX_TEXT_BYTES for p in parts))

    def test_blank_input_is_empty(self):
        self.assertEqual(list(text.chunks(' \r\n\t ')), [])


if __name__ == '__main__':
    unittest.main()
