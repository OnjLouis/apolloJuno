"""Explicit, bounded Apollo command markers and local rendering state."""

from collections import OrderedDict
import re

MAX_PREFIX_BYTES = 192
NO_EFFECT = 255
_BRACES = re.compile(r'\{+|\}+')
_COMMAND = re.compile(r'@(?:W[1-9]|F[0-9A-F+-]|R[0-7]|Q[0-9]|D[0-9A-F]|B[1-8]|'
                      r'K[01]|V[1-6]|[SPH][01]|U[0-9][0-9A-F]{2}[+-]|A[0-9A-F]|T[0-9A-FX])')
_PRESET_PITCH = (8, 6, 9, 11, 10, 12)


def validate(value):
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    if value == 'RESET':
        return 'reset'
    return value if _COMMAND.fullmatch(value) else None


def tokens(text):
    start = 0
    depth, opening, body_start, valid = 0, 0, 0, False
    for match in _BRACES.finditer(text):
        run = match[0]
        if len(run) < 2:
            if depth:
                valid = False
            continue
        if run[0] == '{':
            if not depth:
                opening, body_start, valid = match.start(), match.end(), len(run) == 2
            else:
                valid = False
            depth += 1
            continue
        if not depth:
            continue
        depth -= 1
        if depth or not valid or len(run) != 2:
            continue
        body = text[body_start:match.start()]
        command = validate(body) if 1 <= len(body) <= 12 and '\r' not in body and '\n' not in body else None
        if command is None:
            continue
        if opening > start:
            yield 'text', text[start:opening]
        yield 'command', command
        start = match.end()
    if start < len(text):
        yield 'text', text[start:]


def effect_number(command):
    if not isinstance(command, str) or validate(command) != command or not command.startswith('@T'):
        raise ValueError('Invalid Apollo effect.')
    return 16 if command == '@TX' else int(command[2], 16)


class State:
    def __init__(self, commands=()):
        self._commands = OrderedDict()
        self.level = 15
        for command in commands:
            self.apply(command)

    def apply(self, command):
        if not isinstance(command, str) or validate(command) != command or command.startswith('@T'):
            raise ValueError('Invalid Apollo state command.')
        if command == 'reset':
            self._commands.clear()
            self.level = 15
            return
        if command.startswith('@A'):
            self.level = int(command[2], 16)
            return
        key = command[1:3] if command.startswith('@U') else command[1]
        if command.startswith('@V'):
            for old in list(self._commands):
                if old in ('V', 'F', 'B', 'K') or old.startswith('U'):
                    del self._commands[old]
        if command in ('@F+', '@F-'):
            key = 'Fstep'
        elif key == 'F':
            self._commands.pop('Fstep', None)
        self._commands.pop(key, None)
        self._commands[key] = command

    def snapshot(self):
        commands = tuple(self._commands.values())
        return commands + ((f'@A{self.level:X}',) if self.level != 15 else ())

    def prefix(self, pitch_offset=0):
        commands = list(self._commands.values())
        pitch = None
        for command in commands:
            if command.startswith('@V'):
                pitch = _PRESET_PITCH[int(command[2])-1]
            elif command.startswith('@F') and command[2] not in '+-':
                pitch = int(command[2], 16)
        if pitch is not None and pitch_offset:
            commands.append(f'@F{max(0, min(15, pitch+pitch_offset)):X}')
            if 'Fstep' in self._commands:
                commands.append(self._commands['Fstep'])
        result = ' '.join(commands)
        if len(result) > MAX_PREFIX_BYTES:
            raise ValueError('Apollo command state exceeds its bounded prefix.')
        return result
