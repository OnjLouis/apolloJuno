#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>
#include <math.h>
#include "engine/native_engine.h"
#include "firmware/data/fw_data.h"
#include "orpheus/juno_map.h"
#include "orpheus/orp_synth.h"
#include "output_level.h"
#include "juno_pronunciation.h"
#include "tone_controls.h"

enum { SPEAK = 1, QUIT = 2, READY = 100, AUDIO = 101, DONE = 102, ERROR = 103 };
enum { MAX_TEXT = 320, SETTING_BYTES = 6, MAX_PAYLOAD = MAX_TEXT + SETTING_BYTES, AUDIO_BYTES = 16384, MARK_SPACE = 82,
       MAX_GAIN_HALVINGS = 4, NOISE_LOW_ATTENUATION = 3, NOISE_HIGH_ATTENUATION = 20 };
static const double noise_pole_scale = .9;
static const char magic[4] = {'A', 'P', 'N', 'V'};

typedef struct { char magic[4]; uint32_t type, request, size; } header;
_Static_assert(sizeof(header) == 16, "protocol header size");
static native_engine engine;
static orp_synth voice;
static fw_image juno_image;
static bool juno_image_ready;
static bool juno_pronunciation_ready;
static level_meter output_meter;

static double filter_response(const orp_filter *filter, double omega)
{
    double nr = 1 + filter->d * cos(omega), ni = -filter->d * sin(omega);
    double dr = 1 - filter->b * cos(omega) - filter->c * cos(2 * omega);
    double di = filter->b * sin(omega) + filter->c * sin(2 * omega);
    return sqrt((nr * nr + ni * ni) / (dr * dr + di * di));
}

static void calibrate_noise_bands(void)
{
    for (int cascade = 0; cascade < 2; cascade++) {
        double gain = 1;
        for (int section = 0; section < 3; section++) {
            orp_filter *filter = &voice.fix[cascade * 3 + section];
            double radius = sqrt(-filter->c);
            double omega = acos(filter->b / (2 * radius));
            double before = filter_response(filter, omega);
            filter->b = 2 * radius * cos(omega * noise_pole_scale);
            gain *= before / filter_response(filter, omega * noise_pole_scale);
        }
        /* The renderer overwrites section zero's gain; compensate in section one. */
        voice.fix[cascade * 3 + 1].a *= gain;
    }
}

static void apply_juno_profile(void *user, board *b)
{
    (void)user;
    if (!juno_image_ready) {
        /* Measured on Juno 2.02: W5 caps at R6, W6 at R5, W7 at R4, W8 at R2.
           Keep the recovered Apollo 2.01 image immutable for other renderers. */
        static const uint8_t limits[] = {7, 7, 7, 7, 6, 5, 4, 2, 0};
        memcpy(&juno_image, b->fw->img, sizeof juno_image);
        memcpy(juno_image.rom + CMD_SPEED_LIMITS, limits, sizeof limits);
        juno_pronunciation_ready = juno_pronunciation(&juno_image);
        juno_image_ready = true;
    }
    b->fw->img = &juno_image;
    b->rom = juno_image.rom;
    /* @RR is ambiguous in the original command parser. Initialize the profile
       directly so exclamation stress cannot be mistaken for an intonation command.
       F=0x20 preserves the previous effective comma baseline. */
    static const uint8_t parameters[][2] = {
        {'A', 0xA9}, {'B', 0x29}, {'C', 0x07}, {'D', 0xE4}, {'E', 0xE3},
        {'F', 0x20}, {'K', 0x24}, {'L', 0x8B}, {'M', 0x0A}, {'N', 0x0D}, {'O', 0x0D},
        {'P', 0xA5}, {'Q', 0x3E}, {'R', 0x18}, {'S', 0x04}, {'T', 0xDE},
        /* Juno sustains later stressed vowels instead of dropping to the flat baseline. */
        {'Y', 0x1A},
    };
    for (size_t i = 0; i < sizeof parameters / sizeof parameters[0]; i++)
        fw_wr8(b->fw, (uint16_t)(PROS_PARAMS + parameters[i][0] - 'A'), parameters[i][1]);
}

static int send_message(uint32_t type, uint32_t request, const void *data, uint32_t size)
{
    header h = {{'A', 'P', 'N', 'V'}, type, request, size};
    return fwrite(&h, 1, sizeof h, stdout) == sizeof h &&
           (!size || fwrite(data, 1, size, stdout) == size) && fflush(stdout) == 0;
}

static int send_error(uint32_t request, const char *message)
{
    return send_message(ERROR, request, message, (uint32_t)strlen(message));
}

