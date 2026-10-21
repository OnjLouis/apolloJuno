from collections import deque
import importlib.util
import os
from pathlib import Path
import sys
import threading
import time
import types
import unittest


class AutoProperties:
    def __getattr__(self, name):
        method = getattr(type(self), '_get_'+name, None)
        if method:
            return method(self)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        method = getattr(type(self), '_set_'+name, None) if not name.startswith('_') else None
        if method:
            method(self, value)
        else:
            object.__setattr__(self, name, value)

    def terminate(self):
        pass

    @staticmethod
    def VoiceSetting():
        return Setting('voice')

    @staticmethod
    def RateSetting():
        return Setting('rate')

    @staticmethod
    def PitchSetting():
        return Setting('pitch')

    @staticmethod
    def VolumeSetting():
        return Setting('volume')


class Setting:
    def __init__(self, id, *args, **kwargs):
        self.id = id
        self.__dict__.update(kwargs)


class Action:
    def __init__(self):
        self.calls = []
        self.handler = None

    def notify(self, **kwargs):
        self.calls.append(kwargs)
        if self.handler:
            self.handler(**kwargs)


class IndexCommand:
    def __init__(self, index):
        self.index = index


class PitchCommand:
    def __init__(self, offset=0):
        self.newValue = 50 + offset


class SynthCommand:
    pass


class SynthParamCommand(SynthCommand):
    isDefault = False


class CharacterModeCommand(SynthParamCommand):
    def __init__(self, state):
        self.state = state


class Player:
    def __init__(self, *args, **kwargs):
        self.queue = deque()
        self.lock = threading.Lock()
        self.paused = False
        self.closed = False
        self.stops = 0
        self.block = False
        self.entered = threading.Event()
        self.release = threading.Event()
        self.played = []
        self.auto_drain = False
        self.idle_entered = threading.Event()

    def idle(self):
        # NVDA pumps final callbacks while draining, not from a background thread.
        self.idle_entered.set()
        while True:
            with self.lock:
                if not self.queue:
                    return
            if not self.auto_drain or not self.play_one():
                time.sleep(.002)

    def feed(self, data, size=None, onDone=None):
        if self.block and data:
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError('Test feed barrier timed out')
        with self.lock:
            self.queue.append((data, onDone))

    def stop(self):
        self.stops += 1
        self.paused = False
        with self.lock:
            self.queue.clear()

    def pause(self, switch):
        self.paused = switch

    def close(self):
        self.stop()
        self.closed = True

    def play_one(self):
        with self.lock:
            if self.paused or not self.queue:
                return False
            data, callback = self.queue.popleft()
        if data:
            self.played.append(data)
        if callback:
            callback()
        return True


done, index = Action(), Action()
errors = []
fake_log = types.SimpleNamespace(error=lambda *args, **kwargs: errors.append(args[0]),
                                 debug=lambda *args, **kwargs: None)
modules = {
    'config': types.SimpleNamespace(conf={'audio': {'outputDevice': 'default'}}),
    'nvwave': types.SimpleNamespace(WavePlayer=Player),
    'autoSettingsUtils': types.ModuleType('autoSettingsUtils'),
    'autoSettingsUtils.driverSetting': types.SimpleNamespace(NumericDriverSetting=Setting, BooleanDriverSetting=Setting),
    'logHandler': types.SimpleNamespace(log=fake_log),
    'speech': types.ModuleType('speech'),
    'speech.commands': types.SimpleNamespace(IndexCommand=IndexCommand, PitchCommand=PitchCommand,
        CharacterModeCommand=CharacterModeCommand, SynthCommand=SynthCommand, SynthParamCommand=SynthParamCommand),
    'synthDriverHandler': types.SimpleNamespace(SynthDriver=AutoProperties,
        VoiceInfo=lambda *args, **kwargs: kwargs, synthDoneSpeaking=done, synthIndexReached=index),
}
sys.modules.update(modules)
PATH = Path(__file__).resolve().parents[1]/'addon/synthDrivers/apolloJuno'
spec = importlib.util.spec_from_file_location('apolloJuno', PATH/'__init__.py', submodule_search_locations=[str(PATH)])
driver = importlib.util.module_from_spec(spec)
sys.modules['apolloJuno'] = driver
spec.loader.exec_module(driver)
RealHost = driver.Host
driver.Host = lambda: RealHost(os.environ['APOLLO_TEST_HOST'])


