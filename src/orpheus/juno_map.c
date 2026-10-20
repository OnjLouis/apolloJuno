#include <math.h>
#include "orpheus/juno_map.h"
#include "orpheus/orp_map.h"

/* Fit to recorded Juno @F4 and @FC vowels; @F8 is the held-out check.
   This is a measured approximation, not a recovered DSP frequency table. */
#define JUNO_PITCH_BASE_HZ 25.6490638296705
#define JUNO_PITCH_LOG_STEP 0.042483451168427666
#define JUNO_MIN_PITCH_HZ 25.0
#define JUNO_MAX_PITCH_HZ 400.0
#define JUNO_MARK_SPACE_PERCENT 50

void juno_map_frame(const uint8_t frame[SYNTH_FRAME_BYTES], int16_t params[ORP_PARAMS])
{
    /* Keep the flat-pitch fit separate from the original mapping's empirical
       contour widening. Sentence-level prosody needs separate validation. */
    orp_map_frame(frame, 0.0f, params);
    double hz = JUNO_PITCH_BASE_HZ * exp(JUNO_PITCH_LOG_STEP * frame[10]);
    hz = fmax(JUNO_MIN_PITCH_HZ, fmin(JUNO_MAX_PITCH_HZ, hz));
    int pitch = (int)floor(hz + 0.5);
    int pulse = 2 * pitch - ((2 * pitch - (pitch >> 1)) * JUNO_MARK_SPACE_PERCENT) / 100;
    params[13] = (int16_t)pitch;
    params[14] = (int16_t)(pulse * 100 / 60);
}
