import array
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import threading
import unittest


PATH = Path(__file__).resolve().parents[1]/'addon/synthDrivers/apolloJuno/_host.py'
spec = importlib.util.spec_from_file_location('apollo_host_test', PATH)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
HOST = os.environ['APOLLO_TEST_HOST']


class HostTests(unittest.TestCase):
    def test_sustained_shout_keeps_juno_later_stress(self):
        samples = array.array('h', self.render('Fwaaaaaaaaaaaaaaaaaaaaaaaaaa!', (5, 8, 7, 100)))
        window = samples[3500:6500]
        values = [value-sum(window)/len(window) for value in window]
        def correlation(lag):
            a, b = values[:-lag], values[lag:]
            return sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))
        lag = max(range(46, 126), key=correlation)
        self.assertGreater(10000/lag, 135, 'Sustained stressed vowel falls back to the flat baseline')
        self.assertLess(10000/lag, 175)

    def setUp(self):
        self.host = host.Host(HOST)
        self.host.start()
        self.stopping = threading.Event()

    def tearDown(self):
        process = self.host._session.process if self.host._session else None
        self.host.stop()
        if process:
            self.assertIsNotNone(process.poll())

    def render(self, text='This is a test.', settings=(3, 8, 3, 100)):
        return b''.join(self.host.render(settings, text, self.stopping))

    def test_reuses_one_helper_with_deterministic_pcm(self):
        pid = self.host.pid
        audio = self.render()
        self.assertTrue(any(audio))
        self.assertEqual(len(audio) % 2, 0)
        for _ in range(12):
            self.assertEqual(self.render(), audio)
            self.assertEqual(self.host.pid, pid)

    def test_volume_scales_only_pcm(self):
        full = array.array('h', self.render())
        half = array.array('h', self.render(settings=(3, 8, 3, 50)))
        muted = self.render(settings=(3, 8, 3, 0))
        self.assertTrue(all(abs(2*h-f) <= 1 for h, f in zip(half, full)))
        self.assertEqual(len(half), len(full))
        self.assertEqual(muted, bytes(len(full)*2))

    def test_accepted_sound_references(self):
        references = (
            ('It is a warm afternoon. A spoon in the room. Boom, moon, and noon!', 0,
             '4622424232db2f83043ffcf97f296d6c85a1807f7210bc7421f767d5f5bc5eca'),
            ('Morning. Evening. Humming. Ringing. Singing.', 0,
             'ba5c6feef843cb29fa60e6d729f1556cd3933660e07bc8843e8cb4d8cd25e5aa'),
            ('Good morning! Good evening?', 7,
             '3bc1632d3460a3481bbfcec16a6794b8b8fa602a12ac62235673c6fced06d9af'),
            ('Wo wo? Wo wo! Oh no? Oh no!', 7,
             '1baac760e544b1fbaf2c4a446016e6ee0e28f49f7159332c4e8173bd9437dc38'),
        )
        for text, intonation, digest in references:
            with self.subTest(text=text):
                self.assertEqual(hashlib.sha256(self.render(text, (5, 8, intonation, 100))).hexdigest(), digest)

    def test_juno_pronunciation_references(self):
        references = (
            ('1', '4282067d64e74cba965972142696abe111d8de3199521b59ff4d18c6183792a2'),
            ('sample', 'ec09710f0b79994a34991465bde84b3adea7316acc1450d8973fe30152f2ba96'),
            ('samples', 'a1632add77bca6ea93babf18a8e4b5298ff20d8c017f25e6f544acc389bf439d'),
            ('sampling', '6f85df133a218e50c47f242efe46cb516e3c8d662bf159b9b08a3248dbd77f9a'),
        )
        for text, digest in references:
            with self.subTest(text=text):
                self.assertEqual(hashlib.sha256(self.render(text, (5, 8, 0, 100))).hexdigest(), digest)

    def test_terminal_and_says_use_the_short_vowels(self):
        references = (
            ('terminal', '0571beedd0e439ab76429e1c3fa93ee0ccbf4227edc2eef539a9533fd6a56039'),
            ('terminals', 'b39f13706ddd73a9e9c450ba2098abad0af519531e597569557463cd88696dcd'),
            ('terminally', '72ff4e83bba60d3a4a1a8fe4e132883f0ec4cfb150ec013feba6e4b746b5bf11'),
            ('says', 'e0c527736d7ce0d50ae71ac3ebde9130e72f3cc1e82a8c7d79d641c0c215abea'),
        )
        for text, digest in references:
            with self.subTest(text=text):
                self.assertEqual(hashlib.sha256(self.render(text, (5, 8, 0, 100))).hexdigest(), digest)

    def test_pronunciation_corrections_do_not_change_related_long_vowels(self):
        references = (
            ('say', '01a2ec8aa75e446018ccea79ba09b91a700b9dd2da46112829ee5156856817ba'),
            ('saying', '1488b6fe23d0e3a8b053446ec93d79faab974976c15b332777488778204ab680'),
            ('essays', '5751069f81def3a6b8625bcaa9a85609c4bae8d138fe9ccb2791659554d5f918'),
            ('final', 'ddd0111c3aa30fe8a509595aa799901eca51aec4592959326fbe998721859a2b'),
            ('mine', '4ef76c531229ddd33fbbb8ad005ecf57150e81399623d0a3b588ffa585642a80'),
            ('terminate', 'c9783c04d999ae8a42bf89fa2fc5b1f9cdddd7f053aad1493de34075dd7ef2fe'),
        )
        for text, digest in references:
            with self.subTest(text=text):
                self.assertEqual(hashlib.sha256(self.render(text, (5, 8, 0, 100))).hexdigest(), digest)

    def test_tone_controls_change_only_pcm_not_length(self):
        normal = self.render()
        self.assertEqual(normal, self.render(settings=(3, 8, 3, 100, 50, 50)))
        for bass, treble in ((0, 50), (100, 50), (50, 0), (50, 100), (100, 100)):
            with self.subTest(bass=bass, treble=treble):
                audio = self.render(settings=(3, 8, 3, 100, bass, treble))
                self.assertEqual(len(audio), len(normal))
                self.assertNotEqual(audio, normal)
                samples = array.array('h', audio)
                self.assertLess(max(map(abs, samples)), 27600)
        with self.assertRaises(host.HostError):
            self.render(settings=(3, 8, 3, 100, 50, 101))
        self.assertTrue(any(self.render()))

    def test_rate_pitch_and_intonation_change_audio(self):
        normal = self.render()
        self.assertNotEqual(normal, self.render(settings=(7, 8, 3, 100)))
        self.assertNotEqual(normal, self.render(settings=(3, 4, 3, 100)))
        self.assertNotEqual(self.render('Anna may know?', (3, 8, 0, 100)),
                            self.render('Anna may know?', (3, 8, 7, 100)))

    def test_invalid_input_recovers_without_replacing_helper(self):
        pid = self.host.pid
        for text in ('@F0 test', '_M_EE_M', 'bad\x00text'):
            with self.assertRaises(host.HostError):
                self.render(text)
            self.assertTrue(any(self.render()))
            self.assertEqual(self.host.pid, pid)

    def test_fast_rates_retain_the_intonation_observed_on_juno(self):
        text = 'Anna may know?'
        normal = self.render(text, (3, 8, 7, 100))
        for rate, former_limit in ((5, 4), (6, 2), (7, 0)):
            with self.subTest(rate=rate):
                self.assertFalse(self.render(text, (rate, 8, 7, 100)) ==
                                 self.render(text, (rate, 8, former_limit, 100)),
                                 'High-rate intonation still uses the older firmware limit')
        self.assertEqual(self.render(text, (3, 8, 7, 100)), normal)

    def test_fast_rate_intonation_caps_match_measured_juno_limits(self):
        text = 'Anna may know?'
        for rate, limit in ((5, 6), (6, 5), (7, 4), (8, 2), (9, 0)):
            with self.subTest(rate=rate):
                maximum = self.render(text, (rate, 8, 7, 100))
                capped = self.render(text, (rate, 8, limit, 100))
                self.assertTrue(maximum == capped, 'Measured cap does not match rendered PCM')
                if limit:
                    self.assertFalse(maximum == self.render(text, (rate, 8, limit-1, 100)),
                                     'Intonation below the cap should remain adjustable')

    def test_short_exclamations_start_high_and_fall_like_juno(self):
        def frequency(samples, start, end):
            window = samples[round(start*host.SAMPLE_RATE):round(end*host.SAMPLE_RATE)]
            mean = sum(window)/len(window)
            values = [value-mean for value in window]
            def correlation(lag):
                pairs = list(zip(values[:-lag], values[lag:]))
                return sum(a*b for a, b in pairs)/math.sqrt(
                    sum(a*a for a, b in pairs)*sum(b*b for a, b in pairs))
            # The controlled probes stay between 80 and 220 Hz; exclude doubled periods.
            lag = max(range(round(host.SAMPLE_RATE/220), round(host.SAMPLE_RATE/80)+1), key=correlation)
            return host.SAMPLE_RATE/lag
        for text, tail in (('Wo wo!', (.26, .33)), ('Oh no!', (.20, .27))):
            with self.subTest(text=text):
                samples = array.array('h', self.render(text, (5, 8, 7, 100)))
                first = frequency(samples, .07, .14)
                last = frequency(samples, *tail)
                self.assertGreater(first, 140, 'Missing high initial exclamation stress')
                self.assertGreater(first/last, 1.08, 'Exclamation should fall, not rise')

    def test_invalid_setting_recovers(self):
        with self.assertRaises(host.HostError):
            self.render(settings=(0, 8, 3, 100))
        self.assertTrue(any(self.render()))

    def test_payload_limit_rejected_before_send(self):
        with self.assertRaises(host.HostError):
            self.render('a'*321)
        self.assertTrue(any(self.render()))

    def test_request_identifier_wraps_without_zero(self):
        self.host._next_request = 0xfffffffe
        self.assertTrue(any(self.render()))
        self.assertTrue(any(self.render()))
        self.assertEqual(self.host._next_request, 1)

    def test_numbered_text_continues(self):
        short = self.render('1.')
        long = self.render('1. First item. 2. Second item. The final sentence finishes here.')
        self.assertGreater(len(long), len(short)*3)

    def test_high_pitch_does_not_clip_or_stop_speech(self):
        audio = self.render('The quick brown fox jumps over the lazy dog! What is the time?',
                            (1, 15, 3, 100))
        values = array.array('h', audio)
        self.assertTrue(any(values))
        self.assertGreater(min(values), -32768)
        self.assertLess(max(values), 32767)

    def test_malformed_header_stops_only_helper(self):
        process = self.host._session.process
        process.stdin.write(host.HEADER.pack(b'FAIL', host.SPEAK, 1, 0))
        self.assertEqual(process.wait(timeout=2), 2)

    def test_truncated_header_exits(self):
        process = self.host._session.process
        process.stdin.write(b'AP')
        process.stdin.close()
        self.assertEqual(process.wait(timeout=2), 2)


if __name__ == '__main__':
    unittest.main()
