#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifdef LEGACY_LEVEL
static void scale(int16_t *audio, size_t count, int volume)
{
    for (size_t i = 0; i < count; i++)
        audio[i] = (int16_t)((int32_t)audio[i] * volume / 100);
}
#else
#include "../native/output_level.h"
static void scale(int16_t *audio, size_t count, int volume)
{
    level_meter meter;
    level_result result;
    level_init(&meter);
    if (!level_apply(&meter, audio, count, volume, &result)) {
        fprintf(stderr, "level processing failed\n");
    }
}
#endif

int main(void)
{
    int failures = 0;
    int16_t small[] = {0, 1000, -1000, 500, -500, 0};
    scale(small, 6, 100);
    if (small[1] != 2000 || small[2] != -2000 || small[3] != 1000) {
        fprintf(stderr, "FAIL: volume100 must supply the clean two-times boost\n");
        failures++;
    }
    int16_t half[] = {0, 1000, -1000, 0};
    scale(half, 4, 50);
    if (half[1] != 1000 || half[2] != -1000) failures++;
    int16_t mute[] = {32767, -32768, 200, -200};
    scale(mute, 4, 0);
    for (int i = 0; i < 4; i++) if (mute[i] != 0) failures++;
#ifndef LEGACY_LEVEL
    level_meter meter;
    level_result result;
    level_init(&meter);
    for (int kind = 0; kind < 3; kind++) {
        int16_t loud[128];
        for (int i = 0; i < 128; i++)
            loud[i] = kind == 0 ? 32767 : kind == 1 ? -32768 : (i % 2 ? -32768 : 32767);
        if (!level_apply(&meter, loud, 128, 100, &result)) failures++;
        if (!(result.gain > 0 && result.gain <= LEVEL_NOMINAL_GAIN)) failures++;
        for (int i = 0; i < 128; i++) if (abs(loud[i]) > 27600) failures++;
    }
    int16_t quiet[128] = {0};
    if (!level_apply(&meter, quiet, 128, 100, &result) || result.peak_before != 0) failures++;
    if (!level_apply(&meter, NULL, 0, 100, &result)) failures++;
    if (level_apply(&meter, quiet, 128, -1, &result)) failures++;
    if (level_apply(&meter, quiet, 128, 101, &result)) failures++;
#endif
    printf("level tests: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