static int speak(uint32_t request, const uint8_t *payload, uint32_t size)
{
    if (size <= SETTING_BYTES || payload[0] < 1 || payload[0] > 9 || payload[1] > 15 ||
        payload[2] > 7 || payload[3] > 100 || payload[4] > TONE_MAX || payload[5] > TONE_MAX)
        return send_error(request, "Invalid speech settings or empty input.");
    for (uint32_t i = SETTING_BYTES; i < size; i++) {
        if (payload[i] < 32 || payload[i] > 126 || payload[i] == '@' || payload[i] == '_')
            return send_error(request, "Speech input must be plain English text.");
    }
    char input[MAX_TEXT + 32];
    int prefix = snprintf(input, sizeof input, "@W%X @F%X @R%X ",
                          payload[0], payload[1], payload[2]);
    if (prefix < 0 || (size_t)prefix + size - SETTING_BYTES >= sizeof input)
        return send_error(request, "Speech input is too long.");
    memcpy(input + prefix, payload + SETTING_BYTES, size - SETTING_BYTES);
    input[prefix + size - SETTING_BYTES] = '\0';
    frame_list frames = {0};
    engine_input in = {(const uint8_t *)input, strlen(input), true};
    native_watch watch = {.on_idle = apply_juno_profile};
    engine_status status = native_engine_run_input(&engine, NULL, &in, false, &frames, NULL, &watch);
    if (status != ENGINE_IDLE || !juno_pronunciation_ready) {
        frame_list_free(&frames);
        return send_error(request, "Apollo firmware did not complete this input.");
    }
    if (frames.count > SIZE_MAX / (ORP_FRAME_SAMPLES * sizeof(int16_t))) {
        frame_list_free(&frames);
        return send_error(request, "Apollo audio size exceeded its limit.");
    }
    size_t samples = frames.count * ORP_FRAME_SAMPLES;
    int16_t *audio = samples ? malloc(samples * sizeof *audio) : NULL;
    if (samples && !audio) {
        frame_list_free(&frames);
        return send_error(request, "There is not enough memory for Apollo audio.");
    }
    uint32_t gain_halvings = 0;
    for (;;) {
        orp_init(&voice);
        calibrate_noise_bands();
        /* Validate synthesis headroom before applying the output-level boost. */
        voice.final_f.a /= 1U << gain_halvings;
        voice.final_f.y1 /= 1U << gain_halvings;
        voice.final_f.y2 /= 1U << gain_halvings;
        for (size_t i = 0; i < frames.count; i++) {
            int16_t params[ORP_PARAMS];
            juno_map_frame(frames.frames[i], params);
            if (params[8] > 0)
                params[8] = (int16_t)(params[8] > NOISE_LOW_ATTENUATION ? params[8] - NOISE_LOW_ATTENUATION : 0);
            if (params[9] > 0)
                params[9] = (int16_t)(params[9] > NOISE_HIGH_ATTENUATION ? params[9] - NOISE_HIGH_ATTENUATION : 0);
            int pitch = params[13];
            int pulse = 2 * pitch - ((2 * pitch - (pitch >> 1)) * MARK_SPACE) / 100;
            params[14] = (int16_t)(pulse * 100 / 60);
            orp_frame(&voice, params, i == 0, audio + i * ORP_FRAME_SAMPLES);
        }
        if (!orp_clipped(&voice) || gain_halvings == MAX_GAIN_HALVINGS)
            break;
        gain_halvings++;
    }
    frame_list_free(&frames);
    if (orp_clipped(&voice)) {
        free(audio);
        return send_error(request, "Apollo audio exceeded its safe output range.");
    }
    level_result level;
    if (!tone_apply(&output_meter, audio, samples, payload[3], payload[4], payload[5], &level)) {
        free(audio);
        return send_error(request, "Apollo audio could not be adjusted safely.");
    }
    for (size_t offset = 0; offset < samples;) {
        size_t count = samples - offset;
        if (count > AUDIO_BYTES / 2)
            count = AUDIO_BYTES / 2;
        if (!send_message(AUDIO, request, audio + offset, (uint32_t)(count * 2))) {
            free(audio);
            return 0;
        }
        offset += count;
    }
    free(audio);
    return send_message(DONE, request, &gain_halvings, sizeof gain_halvings);
}

int main(void)
{
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    level_init(&output_meter);
    const uint32_t ready[2] = {2, 10000};
    if (!send_message(READY, 0, ready, sizeof ready))
        return 1;
    for (;;) {
        header h;
        size_t count = fread(&h, 1, sizeof h, stdin);
        if (!count && feof(stdin))
            return 0;
        if (count != sizeof h || memcmp(h.magic, magic, 4) || h.size > MAX_PAYLOAD)
            return 2;
        uint8_t payload[MAX_PAYLOAD];
        if (h.size && fread(payload, 1, h.size, stdin) != h.size)
            return 2;
        if (h.type == QUIT && !h.size)
            return 0;
        if (h.type != SPEAK || !h.request)
            return 2;
        if (!speak(h.request, payload, h.size))
            return 1;
    }
}
