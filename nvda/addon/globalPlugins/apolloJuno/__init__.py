# SPDX-License-Identifier: GPL-2.0-or-later
"""Apollo settings and signed updates, separate from the speech driver."""

import addonHandler
import config
import globalPluginHandler
import globalVars
import gui
import gui.guiHelper
import gui.settingsDialogs
from speech.commands import CharacterModeCommand
from speech.extensions import filter_speechSequence
import synthDriverHandler
import wx

from ._updater import GitHubReleaseUpdater

addonHandler.initTranslation()
_updater = None
_INTERVALS = ("never", "hourly", "daily")


class ApolloSettingsPanel(gui.settingsDialogs.SettingsPanel):
    title = _("Apollo II for NVDA")

    def makeSettings(self, settingsSizer):
        helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        self.interval = helper.addLabeledControl(
            _("Automatically check for &updates:"), wx.Choice,
            choices=[_("Never"), _("Hourly"), _("Daily")],
        )
        self.interval.SetSelection(_INTERVALS.index(config.conf["apolloJunoUpdates"]["interval"]))
        button = helper.addItem(wx.Button(self, label=_("&Check now")))
        button.Bind(wx.EVT_BUTTON, self.onCheck)

    def onCheck(self, event):
        if _updater is not None:
            _updater.checkNow()

    def onSave(self):
        value = _INTERVALS[self.interval.GetSelection()]
        config.conf["apolloJunoUpdates"]["interval"] = value
        if _updater is not None:
            _updater.setInterval(value)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        global _updater
        super().__init__()
        self._registered = False
        if getattr(globalVars.appArgs, "secure", False) or getattr(config, "isAppX", False):
            return
        config.conf.spec["apolloJunoUpdates"] = {"interval": "option('never', 'hourly', 'daily', default='daily')"}
        _updater = GitHubReleaseUpdater("apolloJuno", _("Apollo II for NVDA"), "OnjLouis", "apolloJuno")
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(ApolloSettingsPanel)
        self._registered = True
        filter_speechSequence.register(self._filterSpeech)
        _updater.start()

    def _filterSpeech(self, speechSequence):
        synth = synthDriverHandler.getSynth()
        if getattr(synth, 'name', '') != 'apolloJuno' or not getattr(synth, 'readNumbers', False):
            return speechSequence
        from synthDrivers.apolloJuno._numbers import expand_times
        result = []
        characterMode = False
        for item in speechSequence:
            if isinstance(item, CharacterModeCommand):
                characterMode = item.state
            result.append(expand_times(item) if isinstance(item, str) and not characterMode else item)
        return result

    def terminate(self):
        global _updater
        if self._registered:
            filter_speechSequence.unregister(self._filterSpeech)
            _updater.stop()
            _updater = None
            categories = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
            if ApolloSettingsPanel in categories:
                categories.remove(ApolloSettingsPanel)
        super().terminate()
