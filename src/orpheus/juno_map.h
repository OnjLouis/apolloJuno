#ifndef ORPHEUS_JUNO_MAP_H
#define ORPHEUS_JUNO_MAP_H
#include "orpheus/orp_synth.h"
#include "synth/synth.h"

/* Experimental Juno pitch calibration; the original Orpheus mapping is unchanged. */
void juno_map_frame(const uint8_t frame[SYNTH_FRAME_BYTES], int16_t params[ORP_PARAMS]);
#endif
