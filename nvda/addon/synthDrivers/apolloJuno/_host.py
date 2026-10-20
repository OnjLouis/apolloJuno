"""Bounded transport to one isolated, persistent Apollo renderer."""

import os
import queue
import struct
import subprocess
import threading
import time

HEADER = struct.Struct('<4sIII')
MAGIC = b'APNV'
SPEAK, QUIT = 1, 2
READY, AUDIO, DONE, ERROR = 100, 101, 102, 103
MAX_AUDIO_BYTES = 16384
PROTOCOL_VERSION = 3
SETTING_BYTES = 7
SAMPLE_RATE = 10000
CREATE_NO_WINDOW = 0x08000000
HOST_PATH = os.path.join(os.path.dirname(__file__), 'bin', 'ApolloJunoHost.exe')


class HostError(RuntimeError):
    pass


def read_exact(stream, size):
    parts = []
    while size:
        part = stream.read(size)
        if not part:
            raise EOFError('Apollo helper disconnected.')
        parts.append(part)
        size -= len(part)
    return b''.join(parts)


class _Session:
    def __init__(self, process):
        self.process = process
        self.messages = queue.Queue(maxsize=32)
        self.reader = None


class Host:
    def __init__(self, path=HOST_PATH):
        self.path = path
        self._session = None
        self._next_request = 0
        self.last_gain_halvings = 0

    @property
    def pid(self):
        return self._session.process.pid if self._session else None

    def is_running(self):
        return self._session is not None and self._session.process.poll() is None

    def _put(self, session, message):
        while session is self._session:
            try:
                session.messages.put(message, timeout=.05)
                return
            except queue.Full:
                continue

    def _read(self, session):
        try:
            while session is self._session:
                magic, kind, request, size = HEADER.unpack(read_exact(session.process.stdout, HEADER.size))
                if magic != MAGIC or kind not in (READY, AUDIO, DONE, ERROR) or size > MAX_AUDIO_BYTES:
                    raise HostError('Apollo helper returned an invalid packet.')
                if kind == AUDIO and size % 2:
                    raise HostError('Apollo helper returned an incomplete audio sample.')
                self._put(session, (kind, request, read_exact(session.process.stdout, size)))
        except Exception as error:
            self._put(session, (None, 0, str(error).encode('utf-8', 'replace')))

    @staticmethod
    def _write(session, kind, request, payload=b''):
        packet = HEADER.pack(MAGIC, kind, request, len(payload))+payload
        view = memoryview(packet)
        while view:
            count = session.process.stdin.write(view)
            if not count:
                raise HostError('Apollo helper pipe closed during a write.')
            view = view[count:]

    def start(self):
        self.stop()
        process = subprocess.Popen([self.path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, bufsize=0, creationflags=CREATE_NO_WINDOW)
        session = self._session = _Session(process)
        session.reader = threading.Thread(target=self._read, args=(session,), name='Apollo helper reader', daemon=True)
        session.reader.start()
        try:
            kind, request, payload = session.messages.get(timeout=2)
            if kind != READY or request != 0 or payload != struct.pack('<II', PROTOCOL_VERSION, SAMPLE_RATE):
                raise HostError('Apollo helper protocol or sample rate does not match this driver.')
        except Exception:
            self.stop()
            raise

    def render(self, settings, text, stopping):
        if not self.is_running():
            self.start()
        self._next_request = self._next_request % 0xffffffff + 1
        request = self._next_request
        session = self._session
        if len(settings) == 4:
            settings = (*settings, 50, 50)
        if len(settings) == 6:
            settings = (*settings, 0)
        if len(settings) != SETTING_BYTES:
            raise HostError('Apollo helper requires seven speech settings.')
        payload = bytes(settings)+text.encode('ascii')
        if len(payload) > 320 + SETTING_BYTES:
            raise HostError('Apollo helper input exceeds the protocol limit.')
        self._write(session, SPEAK, request, payload)
        progress = time.monotonic()
        while not stopping.is_set():
            try:
                kind, response, audio = session.messages.get(timeout=.05)
            except queue.Empty:
                if time.monotonic()-progress > 5:
                    raise HostError('Apollo helper stopped responding for five seconds.')
                continue
            progress = time.monotonic()
            if kind is None:
                raise HostError(audio.decode('utf-8', 'replace'))
            if response != request:
                raise HostError('Apollo helper returned an unexpected request identifier.')
            if kind == AUDIO:
                yield audio
            elif kind == DONE:
                if len(audio) != 4:
                    raise HostError('Apollo helper completion metadata is invalid.')
                self.last_gain_halvings = struct.unpack('<I', audio)[0]
                if self.last_gain_halvings > 4:
                    raise HostError('Apollo helper headroom metadata is invalid.')
                return
            elif kind == ERROR:
                raise HostError(audio.decode('utf-8', 'replace'))
            else:
                raise HostError('Apollo helper returned an unexpected response.')

    def stop(self):
        session = self._session
        self._session = None
        if session is None:
            return
        process = session.process
        try:
            if process.poll() is None:
                try:
                    self._write(session, QUIT, 0)
                    process.stdin.close()
                    process.wait(timeout=.5)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    process.terminate()
                    process.wait(timeout=1)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
            for stream in (process.stdin, process.stdout):
                stream.close()
            if session.reader is not threading.current_thread():
                session.reader.join(timeout=1)
