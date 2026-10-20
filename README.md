# Apollo II for NVDA

A local UK English speech synthesizer for NVDA, based on
[Dolphin Apollo II Reborn by rommix0](https://github.com/rommix0/Dolphin-Apollo-II-Reborn),
with pronunciation, intonation and tone adjustments measured against a Dolphin Juno.
It is an approximation of that hardware, not an exact recreation of every revision.

## Install

Download `apolloJuno-1.0.nvda-addon` from the
[1.0 release](https://github.com/OnjLouis/apolloJuno/releases/tag/v1.0),
install it in NVDA and restart. Choose **Apollo II for NVDA** in the synthesizer
dialog. Requires NVDA 2026.2 or later on 64-bit Windows.

Speech is generated on your computer and uses NVDA's selected audio device.
No external hardware, voice download or network connection is needed to speak.
Control interrupts speech; Shift pauses and resumes. Spelling and Say All are
supported, including playback-timed indexes.

## Settings

Rate, pitch, volume, intonation, bass and treble appear in NVDA's Speech settings
and synthesizer ring. Pitch and intonation have a limited number of native steps.
Bass and treble are neutral at 50, with up to 12 dB of cut or boost. Peak protection
prevents strong boosts from clipping.

Enable **Read numbers as words** in Speech settings for English integers,
decimals, ordinals and valid 24-hour times. For example, `16:30:29` becomes
"sixteen thirty and twenty-nine seconds." This option is off by default.
Structured identifiers are conservatively left alone.

The **Apollo II for NVDA** settings category offers automatic update checks
(Never, Hourly or Daily) and **Check now**. Daily is the default. Checks contact
GitHub but do not send speech text. Downloads must pass the publisher's signature,
identity, version, size and hash checks before NVDA stages the update.

Save NVDA's configuration to retain your choices. See the
[full manual](nvda/addon/doc/en/readme.html) for controls, limitations and credits.

## Credits And Licence

The firmware implementation and underlying renderer are from
[Apollo II Reborn](https://github.com/rommix0/Dolphin-Apollo-II-Reborn).
Upstream describes a C port of Apollo firmware and an Orpheus Build 18 renderer
port, with a separately rewritten DSP. NVDA integration and Juno-reference
adjustments are by Andre Louis. Dolphin does not endorse this add-on.

The upstream author has
[explicitly permitted GPL licensing of this NVDA add-on](https://github.com/rommix0/Dolphin-Apollo-II-Reborn/issues/1#issuecomment-6295193927).
The add-on is GPL-2.0-or-later; this does not claim that upstream's entire
repository has adopted GPL. See [COPYING](COPYING) and [NOTICE](NOTICE).
English number expansion uses the included LGPL-2.1-or-later num2words subset.
The signed updater retains its original BSD-3-Clause notice, and the tone
controls use Robert Bristow-Johnson's Audio EQ Cookbook equations.

## Build From Source

The corresponding native host source is included. Use a 64-bit Windows C11
compiler, CMake and Ninja. LLVM-MinGW is supported; no external ROM file or
proprietary DLL is required at build or runtime.

```powershell
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
$env:APOLLO_TEST_HOST = (Resolve-Path build/bin/ApolloJunoHost.exe).Path
python -B -m unittest discover -s nvda/tests
```

Place the resulting `ApolloJunoHost.exe` under
`nvda/addon/synthDrivers/apolloJuno/bin/` when packaging an add-on. The installed
archive contains the contents of `nvda/addon`, not this repository's tests or
native source directories. The binary protocol and architecture are documented
in [the integration notes](nvda/README.md).

## Version 1.0

- Local Apollo/Juno-style speech with calibrated pronunciation and intonation.
- NVDA audio output, spelling, Say All, pause and interruption support.
- Rate, pitch, volume, intonation and configurable bass/treble controls.
- Optional English number and 24-hour time reading.
- Signed GitHub updates with configurable automatic checks.
