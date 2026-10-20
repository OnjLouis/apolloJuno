"""Plain-text preparation and percentage-to-firmware setting mappings."""

import re
import unicodedata

MAX_TEXT_BYTES = 320
_PUNCTUATION = str.maketrans({
    '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
    '\u2013': '-', '\u2014': '-', '\u2026': '...',
})


def percent(value):
    return max(0, min(100, int(value)))


def native_rate(value):
    value = percent(value)
    if value <= 50:
        return 1+round(value*2/50)
    return 3+round((value-50)*6/50)


def native_pitch(value):
    return round(percent(value)*15/100)


def native_intonation(value):
    return round(percent(value)*7/100)


def clean_text(value):
    value = unicodedata.normalize('NFKD', value.translate(_PUNCTUATION))
    value = value.encode('ascii', 'ignore').decode('ascii')
    value = value.replace('@', ' at ').replace('_', ' underscore ')
    return re.sub(r'\s+', ' ', re.sub(r'[^\x20-\x7e]', ' ', value)).strip()


def chunks(value):
    value = clean_text(value)
    while len(value) > MAX_TEXT_BYTES:
        cut = value.rfind(' ', 0, MAX_TEXT_BYTES+1)
        if cut <= 0:
            cut = MAX_TEXT_BYTES
        yield value[:cut]
        value = value[cut:].lstrip()
    if value:
        yield value
