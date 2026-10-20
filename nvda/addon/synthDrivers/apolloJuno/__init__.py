"""Apollo II/Juno voice using NVDA playback and playback-timed indexes."""

from collections import OrderedDict
import os
import queue
import threading

import config
import nvwave
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
from logHandler import log
from speech.commands import IndexCommand, PitchCommand
from synthDriverHandler import SynthDriver as BaseSynth, VoiceInfo, synthDoneSpeaking, synthIndexReached

from ._host import Host, HOST_PATH, SAMPLE_RATE
from ._text import chunks, native_rate, native_pitch, native_intonation, percent
from ._numbers import expand_numbers


class SynthDriver(BaseSynth):
    name = 'apolloJuno'
    description = 'Apollo II for NVDA'
    supportedSettings = (
        BaseSynth.RateSetting(), BaseSynth.PitchSetting(), BaseSynth.VolumeSetting(),
        NumericDriverSetting('intonation', '&Intonation', availableInSettingsRing=True,
                             defaultVal=43, minStep=1, normalStep=14, largeStep=28,
                             displayName='Intonation'),
        NumericDriverSetting('bass', '&Bass', availableInSettingsRing=True,
                             defaultVal=50, minStep=1, normalStep=5, largeStep=10, displayName='Bass'),
        NumericDriverSetting('treble', '&Treble', availableInSettingsRing=True,
                             defaultVal=50, minStep=1, normalStep=5, largeStep=10, displayName='Treble'),
        BooleanDriverSetting('readNumbers', 'Read &numbers as words', defaultVal=False,
                             displayName='Read numbers as words'),
    )
    supportedCommands = {IndexCommand, PitchCommand}
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        return os.path.isfile(HOST_PATH)

    def __init__(self):
        super().__init__()
        self._rate, self._pitch, self._volume, self._intonation = 50, 50, 100, 43
        self._bass, self._treble = 50, 50
        self._readNumbers = False
        self._generation = 0
        self._latest_job = 0
        self._lock = threading.Lock()
        self._control_lock = threading.Lock()
        self._stopping = threading.Event()
        self._jobs = queue.Queue()
        self._host = Host()
        self._player = None
        try:
            self._host.start()
            self._player = nvwave.WavePlayer(1, SAMPLE_RATE, 16, outputDevice=config.conf['audio']['outputDevice'])
            self._worker = threading.Thread(target=self._run, name='Apollo speech worker', daemon=True)
            self._worker.start()
        except Exception:
            self._host.stop()
            if self._player is not None:
                self._player.close()
            raise

    def _get_availableVoices(self):
        return OrderedDict((('uk', VoiceInfo('uk', 'UK English', language='en_GB')),))

    def _get_voice(self):
        return 'uk'

    def _set_voice(self, value):
        if value != 'uk':
            raise ValueError('This trial has one UK English voice.')

    def _get_language(self):
        return 'en_GB'

    def _get_rate(self):
        return self._rate

    def _set_rate(self, value):
        self._rate = percent(value)

    def _get_pitch(self):
        return self._pitch

    def _set_pitch(self, value):
        self._pitch = percent(value)

    def _get_volume(self):
        return self._volume

    def _set_volume(self, value):
        self._volume = percent(value)

    def _get_intonation(self):
        return self._intonation

    def _set_intonation(self, value):
        self._intonation = percent(value)

    def _get_bass(self):
        return self._bass

    def _set_bass(self, value):
        self._bass = percent(value)

    def _get_treble(self):
        return self._treble

    def _set_treble(self, value):
        self._treble = percent(value)

    def _get_readNumbers(self):
        return self._readNumbers

    def _set_readNumbers(self, value):
        self._readNumbers = bool(value)

    def _current(self, generation):
        with self._lock:
            return not self._stopping.is_set() and generation == self._generation

    def speak(self, speechSequence):
        events, parts = [], []
        def flush():
            text = ' '.join(parts)
            if self._readNumbers:
                text = expand_numbers(text)
            events.extend(('text', chunk) for chunk in chunks(text))
            parts.clear()
        for item in speechSequence:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, IndexCommand):
                flush()
                events.append(('index', item.index))
            elif isinstance(item, PitchCommand):
                flush()
                events.append(('pitch', native_pitch(item.newValue)))
        flush()
        with self._control_lock:
            with self._lock:
                if self._stopping.is_set():
                    return
                self._latest_job += 1
                settings = (native_rate(self._rate), native_pitch(self._pitch),
                            native_intonation(self._intonation), self._volume, self._bass, self._treble)
                self._jobs.put((self._generation, self._latest_job, settings, events))

    def cancel(self):
        with self._control_lock:
            with self._lock:
                self._generation += 1
                try:
                    while True:
                        self._jobs.get_nowait()
                        self._jobs.task_done()
                except queue.Empty:
                    pass
            self._player.stop()

    def pause(self, switch):
        self._player.pause(switch)

    def _index(self, generation, value):
        if self._current(generation):
            synthIndexReached.notify(synth=self, index=value)

    def _done(self, generation, job):
        with self._lock:
            current = generation == self._generation and job == self._latest_job and not self._stopping.is_set()
        if current:
            synthDoneSpeaking.notify(synth=self)

    def _feed(self, generation, data=None, callback=None):
        if not self._current(generation):
            return False
        self._player.feed(data, None if data is not None else 0, onDone=callback)
        # Cancellation may race a blocked feed; stop that stale audio before processing any new job.
        if not self._current(generation):
            self._player.stop()
            return False
        return True

    def _render(self, generation, job, settings, events):
        for kind, value in events:
            if not self._current(generation):
                return
            if kind == 'index':
                self._feed(generation, callback=lambda index=value: self._index(generation, index))
                continue
            if kind == 'pitch':
                settings = (settings[0], value, *settings[2:])
                continue
            for audio in self._host.render(settings, value, self._stopping):
                # Continue draining cancelled responses so the same helper is ready for the next input.
                if self._current(generation):
                    self._feed(generation, audio)
            if self._host.last_gain_halvings:
                log.debug('Apollo adjusted headroom: settings=%s gainHalvings=%d', settings, self._host.last_gain_halvings)
        self._feed(generation, callback=lambda: self._done(generation, job))

    def _run(self):
        try:
            while True:
                job = self._jobs.get()
                try:
                    if job is None:
                        return
                    if self._current(job[0]):
                        try:
                            self._render(*job)
                        except Exception:
                            log.error('Apollo synthesis failed: settings=%s pid=%s; recreating on next input.',
                                      job[2], self._host.pid, exc_info=True)
                            self._host.stop()
                            self._feed(job[0], callback=lambda generation=job[0], number=job[1]: self._done(generation, number))
                finally:
                    self._jobs.task_done()
                if self._jobs.empty():
                    try:
                        # NVDA dispatches final playback callbacks during this drain.
                        # Do not drain between queued fragments or hold cancellation locks.
                        self._player.idle()
                    except Exception:
                        log.error('Apollo playback drain failed.', exc_info=True)
                        self._player.stop()
        finally:
            self._host.stop()

    def terminate(self):
        self._stopping.set()
        self.cancel()
        self._jobs.put(None)
        self._worker.join(timeout=2)
        if self._worker.is_alive():
            self._host.stop()
            self._worker.join(timeout=1)
            if self._worker.is_alive():
                log.error('Apollo speech worker did not exit within its shutdown deadline.')
        self._player.close()
        super().terminate()
