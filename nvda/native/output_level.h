#ifndef APOLLO_LEVEL_H
#define APOLLO_LEVEL_H

#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#define LEVEL_NOMINAL_GAIN 2.0
#define LEVEL_CEILING_DBTP (-1.5)
#define LEVEL_TAPS 32
#define LEVEL_PHASES 3

typedef struct { double coefficients[LEVEL_PHASES][LEVEL_TAPS]; } level_meter;
typedef struct { double gain, peak_before; } level_result;

static void level_init(level_meter *meter)
{
    const double pi = acos(-1.0);
    for (int phase = 0; phase < LEVEL_PHASES; phase++) {
        double fraction = (phase + 1) / 4.0, sum = 0;
        for (int tap = 0; tap < LEVEL_TAPS; tap++) {
            double x = tap - 15 - fraction;
            double window = .42 + .5 * cos(pi * x / 16) + .08 * cos(2 * pi * x / 16);
            double value = sin(pi * x) / (pi * x) * window;
            meter->coefficients[phase][tap] = value;
            sum += value;
        }
        for (int tap = 0; tap < LEVEL_TAPS; tap++)
            meter->coefficients[phase][tap] /= sum;
    }
}

static bool level_process(const level_meter *meter, int16_t *audio, const double *filtered,
                          size_t count, int volume, level_result *result)
{
    if (!meter || !result || (count && !audio) || volume < 0 || volume > 100 ||
        count > (size_t)PTRDIFF_MAX - LEVEL_TAPS) return false;
    double peak = 0;
    for (size_t i = 0; i < count; i++) {
        double value = filtered ? filtered[i] : audio[i];
        if (!isfinite(value)) return false;
        peak = fmax(peak, fabs(value));
    }
    /* Measure reconstructed peaks, including boundary ringing, without filtering output. */
    if (peak > 0) {
        for (ptrdiff_t i = -16; i < (ptrdiff_t)count + 16; i++) {
            for (int phase = 0; phase < LEVEL_PHASES; phase++) {
                double value = 0;
                for (int tap = 0; tap < LEVEL_TAPS; tap++) {
                    ptrdiff_t index = i + tap - 15;
                    if (index >= 0 && index < (ptrdiff_t)count)
                        value += (filtered ? filtered[index] : audio[index]) * meter->coefficients[phase][tap];
                }
                peak = fmax(peak, fabs(value));
            }
        }
    }
    double ceiling = 32767 * pow(10, LEVEL_CEILING_DBTP / 20);
    double gain = peak > 0 ? fmin(LEVEL_NOMINAL_GAIN, ceiling / peak) : LEVEL_NOMINAL_GAIN;
    gain *= volume / 100.0;
    if (!isfinite(gain)) return false;
    for (size_t i = 0; i < count; i++) {
        long sample = lrint((filtered ? filtered[i] : audio[i]) * gain);
        if (sample < INT16_MIN || sample > INT16_MAX) return false;
        audio[i] = (int16_t)sample;
    }
    result->gain = gain;
    result->peak_before = peak;
    return true;
}

static bool level_apply(const level_meter *meter, int16_t *audio, size_t count,
                       int volume, level_result *result)
{
    return level_process(meter, audio, NULL, count, volume, result);
}
#endif
