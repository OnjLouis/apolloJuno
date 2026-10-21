#ifndef APOLLO_INLINE_COMMANDS_H
#define APOLLO_INLINE_COMMANDS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { MAX_INLINE_PREFIX = 192, INLINE_HEADER_BYTES = 4,
       INLINE_FULL_VOLUME = 15, INLINE_NO_EFFECT = 255, INLINE_PAUSE_EFFECT = 16 };

static bool inline_hex(uint8_t c)
{
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F');
}

/* Only audio settings, never serial, bank, query, reset or raw text commands. */
static bool inline_setting(const uint8_t *s, size_t n)
{
    if (n < 3 || s[0] != '@')
        return false;
    if (n == 6 && s[1] == 'U')
        return s[2] >= '0' && s[2] <= '9' && inline_hex(s[3]) && inline_hex(s[4]) &&
               (s[5] == '+' || s[5] == '-');
    if (n != 3)
        return false;
    uint8_t c = s[2];
    switch (s[1]) {
    case 'W': return c >= '1' && c <= '9';
    case 'F': return inline_hex(c) || c == '+' || c == '-';
    case 'R': return c >= '0' && c <= '7';
    case 'Q': return c >= '0' && c <= '9';
    case 'D': return inline_hex(c);
    case 'B': return c >= '1' && c <= '8';
    case 'K': case 'S': case 'P': case 'H': return c == '0' || c == '1';
    case 'V': return c >= '1' && c <= '6';
    default: return false;
    }
}

static bool inline_prefix_valid(const uint8_t *s, size_t n)
{
    if (n > MAX_INLINE_PREFIX)
        return false;
    size_t start = 0;
    for (size_t i = 0; i <= n; i++) {
        if (i != n && s[i] != ' ')
            continue;
        if (i == n && !n)
            return true;
        if (!inline_setting(s + start, i - start))
            return false;
        start = i + 1;
    }
    return true;
}

#endif
