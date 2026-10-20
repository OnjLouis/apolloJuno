#include <stdio.h>
#include <string.h>
#include "../native/tone_controls.h"

static double response_db(tone_filter f, double cosine)
{
    return 20 * log10(fabs((f.b0 + cosine*f.b1 + f.b2) / (1 + cosine*f.a1 + f.a2)));
}

int main(void)
{
    int failures = 0;
    for (int value = 0; value <= 100; value++) {
        double db = (value - 50) * 12.0 / 50;
        for (int high = 0; high <= 1; high++) {
            tone_filter filter = tone_shelf(high ? 2000 : 250, db, high != 0);
            if (fabs(response_db(filter, high ? -1 : 1) - db) > 1e-8 ||
                fabs(response_db(filter, high ? 1 : -1)) > 1e-8 ||
                fabs(filter.a2) >= 1 || 1 + filter.a1 + filter.a2 <= 0 ||
                1 - filter.a1 + filter.a2 <= 0) failures++;
        }
    }
    level_meter meter;
    level_init(&meter);
    int16_t input[1000], actual[1000], expected[1000];
    for (int i = 0; i < 1000; i++) input[i] = (int16_t)(15000 * sin(i * .13) + 7000 * sin(i * 2.7));
    memcpy(actual, input, sizeof input);
    memcpy(expected, input, sizeof input);
    level_result level;
    if (!level_apply(&meter, expected, 1000, 100, &level) ||
        !tone_apply(&meter, actual, 1000, 100, 50, 50, &level) ||
        memcmp(actual, expected, sizeof actual)) failures++;
    for (int bass = 0; bass <= 100; bass += 50) {
        for (int treble = 0; treble <= 100; treble += 50) {
            memcpy(actual, input, sizeof input);
            if (!tone_apply(&meter, actual, 1000, 100, bass, treble, &level)) failures++;
            for (int i = 0; i < 1000; i++) if (abs(actual[i]) > 27600) failures++;
        }
    }
    if (tone_apply(&meter, actual, 1000, 100, -1, 50, &level) ||
        tone_apply(&meter, actual, 1000, 100, 50, 101, &level)) failures++;
    printf("tone tests: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
