# Apollo II / Juno NVDA Integration

This directory contains the Apollo II for NVDA 1.1 integration. Its firmware
profile and Juno-reference adjustments are specific to the NVDA host. Upstream
has explicitly permitted GPL licensing of the add-on; see addon/NOTICE for the
permission reference and preserved third-party attribution.

`addon` contains the NVDA driver and manual. `native/apollo_host.c` links against
the parent project's C firmware, Juno mapping and Orpheus renderer. The resulting
`ApolloJunoHost.exe` belongs at `synthDrivers/apolloJuno/bin` in the add-on package.
No external ROM files or DLLs are required at runtime.

Two voice profiles share one helper and the same playback lifecycle. The existing
`uk` voice ID remains Juno (calibrated), preserving saved selections; `apollo`
selects Apollo II (original). The selected profile is captured with each queued
speech job. The original profile uses the immutable upstream firmware data,
unmodified prosody and rate limits, and `orp_map_frame` with the utterance's
voiced pitch centre. It does not apply Juno's pronunciation corrections, pulse,
noise or absolute-pitch calibration. Peak-safe volume and optional EQ remain
shared. It is the upstream reconstruction, not a claim of bit-exact hardware audio.
The install hook copies the previous single-voice NVDA dictionary to the new
Juno dictionary filename, preserving the source and never overwriting an existing
destination. The original profile gets a separate NVDA voice dictionary.

The Juno profile uses a private copy of the converted firmware data with
rate-dependent intonation limits inferred from Juno 2.02 recordings. The
recovered Apollo 2.01 limits are more abrupt. The original image and other
renderers remain unchanged; this calibration is not a recovered Juno ROM.
Calibrated prosody parameters are initialized directly in the host's firmware
state, avoiding the legacy parser's ambiguous doubled-R command. Exclamation
stress follows hardware comparisons; the effective comma baseline is retained
for compatibility with the previously tested voice.

The calibrated renderer adjusts the two fixed noise cascades and their amplitude
codes, and uses pulse shape 82 for voiced sound. Output is boosted by up to 6 dB
using one peak-safe scalar per utterance, followed by the selected volume. A
four-times interpolated peak estimate leaves 1.5 dB of headroom; it measures
the waveform without filtering it. No compressor or per-word gain is applied.
Optional 250 Hz bass and 2 kHz treble shelves offer +/-12 dB, centred at 50.
They run in floating point before peak measurement and the single conversion
to output PCM. At neutral settings they bypass processing exactly.
The private firmware data image also corrects the digit 1, sample-family,
terminal-family and says pronunciations. MI consumes the N in terminal before
the I/IN rules run, so its word-bounded correction belongs in the MI list;
says belongs in AY. Copied rule lists are placed in verified free main-ROM
data above the LOW overlay so either bank can read them. Recovered lists
remain the fallback, and the original image and other renderers are unchanged.

The helper stays alive until the driver unloads. Each bounded text request uses
fresh firmware and renderer state; cancellation discards old audio rather than
replaying text or restarting a healthy helper. Audio and notifications use NVDA's
WavePlayer, including playback-timed indexes and final completion. Failed helpers
are reaped and recreated on the next request, not retried indefinitely.

The binary protocol is little-endian, with a sixteen-byte header: magic `APNV`,
message type, nonzero request identifier and payload size. Speak requests carry
seven setting bytes (native rate, pitch, intonation, volume, bass, treble, profile)
and up to 320 bytes of
plain ASCII text. Protocol constants are mirrored and tested in `_host.py`.
Profile 0 is Juno and 1 is original Apollo; other values are rejected. Ready
announces protocol version 3 and 10 kHz mono PCM16. Audio frames are at most
16384 bytes. Done carries the number of headroom halvings applied (zero normally).
Plain speech cannot inject firmware commands.

The optional readNumbers BooleanDriverSetting expands plain English numbers
before text chunking; it is off by default and does not change playback indexes.
It preserves structured identifiers and caps conversion
length. Only the unchanged English runtime subset of num2words 0.5.14 is included,
with its LGPL-2.1-or-later notice and source. Other languages and the CLI are not
runtime dependencies. A later-stress term measured from sustained Juno vowels
keeps shouted contours from collapsing to the baseline; ordinary accepted
reference passages remain unchanged.

Valid 24-hour HH:MM and HH:MM:SS times are expanded by the same opt-in setting.
URL/path spans and invalid colon-delimited identifiers remain unchanged.

The updater lives in its own globalPlugins.apolloJuno package, avoiding shared
helper-name collisions with other add-ons. Its settings panel offers Never,
Hourly and Daily checks plus Check now. Downloads use the established signed
GitHub metadata format with addon identity apolloJuno, tags v<version>, manifest
apolloJuno-update.json and asset apolloJuno-<version>.nvda-addon in
OnjLouis/apolloJuno. Signatures cover every metadata field except signature.
NVDA's own bundle installer stages the verified package; it is never extracted
over the running add-on. Pending operations block another installation.
No signing key, account token or release tooling belongs in source/packages.
COPYING covers this add-on with the upstream author's explicit permission;
NOTICE preserves that permission reference and separate third-party notices.

Tests use a real helper process and a simulated WavePlayer for deterministic
playback/cancellation races. Set `APOLLO_TEST_HOST` to the freshly built helper
before running unittest discovery in `tests`. These tests do not replace live
NVDA keyboard, audio-device, spelling, Say All or long-running verification.

Only `addon` and the required helper belong in an installable package. Native
sources and tests are source material, not add-on runtime content. Do not package
personal configuration, recordings, logs or maintainer tooling.
