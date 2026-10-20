#ifndef APOLLO_TONE_CONTROLS_H
#define APOLLO_TONE_CONTROLS_H

#include "output_level.h"

enum { TONE_CENTRE = 50, TONE_MAX = 100, TONE_SAMPLE_RATE = 10000 };
static const double tone_range_db = 12;
static const double bass_frequency = 250, treble_frequency = 2000;
typedef struct { double b0, b1, b2, a1, a2; } tone_filter;

/* Robert Bristow-Johnson's S=1 shelving equations, W3C Audio EQ Cookbook:
   https://www.w3.org/TR/audio-eq-cookbook/ */
static tone_filter tone_shelf(double frequency, double db, bool high)
{
    double a = pow(10, db / 40), omega = 2 * acos(-1.0) * frequency / TONE_SAMPLE_RATE;
    double c = cos(omega), beta = sqrt(2 * a) * sin(omega);
    double b0, b1, b2, a0, a1, a2;
    if (high) {
        b0 = a * ((a + 1) + (a - 1) * c + beta);
        b1 = -2 * a * ((a - 1) + (a + 1) * c);
        b2 = a * ((a + 1) + (a - 1) * c - beta);
        a0 = (a + 1) - (a - 1) * c + beta;
        a1 = 2 * ((a - 1) - (a + 1) * c);
        a2 = (a + 1) - (a - 1) * c - beta;
    } else {
        b0 = a * ((a + 1) - (a - 1) * c + beta);
        b1 = 2 * a * ((a - 1) - (a + 1) * c);
        b2 = a * ((a + 1) - (a - 1) * c - beta);
        a0 = (a + 1) + (a - 1) * c + beta;
        a1 = -2 * ((a - 1) + (a + 1) * c);
        a2 = (a + 1) + (a - 1) * c - beta;
    }
    return (tone_filter){b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0};
}

static void tone_filter_audio(double *audio, size_t count, tone_filter filter)
{
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (size_t i = 0; i < count; i++) {
        double x = audio[i];
        double y = filter.b0*x + filter.b1*x1 + filter.b2*x2 - filter.a1*y1 - filter.a2*y2;
        audio[i] = y;
        x2 = x1; x1 = x; y2 = y1; y1 = y;
    }
}

static bool tone_apply(const level_meter *meter, int16_t *audio, size_t count,
                       int volume, int bass, int treble, level_result *result)
{
    if (bass < 0 || bass > TONE_MAX || treble < 0 || treble > TONE_MAX) return false;
    if (bass == TONE_CENTRE && treble == TONE_CENTRE)
        return level_apply(meter, audio, count, volume, result);
    if (count > SIZE_MAX / sizeof(double) || (count && !audio)) return false;
    double *filtered = count ? malloc(count * sizeof *filtered) : NULL;
    if (count && !filtered) return false;
    for (size_t i = 0; i < count; i++) filtered[i] = audio[i];
    if (bass != TONE_CENTRE)
        tone_filter_audio(filtered, count, tone_shelf(bass_frequency, (bass-TONE_CENTRE)*tone_range_db/TONE_CENTRE, false));
    if (treble != TONE_CENTRE)
        tone_filter_audio(filtered, count, tone_shelf(treble_frequency, (treble-TONE_CENTRE)*tone_range_db/TONE_CENTRE, true));
    bool ok = level_process(meter, audio, filtered, count, volume, result);
    free(filtered);
    return ok;
}
#endif
