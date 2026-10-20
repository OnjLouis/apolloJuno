#ifndef APOLLO_JUNO_PRONUNCIATION_H
#define APOLLO_JUNO_PRONUNCIATION_H

#include "firmware/data/fw_data.h"
#include <string.h>

enum { JUNO_RULE_STORAGE_START = 0x8000, LTS_PAIR_TABLE_BYTES = 26 * 2 };

static size_t rule_bytes(const fw_rule *rule)
{
    return strlen(rule->left) + strlen(rule->consumed) + strlen(rule->right) +
           strlen(rule->output) + 2;
}

static size_t encode_rule(uint8_t *target, const fw_rule *rule)
{
    size_t at = 0;
    for (size_t n = strlen(rule->left); n-- > 0;) target[at++] = (uint8_t)rule->left[n];
    target[at++] = (uint8_t)strlen(rule->consumed);
    memcpy(target + at, rule->consumed, strlen(rule->consumed));
    at += strlen(rule->consumed);
    memcpy(target + at, rule->right, strlen(rule->right));
    at += strlen(rule->right);
    target[at++] = (uint8_t)strlen(rule->output);
    memcpy(target + at, rule->output, strlen(rule->output));
    return at + strlen(rule->output);
}

static bool prepend_juno_rules(fw_image *image, uint16_t low, uint16_t high,
                               const fw_rule_list *original, const fw_rule *additions, size_t count)
{
    size_t size = 1;
    for (size_t i = 0; i < count; i++) size += rule_bytes(&additions[i]);
    for (size_t i = 0; i < original->count; i++) size += rule_bytes(&original->rules[i]);
    /* Keep copied lists outside the LOW overlay so both pair-table banks can
       read them. Allocate only unoccupied converted-ROM data. */
    size_t start = 0, free_bytes = 0;
    for (size_t address = JUNO_RULE_STORAGE_START; address < sizeof image->rom; address++) {
        if (image->rom_ok[address >> 3] & (1u << (address & 7))) free_bytes = 0;
        else if (++free_bytes == size) { start = address + 1 - size; break; }
    }
    if (!start) return false;
    size_t at = start;
    for (size_t i = 0; i < count; i++) at += encode_rule(image->rom + at, &additions[i]);
    for (size_t i = 0; i < original->count; i++) at += encode_rule(image->rom + at, &original->rules[i]);
    image->rom[at++] = 0xff;
    for (size_t address = start; address < at; address++)
        image->rom_ok[address >> 3] |= (uint8_t)(1u << (address & 7));
    image->rom[low] = (uint8_t)start;
    image->rom[high] = (uint8_t)(start >> 8);
    return true;
}

static bool juno_pronunciation(fw_image *image)
{
    /* Calibrate the private data image, not the recovered ROM or unrelated vowels. */
    const fw_rule_list *digits = tn_char_lists['1'];
    size_t at = image->rom[TN_CHAR_RULES_LO + '1'] |
                (image->rom[TN_CHAR_RULES_HI + '1'] << 8);
    unsigned replacements = 0;
    for (size_t i = 0; i < digits->count; i++) {
        const fw_rule *rule = &digits->rules[i];
        if (!strcmp(rule->output, " WQN ")) {
            size_t output = at + rule_bytes(rule) - strlen(rule->output);
            if (memcmp(image->rom + output, " WQN ", 5)) return false;
            image->rom[output + 2] = 'u';
            replacements++;
        }
        at += rule_bytes(rule);
    }
    if (replacements != 2) return false;
    static const fw_rule additions[] = {
        {" S", "", "MPLE ", "h"}, {" S", "", "MPLES ", "h"},
        {" S", "", "MPLED ", "h"}, {" S", "", "MPLER ", "h"},
        {" S", "", "MPLERS ", "h"}, {" S", "", "MPLING ", "h"},
        {" S", "", "MPLINGS ", "h"},
    };
    static const fw_rule terminal[] = {
        {" TER", "N", "AL ", "MiN"}, {" TER", "N", "ALS ", "MiN"},
        {" TER", "N", "ALLY ", "MiN"},
    };
    static const fw_rule says[] = {{" S", "", "S ", "e"}};
    /* MI consumes the N before IN can be reached. AY similarly wins over A.
       Keep each recovered list as the fallback for all other words. */
    const uint16_t mi = LTS_PAIRS_A + ('M' - 'A') * LTS_PAIR_TABLE_BYTES + ('I' - 'A') * 2;
    const uint16_t ay = LTS_PAIRS_A + ('Y' - 'A') * 2;
    return prepend_juno_rules(image, TN_CHAR_RULES_LO + 'A', TN_CHAR_RULES_HI + 'A',
                             tn_char_lists['A'], additions, sizeof additions / sizeof additions[0]) &&
           prepend_juno_rules(image, mi, mi + 1, lts_pair_lists['M' - 'A']['I' - 'A'],
                             terminal, sizeof terminal / sizeof terminal[0]) &&
           prepend_juno_rules(image, ay, ay + 1, lts_pair_lists[0]['Y' - 'A'], says, 1);
}
#endif
