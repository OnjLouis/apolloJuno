"""NVDA command objects preserve markers through punctuation and utterance splitting."""

from collections.abc import Sequence

from speech.commands import CharacterModeCommand, SynthCommand, SynthParamCommand

from ._inline import State, effect_number, tokens


class InlineStateCommand(SynthParamCommand):
    def __init__(self, commands=()):
        self.commands = State(commands).snapshot()
        self.isDefault = not self.commands

    def __eq__(self, other):
        return type(self) is type(other) and self.commands == other.commands

    def __repr__(self):
        return f'InlineStateCommand({self.commands!r})'


class InlineEffectCommand(SynthCommand):
    def __init__(self, command):
        self.effect = effect_number(command)

    def __repr__(self):
        return f'InlineEffectCommand({self.effect})'


def prepare_sequence(sequence):
    if not isinstance(sequence, Sequence):
        sequence = list(sequence)
    result = []
    state = State()
    character_mode = False
    changed = False
    for item in sequence:
        if isinstance(item, CharacterModeCommand):
            character_mode = item.state
        if not isinstance(item, str) or character_mode:
            result.append(item)
            continue
        for kind, value in tokens(item):
            if kind == 'text':
                result.append(value)
                continue
            changed = True
            if value.startswith('@T'):
                result.append(InlineEffectCommand(value))
            else:
                state.apply(value)
                result.append(InlineStateCommand(state.snapshot()))
    if not changed:
        return sequence
    # NVDA tracks SynthParamCommand snapshots when an utterance is split or preempted.
    # Explicitly end this input's state so unrelated speech never inherits it.
    if state.snapshot():
        result.append(InlineStateCommand())
    return result
