"""Conservative English number expansion without changing structured identifiers."""

from functools import lru_cache
import re

from ._numberwords.lang_EN import Num2Word_EN

MAX_INTEGER_DIGITS = 18
_PROTECTED = re.compile(
    r'https?://\S+|www\.\S+|(?<![\w.+-])[\w.+-]+@[\w.-]+\.\w+|[A-Za-z]:\\\S+'
    r'|\b(?:version|ver|v)\s*\d+(?:\.\d+)+\b'
    r'|(?<!\w)\d+(?:\.\d+){2,}(?!\w)'
    r'|\b\w+(?::\w+)+\b'
    r'|(?<!\w)\d{1,4}[-/]\d{1,2}[-/]\d{1,4}(?!\w)'
    r'|(?<!\w)\+?\d{1,4}(?:[ ()-]+\d{2,6}){2,4}(?!\w)', re.I,
)
_NUMBER = re.compile(r'(?<![\w.])([+-]?)(\d+(?:,\d+)*)(?:\.(\d+))?(st|nd|rd|th)?(?!\w|\.\d)', re.I)
_CLOCK = re.compile(r'(\d{1,2}):(\d{2})(?::(\d{2}))?')


@lru_cache(maxsize=1)
def _converter():
    return Num2Word_EN()


def _replace(match):
    sign, integer, fraction, ordinal = match.groups()
    digits = integer.replace(',', '')
    if len(digits) > MAX_INTEGER_DIGITS or len(digits) > 1 and digits.startswith('0'):
        return match.group()
    if fraction is not None and len(fraction) > MAX_INTEGER_DIGITS:
        return match.group()
    if ',' in integer and not re.fullmatch(r'[1-9]\d{0,2}(?:,\d{3})+', integer):
        return match.group()
    if ordinal and (fraction is not None or sign):
        return match.group()
    converter = _converter()
    value = int(digits)
    try:
        if ordinal:
            if converter.to_ordinal_num(value)[-2:].lower() != ordinal.lower():
                return match.group()
            words = converter.to_ordinal(value)
        else:
            words = converter.to_cardinal(value)
            if fraction is not None:
                words += ' point ' + ' '.join(converter.to_cardinal(int(d)) for d in fraction)
        if sign:
            words = ('minus ' if sign == '-' else 'plus ') + words
        return words.replace('-', ' ')
    except (ValueError, OverflowError, TypeError):
        return match.group()


def _time_words(text):
    match = _CLOCK.fullmatch(text)
    if match is None:
        return text
    hour, minute, second = match.groups()
    if int(hour) > 23 or int(minute) > 59 or second is not None and int(second) > 59:
        return text
    cardinal = _converter().to_cardinal
    words = cardinal(int(hour))
    if int(minute) == 0:
        words += ' hundred'
    else:
        words += (' oh ' if int(minute) < 10 else ' ') + cardinal(int(minute))
    if second is not None:
        words += ' and ' + cardinal(int(second)) + (' second' if int(second) == 1 else ' seconds')
    return words.replace('-', ' ')


def expand_numbers(text):
    parts, start = [], 0
    for protected in _PROTECTED.finditer(text):
        parts.append(_NUMBER.sub(_replace, text[start:protected.start()]))
        parts.append(_time_words(protected.group()))
        start = protected.end()
    parts.append(_NUMBER.sub(_replace, text[start:]))
    return ''.join(parts)


def expand_times(text):
    """Expand before NVDA replaces colon symbols; leave other number rules alone."""
    return _PROTECTED.sub(lambda match: _time_words(match.group()), text)