def wait_for(predicate, seconds=3, tick=None):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if tick:
            tick()
        if predicate():
            return
        time.sleep(.002)
    raise AssertionError('Asynchronous test deadline expired')


class DriverTests(unittest.TestCase):
    voice = 'uk'

    def test_inline_commands_are_opt_in_and_do_not_leak_to_next_job(self):
        self.assertFalse(self.synth.inlineCommands)
        self.synth.inlineCommands = True
        captured = []
        original = self.synth._host.render_inline
        def capture(settings, prefix, level, text, effect, stopping):
            captured.append((prefix, level, text, effect))
            return original(settings, prefix, level, text, effect, stopping)
        self.synth._host.render_inline = capture
        self.synth.speak(['{{@F0}}Low.{{@A5}}Quiet.{{@T0}}{{reset}}Normal.', IndexCommand(1)])
        self.ready()
        self.drain()
        self.assertEqual(captured, [('@F0',15,'Low.',255), ('@F0',5,'Quiet.',255), ('@F0',5,'',0)])
        self.assertEqual((self.synth.pitch, self.synth.volume), (50,100))
        self.synth.speak(['Next.', IndexCommand(2)])
        self.ready()
        self.drain()
        self.assertEqual(len(captured),3)

    def test_inline_preprocessing_preserves_spelling_indexes_and_reset(self):
        from apolloJuno._commands import prepare_sequence, InlineStateCommand, InlineEffectCommand
        spelling = [CharacterModeCommand(True), '{{@F0}}', CharacterModeCommand(False)]
        self.assertIs(prepare_sequence(spelling), spelling)
        marker = IndexCommand(88)
        sequence = prepare_sequence(['{{@F0}}One.', marker, '{{@T1}}Two.'])
        self.assertIsInstance(sequence[0], InlineStateCommand)
        self.assertIs(sequence[2], marker)
        self.assertIsInstance(sequence[3], InlineEffectCommand)
        self.assertTrue(sequence[-1].isDefault)
        self.synth.inlineCommands = True
        self.synth.speak(sequence)
        self.ready()
        self.drain()
        self.assertEqual([call['index'] for call in index.calls], [88])

    def test_inline_state_survives_text_chunks_and_capital_pitch_changes(self):
        self.synth.inlineCommands = True
        captured=[]
        original=self.synth._host.render_inline
        def capture(settings,prefix,level,text,effect,stopping):
            captured.append((prefix,level,text))
            return original(settings,prefix,level,text,effect,stopping)
        self.synth._host.render_inline=capture
        self.synth.speak(['{{@F3}}{{@A5}}'+'Several words. '*50,
                          IndexCommand(1),PitchCommand(30),'Capital.',PitchCommand(),'Normal.'])
        self.ready()
        self.drain()
        self.assertGreater(len(captured),3)
        self.assertTrue(all(prefix=='@F3' and level==5 for prefix,level,text in captured[:-2]))
        self.assertEqual(captured[-2][0], '@F3 @F7')
        self.assertEqual(captured[-1][0], '@F3')
        self.assertEqual([call['index'] for call in index.calls],[1])

    def test_inline_disabled_input_and_plain_enabled_input_keep_old_audio(self):
        captured=[]
        original=self.synth._host.render
        def capture(settings,text,stopping):
            captured.append(text)
            return original(settings,text,stopping)
        self.synth._host.render=capture
        self.synth.speak(['{{@T0}} @W9'])
        self.ready()
        self.drain()
        self.assertIn('at T0',captured[-1])
        self.synth.inlineCommands=True
        self.synth.speak(['Ordinary speech.'])
        self.ready()
        self.drain()
        self.assertEqual(captured[-1],'Ordinary speech.')

    def test_inline_cancel_does_not_leak_state_or_restart_helper(self):
        self.synth.inlineCommands=True
        pid=self.synth._host.pid
        player=self.synth._player
        player.block=True
        self.synth.speak(['{{@F0}}{{@A0}}Old.',IndexCommand(1)])
        self.assertTrue(player.entered.wait(2))
        self.synth.cancel()
        player.block=False
        player.release.set()
        self.synth.speak(['New.',IndexCommand(2)])
        self.ready()
        self.drain()
        self.assertEqual([call['index'] for call in index.calls],[2])
        self.assertTrue(any(b''.join(player.played)))
        self.assertEqual(self.synth._host.pid,pid)

    def test_inline_sequence_snapshots_survive_manager_parameter_replay(self):
        from apolloJuno._commands import prepare_sequence, InlineStateCommand
        sequence=prepare_sequence(['{{@W9}}Fast.','{{@F0}}Low.','{{@A5}}Quiet.'])
        commands=[item for item in sequence if isinstance(item,InlineStateCommand)]
        self.assertEqual(commands[2].commands,('@W9','@F0','@A5'))
        self.assertTrue(commands[-1].isDefault)
        self.assertIs(prepare_sequence(sequence),sequence)
        self.assertEqual(prepare_sequence(iter(['Unchanged.'])), ['Unchanged.'])
        self.synth.inlineCommands=True
        captured=[]
        original=self.synth._host.render_inline
        def capture(settings,prefix,level,text,effect,stopping):
            captured.append((prefix,level,text))
            return original(settings,prefix,level,text,effect,stopping)
        self.synth._host.render_inline=capture
        # NVDA replays the full last parameter command when it splits an utterance.
        self.synth.speak([commands[1],'Later.',IndexCommand(1)])
        self.ready()
        self.drain()
        self.assertEqual(captured,[('@W9 @F0',15,'Later.')])



    def test_voice_selection_preserves_controls_and_rejects_unknown_ids(self):
        self.assertIn('voice', [setting.id for setting in self.synth.supportedSettings])
        self.assertEqual(list(self.synth.availableVoices), ['uk', 'apollo'])
        self.assertEqual(self.synth.voice, self.voice)
        self.synth.rate, self.synth.pitch, self.synth.intonation = 65, 35, 100
        self.synth.volume, self.synth.bass, self.synth.treble = 42, 60, 40
        for selected in ('apollo', 'uk', 'apollo'):
            self.synth.voice = selected
            self.assertEqual(self.synth.voice, selected)
            self.assertEqual((self.synth.rate, self.synth.pitch, self.synth.intonation,
                              self.synth.volume, self.synth.bass, self.synth.treble),
                             (65, 35, 100, 42, 60, 40))
        with self.assertRaises(ValueError):
            self.synth.voice = 'unknown'
        self.assertEqual(self.synth.voice, 'apollo')

    def test_queued_speech_keeps_its_selected_profile(self):
        rendered = []
        original = self.synth._host.render
        def capture(settings, text, stopping):
            rendered.append((settings[-1], text))
            return original(settings, text, stopping)
        self.synth._host.render = capture
        self.synth._player.block = True
        self.synth.voice = 'uk'
        self.synth.speak(['First.', IndexCommand(1)])
        self.assertTrue(self.synth._player.entered.wait(2))
        self.synth.voice = 'apollo'
        self.synth.speak(['Second.', IndexCommand(2)])
        self.synth.voice = 'uk'
        self.synth.speak(['Third.', IndexCommand(3)])
        self.synth._player.block = False
        self.synth._player.release.set()
        self.ready()
        self.drain()
        self.assertEqual(rendered, [(0, 'First.'), (1, 'Second.'), (0, 'Third.')])

    def test_number_expansion_is_opt_in_and_preserves_identifiers(self):
        self.assertFalse(self.synth.readNumbers)
        captured = []
        original = self.synth._host.render
        def capture(settings, text, stopping):
            captured.append(text)
            return original(settings, text, stopping)
        self.synth._host.render = capture
        self.synth.speak(['There are 123 items.'])
        wait_for(lambda: self.synth._jobs.unfinished_tasks == 0)
        self.assertEqual(captured.pop(), 'There are 123 items.')
        self.drain()
        done.calls.clear()
        self.synth.readNumbers = True
        self.synth.speak(['There are 123 items. IP 192.168.0.1.'])
        wait_for(lambda: self.synth._jobs.unfinished_tasks == 0)
        self.assertEqual(captured.pop(), 'There are one hundred and twenty three items. IP 192.168.0.1.')
        self.drain()

    def test_capital_pitch_command_changes_only_the_requested_fragment(self):
        self.assertIn(PitchCommand, self.synth.supportedCommands)
        rendered = []
        original = self.synth._host.render
        def capture(settings, text, stopping):
            rendered.append((settings, text))
            return original(settings, text, stopping)
        self.synth._host.render = capture
        self.synth.speak(['a', PitchCommand(30), 'A', PitchCommand(), 'a', IndexCommand(1)])
        wait_for(lambda: self.synth._jobs.unfinished_tasks == 0)
        self.assertEqual([settings[1] for settings, text in rendered], [8, 12, 8])
        self.assertEqual(self.synth.pitch, 50)

    def setUp(self):
        done.calls.clear()
        index.calls.clear()
        done.handler = index.handler = None
        errors.clear()
        self.synth = driver.SynthDriver()
        self.synth.voice = self.voice

    def tearDown(self):
        player = self.synth._player
        player.release.set()
        process = self.synth._host._session.process if self.synth._host._session else None
        reader = self.synth._host._session.reader if self.synth._host._session else None
        self.synth.terminate()
        self.assertFalse(self.synth._worker.is_alive())
        if process:
            self.assertIsNotNone(process.poll())
            self.assertFalse(reader.is_alive())
        self.assertTrue(player.closed)

    def ready(self):
        wait_for(lambda: self.synth._jobs.unfinished_tasks == 0)

    def drain(self):
        wait_for(lambda: bool(done.calls), tick=self.synth._player.play_one)

    def test_indexes_and_done_follow_playback(self):
        self.synth.speak(['First.', IndexCommand(1), 'Second.', IndexCommand(2)])
        self.ready()
        self.assertEqual(index.calls, [])
        self.assertEqual(done.calls, [])
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], [1, 2])
        self.assertEqual(len(done.calls), 1)

    def test_spelling_including_spaces_and_punctuation_completes(self):
        pieces = ['1', 'dot', 'space', 'A', 'n', 'd', 'r', 'e', 'space', 'L', 'o', 'u', 'i', 's']
        events = []
        for number, part in enumerate(pieces):
            events.extend((part, IndexCommand(number)))
        self.synth.speak(events)
        self.ready()
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], list(range(len(pieces))))
        self.assertGreaterEqual(len(self.synth._player.played), len(pieces))

    def test_say_all_queues_next_line_from_playback_index(self):
        def next_line(synth, index):
            if index < 4:
                synth.speak(['Next line '+str(index+1), IndexCommand(index+1)])
        index.handler = next_line
        self.synth.speak(['First line', IndexCommand(1)])
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], [1, 2, 3, 4])

    def test_final_callbacks_are_pumped_without_an_external_playback_thread(self):
        self.synth._player.auto_drain = True
        self.synth.speak(['One.', IndexCommand(1)])
        wait_for(lambda: bool(done.calls))
        self.assertEqual([c['index'] for c in index.calls], [1])

    def test_spelling_advances_from_completion_without_external_callback_pumping(self):
        self.synth._player.auto_drain = True
        def next_letter(synth):
            if len(done.calls) < 5:
                synth.speak(['A', IndexCommand(len(done.calls)+1)])
        done.handler = next_letter
        self.synth.speak(['A', IndexCommand(1)])
        wait_for(lambda: len(done.calls) == 5)
        self.assertEqual([c['index'] for c in index.calls], [1, 2, 3, 4, 5])

    def test_say_all_advances_without_external_callback_pumping(self):
        self.synth._player.auto_drain = True
        def next_line(synth, index):
            if index < 5:
                synth.speak(['Next line.', IndexCommand(index+1)])
        index.handler = next_line
        self.synth.speak(['First line.', IndexCommand(1)])
        wait_for(lambda: len(index.calls) == 5 and bool(done.calls))
        self.assertEqual([c['index'] for c in index.calls], [1, 2, 3, 4, 5])

    def test_worker_drain_waits_for_resume(self):
        player = self.synth._player
        self.synth.pause(True)
        player.auto_drain = True
        self.synth.speak(['Paused.', IndexCommand(1)])
        self.assertTrue(player.idle_entered.wait(2))
        self.assertEqual(index.calls, [])
        self.assertEqual(done.calls, [])
        self.synth.pause(False)
        wait_for(lambda: bool(done.calls))
        self.assertEqual([c['index'] for c in index.calls], [1])

    def test_cancel_releases_worker_drain_and_preserves_replacement(self):
        player = self.synth._player
        self.synth.speak(['Old.', IndexCommand(1)])
        self.assertTrue(player.idle_entered.wait(2))
        self.synth.cancel()
        player.auto_drain = True
        self.synth.speak(['New.', IndexCommand(2)])
        wait_for(lambda: bool(done.calls))
        self.assertEqual([c['index'] for c in index.calls], [2])

    def test_cancel_filters_callbacks_already_in_flight(self):
        self.synth.speak(['Old text.', IndexCommand(1)])
        self.ready()
        callbacks = [callback for _, callback in self.synth._player.queue if callback]
        self.synth.cancel()
        for callback in callbacks:
            callback()
        self.assertEqual(index.calls, [])
        self.assertEqual(done.calls, [])
        self.synth.speak(['Replacement.', IndexCommand(2)])
        self.ready()
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], [2])

    def test_cancel_is_not_blocked_by_an_audio_feed(self):
        player = self.synth._player
        player.block = True
        self.synth.speak(['Old text.', IndexCommand(1)])
        self.assertTrue(player.entered.wait(2))
        start = time.monotonic()
        self.synth.cancel()
        self.assertLess(time.monotonic()-start, .1)
        player.block = False
        player.release.set()
        self.synth.speak(['Replacement.', IndexCommand(2)])
        self.ready()
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], [2])
        self.assertGreaterEqual(player.stops, 2)

    def test_repeated_interruptions_reuse_same_helper(self):
        pid = self.synth._host.pid
        for i in range(25):
            self.synth.speak(['Letter '+str(i), IndexCommand(i)])
            self.ready()
            self.synth.cancel()
            self.assertEqual(self.synth._host.pid, pid)
        self.synth.speak(['Final.', IndexCommand(100)])
        self.ready()
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], [100])
        self.assertEqual(errors, [])

    def test_pause_defers_indexes_until_resumed(self):
        self.synth.speak(['One line.', IndexCommand(1)])
        self.ready()
        self.synth.pause(True)
        self.assertFalse(self.synth._player.play_one())
        self.assertEqual(index.calls, [])
        self.synth.pause(False)
        self.drain()
        self.assertEqual([c['index'] for c in index.calls], [1])

    def test_settings_and_helper_recover_after_process_exit(self):
        self.synth.rate, self.synth.pitch, self.synth.volume, self.synth.intonation = 65, 35, 42, 100
        process = self.synth._host._session.process
        process.kill()
        process.wait(timeout=2)
        self.synth.speak(['Recovery.', IndexCommand(1)])
        self.ready()
        self.drain()
        self.assertNotEqual(process.pid, self.synth._host.pid)
        self.assertEqual((self.synth.rate, self.synth.pitch, self.synth.volume, self.synth.intonation),
                         (65, 35, 42, 100))


class OriginalDriverTests(DriverTests):
    voice = 'apollo'

    def test_number_words_option_bypasses_original_digit_pronunciation(self):
        rendered = []
        original = self.synth._host.render
        def capture(settings, text, stopping):
            rendered.append((settings[-1], text))
            return original(settings, text, stopping)
        self.synth._host.render = capture
        self.synth.speak(['1'])
        self.ready()
        self.drain()
        done.calls.clear()
        self.synth.readNumbers = True
        self.synth.speak(['1'])
        self.ready()
        self.drain()
        self.assertEqual(rendered, [(1, '1'), (1, 'one')])


if __name__ == '__main__':
    unittest.main()
