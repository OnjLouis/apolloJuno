import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1]/'addon/synthDrivers/apolloJuno/_inline.py'
spec = importlib.util.spec_from_file_location('apollo_inline_test', PATH)
inline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inline)


class InlineTests(unittest.TestCase):
    def test_markers_are_explicit_and_case_insensitive(self):
        self.assertEqual(list(inline.tokens('Normal {{ @w9 }}fast{{reset}} normal @F0.')),
                         [('text', 'Normal '), ('command', '@W9'), ('text', 'fast'),
                          ('command', 'reset'), ('text', ' normal @F0.')])

    def test_invalid_unsupported_nested_and_truncated_markers_stay_literal(self):
        for value in ('{{@J}}', '{{@W0}}', '{{@W10}}', '{{@M16}}', '{{@$1}}', '{{@V0}}',
                      '{{@F8 @W9}}', '{{{@W9}}}', '{{@W9', '{{@U0F+}}', '{{@RZFF}}',
                      '{{outer {{@T0}} words}}', '{{outer {{@T0}} {{@T1}} words}}',
                      '{{unfinished {{@T0}}', '{{\n@T0}}'):
            with self.subTest(value=value):
                self.assertEqual(list(inline.tokens(value)), [('text', value)])

    def test_effects_and_supported_ranges(self):
        for value in ('@W1', '@W9', '@F0', '@FF', '@F+', '@F-', '@R0', '@R7', '@Q9',
                      '@DF', '@B1', '@B8', '@K1', '@V6', '@S1', '@P0', '@H1',
                      '@U010+', '@U9FF-', '@A0', '@AF', '@T0', '@TF', '@TX'):
            self.assertEqual(inline.validate(value), value)

    def test_volume_is_relative_and_state_is_bounded(self):
        state = inline.State()
        for _ in range(1000):
            state.apply('@W9')
            state.apply('@FF')
        state.apply('@A5')
        self.assertEqual(state.level, 5)
        self.assertEqual(state.prefix(), '@W9 @FF')
        self.assertEqual(inline.State(state.snapshot()).snapshot(), state.snapshot())
        state.apply('reset')
        self.assertEqual(state.snapshot(), ())
        self.assertEqual(state.level, 15)

    def test_presets_replace_only_the_attributes_they_actually_reset(self):
        state = inline.State(('@W9', '@F0', '@F+', '@K1', '@B1', '@U010+', '@Q9', '@A5'))
        state.apply('@V2')
        self.assertEqual(state.snapshot(), ('@W9', '@F+', '@Q9', '@V2', '@A5'))
        self.assertEqual(state.prefix(4), '@W9 @F+ @Q9 @V2 @FA @F+')
        state.apply('@F3')
        state.apply('@F-')
        self.assertEqual(state.prefix(4), '@W9 @Q9 @V2 @F3 @F- @F7 @F-')

    def test_snapshots_cannot_contain_effects_or_unvalidated_commands(self):
        for command in ('@T0', '@J', '@W0', '@A100', 'arbitrary'):
            with self.assertRaises(ValueError):
                inline.State((command,))


if __name__ == '__main__':
    unittest.main()
