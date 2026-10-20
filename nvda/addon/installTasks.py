"""Preserve the single-voice dictionary when adding named voice profiles."""

from pathlib import Path
import shutil

from NVDAState import WritePaths
from speechDictHandler import dictFormatUpgrade


def onInstall():
    folder = Path(WritePaths.voiceDictsDir) / 'apolloJuno'
    source = folder / 'apolloJuno.dic'
    if not source.is_file() or source.is_symlink():
        return
    target = folder / dictFormatUpgrade.createVoiceDictFileName('apolloJuno', 'Juno (calibrated)')
    try:
        output = target.open('xb')
    except FileExistsError:
        return
    try:
        with output, source.open('rb') as original:
            shutil.copyfileobj(original, output)
    except Exception:
        target.unlink()
        raise
