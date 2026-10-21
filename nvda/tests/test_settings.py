import builtins
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.modules = {name: types.ModuleType(name) for name in (
            'addonHandler', 'config', 'globalPluginHandler', 'globalVars', 'gui',
            'gui.guiHelper', 'gui.settingsDialogs', 'wx', 'apollo_settings_test._updater',
            'speech', 'speech.commands', 'speech.extensions', 'synthDriverHandler',
            'synthDrivers.apolloJuno._numbers',
        )}
        self.config = self.modules['config']
        class Configuration(dict):
            spec = {}
        self.config.conf = Configuration(apolloJunoUpdates={'interval': 'daily'})
        self.modules['globalVars'].appArgs = types.SimpleNamespace(secure=False)
        self.modules['addonHandler'].initTranslation = Mock()
        class CharacterModeCommand:
            def __init__(self, state):
                self.state = state
        self.characterMode = CharacterModeCommand
        self.modules['speech.commands'].CharacterModeCommand = CharacterModeCommand
        self.filter = Mock()
        self.modules['speech.extensions'].filter_speechSequence = self.filter
        self.modules['synthDriverHandler'].getSynth = Mock(return_value=types.SimpleNamespace(name='apolloJuno', readNumbers=True))
        self.expandTimes = Mock(side_effect=lambda text: text.replace('16:30:29', 'sixteen thirty and twenty nine seconds'))
        self.modules['synthDrivers.apolloJuno._numbers'].expand_times = self.expandTimes
        self.modules['globalPluginHandler'].GlobalPlugin = type('Base', (), {'terminate': Mock()})
        dialogs = self.modules['gui.settingsDialogs']
        dialogs.SettingsPanel = object
        self.categories = []
        dialogs.NVDASettingsDialog = types.SimpleNamespace(categoryClasses=self.categories)
        self.modules['gui'].settingsDialogs = dialogs
        self.modules['gui'].guiHelper = self.modules['gui.guiHelper']
        self.updater = Mock()
        self.modules['apollo_settings_test._updater'].GitHubReleaseUpdater = Mock(return_value=self.updater)
        path = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/apolloJuno/__init__.py'
        spec = importlib.util.spec_from_file_location('apollo_settings_test', path, submodule_search_locations=[str(path.parent)])
        self.module = importlib.util.module_from_spec(spec)
        self.modules['apollo_settings_test'] = self.module
        self.mapping = patch.dict(sys.modules, self.modules)
        self.mapping.start()
        self.translation = patch.object(builtins, '_', lambda text: text, create=True)
        self.translation.start()
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.translation.stop()
        self.mapping.stop()

    def test_register_save_and_terminate(self):
        plugin = self.module.GlobalPlugin()
        self.assertEqual(self.categories, [self.module.ApolloSettingsPanel])
        self.updater.start.assert_called_once()
        panel = self.module.ApolloSettingsPanel()
        panel.interval = Mock()
        panel.interval.GetSelection.return_value = 0
        panel.onSave()
        self.assertEqual(self.config.conf['apolloJunoUpdates']['interval'], 'never')
        self.updater.setInterval.assert_called_once_with('never')
        panel.onCheck(None)
        self.updater.checkNow.assert_called_once_with()
        plugin.terminate()
        self.filter.unregister.assert_called_once_with(plugin._filterSpeech)
        self.updater.stop.assert_called_once()
        self.assertEqual(self.categories, [])
        panel.onCheck(None)
        self.updater.checkNow.assert_called_once()

    def test_named_controls_and_unique_mnemonics(self):
        self.module.GlobalPlugin()
        wx = self.modules['wx']
        wx.Choice, wx.Button, wx.EVT_BUTTON = Mock(), Mock(), object()
        helper = Mock()
        self.modules['gui.guiHelper'].BoxSizerHelper = Mock(return_value=helper)
        panel = self.module.ApolloSettingsPanel()
        panel.makeSettings(object())
        args, kwargs = helper.addLabeledControl.call_args
        self.assertEqual(args[0], 'Automatically check for &updates:')
        self.assertEqual(kwargs['choices'], ['Never', 'Hourly', 'Daily'])
        helper.addLabeledControl.return_value.SetSelection.assert_called_once_with(2)
        wx.Button.assert_called_once_with(panel, label='&Check now')

    def test_secure_mode_does_not_register_or_check(self):
        self.modules['globalVars'].appArgs.secure = True
        plugin = self.module.GlobalPlugin()
        self.assertFalse(self.categories)
        self.updater.start.assert_not_called()
        plugin.terminate()

    def test_time_filter_preserves_commands_and_spelling(self):
        plugin = self.module.GlobalPlugin()
        start, end, index = self.characterMode(True), self.characterMode(False), object()
        sequence = ['16:30:29', index, start, '16:30:29', end, 'another line']
        self.assertEqual(plugin._filterSpeech(sequence), [
            'sixteen thirty and twenty nine seconds', index, start, '16:30:29', end, 'another line',
        ])
        self.assertEqual(sequence[0], '16:30:29')
        self.assertEqual(self.expandTimes.call_count, 2)

    def test_time_filter_is_inactive_for_other_synths_or_disabled_option(self):
        plugin = self.module.GlobalPlugin()
        for name, enabled in (('oneCore', True), ('apolloJuno', False)):
            self.modules['synthDriverHandler'].getSynth.return_value = types.SimpleNamespace(name=name, readNumbers=enabled)
            sequence = ['16:30:29']
            self.assertIs(plugin._filterSpeech(sequence), sequence)
        self.expandTimes.assert_not_called()

    def test_inline_filter_runs_before_time_expansion_and_only_for_this_synth(self):
        command=object()
        prepared=['16:30:29',command]
        module=types.ModuleType('synthDrivers.apolloJuno._commands')
        module.prepare_sequence=Mock(return_value=prepared)
        with patch.dict(sys.modules,{'synthDrivers.apolloJuno._commands':module}):
            plugin=self.module.GlobalPlugin()
            synth=self.modules['synthDriverHandler'].getSynth.return_value
            synth.inlineCommands=True
            result=plugin._filterSpeech(['{{@W9}}16:30:29'])
            self.assertEqual(result,['sixteen thirty and twenty nine seconds',command])
            module.prepare_sequence.assert_called_once_with(['{{@W9}}16:30:29'])
            synth.name='oneCore'
            sequence=['{{@W9}}']
            self.assertIs(plugin._filterSpeech(sequence),sequence)
            module.prepare_sequence.assert_called_once()
            synth.name='apolloJuno'
            synth.readNumbers=False
            self.assertIs(plugin._filterSpeech(sequence),prepared)
