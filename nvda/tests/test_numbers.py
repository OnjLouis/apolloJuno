import importlib
from pathlib import Path
import sys
import types
import unittest

root = Path(__file__).resolve().parents[1] / 'addon/synthDrivers/apolloJuno'
package = types.ModuleType('apollo_number_test')
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
numbers = importlib.import_module(package.__name__ + '._numbers')


class NumberTests(unittest.TestCase):
    def test_plain_numbers(self):
        for text, expected in (
            ('123', 'one hundred and twenty three'), ('1,234', 'one thousand, two hundred and thirty four'),
            ('-42', 'minus forty two'), ('+7', 'plus seven'), ('0', 'zero'),
            ('3.05', 'three point zero five'), ('0.00', 'zero point zero zero'),
            ('21st', 'twenty first'), ('12th', 'twelfth'), ('1. First item.', 'one. First item.'),
        ):
            with self.subTest(text=text):
                self.assertEqual(numbers.expand_numbers(text), expected)

    def test_structured_identifiers_remain_unchanged(self):
        for text in ('00123', '192.168.0.1', 'v1.2', 'version 1.2', '1.2.3',
                     '20/10/2026', '2026-10-20', 'AB123', 'B2B',
                     '+44 7911 123456', '020 7946 0123', '123-456-7890',
                     'https://example.org/123', 'user123@example.org', '12,34',
                     '12st', '123456789012345678901234567890'):
            with self.subTest(text=text):
                self.assertEqual(numbers.expand_numbers(text), text)

    def test_24_hour_times(self):
        for text, expected in (
            ('16:30:29', 'sixteen thirty and twenty nine seconds'),
            ('23:06:03', 'twenty three oh six and three seconds'),
            ('09:05', 'nine oh five'), ('00:00', 'zero hundred'),
            ('12:00', 'twelve hundred'), ('07:00:01', 'seven hundred and one second'),
            ('16:30:00', 'sixteen thirty and zero seconds'),
            ('It is 16:30:29.', 'It is sixteen thirty and twenty nine seconds.'),
        ):
            with self.subTest(text=text):
                self.assertEqual(numbers.expand_numbers(text), expected)

    def test_invalid_and_embedded_times_are_preserved(self):
        for text in ('24:00', '12:60', '12:30:99', '123:45', '12:34:56:78',
                     'https://example.org/16:30:29', r'C:\logs\16:30:29.txt',
                     'ID16:30', '16:30ID'):
            with self.subTest(text=text):
                self.assertEqual(numbers.expand_numbers(text), text)

    def test_pre_symbol_filter_only_expands_times(self):
        self.assertEqual(numbers.expand_times('123 at 16:30:29 https://example.org/16:30:29'),
                         '123 at sixteen thirty and twenty nine seconds https://example.org/16:30:29')

    def test_context_and_safety(self):
        self.assertEqual(numbers.expand_numbers('There are 42 items and 3.05 litres.'),
                         'There are forty two items and three point zero five litres.')
        self.assertEqual(numbers.expand_numbers('See https://example.org/123 then read 42.'),
                         'See https://example.org/123 then read forty two.')
        value = '0' * 10000
        self.assertEqual(numbers.expand_numbers(value), value)
