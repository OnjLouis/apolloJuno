# Apollo II for NVDA

A local UK English speech synthesizer for NVDA, based on
[Dolphin Apollo II Reborn by rommix0](https://github.com/rommix0/Dolphin-Apollo-II-Reborn),
with pronunciation, intonation and tone adjustments measured against a Dolphin Juno.
It offers both the original Apollo II Reborn profile and the Juno-calibrated
profile. These are approximations, not exact recreations of every hardware revision.

## Hardware Reference

This is the independently maintained Juno-calibrated implementation. The upstream
Apollo II Reborn project and this project use different hardware/firmware
references; differences in pronunciation and sound can be intentional, rather
than a defect in either implementation. Neither is a universal replacement for
the other.

Our calibration follows recordings and listening comparisons with a working
Juno. It is not a recovered newer ROM or a claim of bit-exact firmware accuracy;
the hardware's audio path also contributes to its sound. Model-specific changes
remain here, while generally applicable fixes can be offered upstream separately.
The native engine, calibration, NVDA integration and their tests are maintained
together in this repository.

## Install

Download the add-on from the
[releases page](https://github.com/OnjLouis/apolloJuno/releases),
install it in NVDA and restart. Choose **Apollo II for NVDA** in the synthesizer
dialog. Requires NVDA 2026.2 or later on 64-bit Windows.

Speech is generated on your computer and uses NVDA's selected audio device.
No external hardware, voice download or network connection is needed to speak.
Control interrupts speech; Shift pauses and resumes. Spelling and Say All are
supported, including playback-timed indexes.

## Settings

Voice, rate, pitch, volume, intonation, bass and treble appear in NVDA's Speech settings
and synthesizer ring. Pitch and intonation have a limited number of native steps.
Bass and treble are neutral at 50, with up to 12 dB of cut or boost. Peak protection
prevents strong boosts from clipping.

Choose **Juno (calibrated)** for the existing Juno-reference pronunciation,
intonation and tone, or **Apollo II (original)** to hear the upstream profile
before those adjustments. Juno remains the default and existing selections are
preserved. Both are UK English and share the same NVDA playback and controls.
For a comparison without additional EQ, set bass and treble to 50. Original
refers to the upstream reconstruction, not an exact hardware-ROM recording.
Turn off **Read numbers as words** to compare raw digits: otherwise `1` is
converted to the word "one" before either voice receives it.

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

## Version 1.1

- Added Apollo II (original) alongside the unchanged Juno (calibrated) voice.
- Voice selection is available in Speech settings and the synthesizer ring.
- Both profiles share playback, indexing, volume, EQ and number-reading options.

## Version 1.0

- Local Apollo/Juno-style speech with calibrated pronunciation and intonation.
- NVDA audio output, spelling, Say All, pause and interruption support.
- Rate, pitch, volume, intonation and configurable bass/treble controls.
- Optional English number and 24-hour time reading.
- Signed GitHub updates with configurable automatic checks.
