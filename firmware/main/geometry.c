#include "geometry.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>

static void skip_space(const char **p)
{
    while (isspace((unsigned char)**p)) {
        (*p)++;
    }
}

// Reads a plain decimal number, without the sign and spaces strtoul would accept.
static bool read_number(const char **p, unsigned *out)
{
    if (!isdigit((unsigned char)**p)) {
        return false;
    }
    char *end;
    unsigned long n = strtoul(*p, &end, 10);
    if (n > 255) {
        return false;
    }
    *out = (unsigned)n;
    *p = end;
    return true;
}

// Reads "<a>x<b>" followed by whitespace or the end of the text.
static bool read_pair(const char **p, unsigned *a, unsigned *b)
{
    skip_space(p);
    if (!read_number(p, a) || **p != 'x') {
        return false;
    }
    (*p)++;
    return read_number(p, b) && (**p == '\0' || isspace((unsigned char)**p));
}

bool geometry_parse(const char *text, geometry_t *g, const char **err)
{
    const char *p = text;
    unsigned cols, rows, across, down;

    if (!read_pair(&p, &cols, &rows)) {
        *err = "expected the panel size as <columns>x<rows>, such as 28x16";
        return false;
    }
    if (cols < 1 || cols > GEOMETRY_MAX_PANEL_DOTS || rows < 1 || rows > GEOMETRY_MAX_PANEL_DOTS) {
        *err = "a panel has 1 to 28 dots each way";
        return false;
    }
    if (!read_pair(&p, &across, &down)) {
        *err = "expected the panel count as <across>x<down>, such as 4x2";
        return false;
    }
    if (across < 1 || down < 1 || across * down > GEOMETRY_MAX_PANELS) {
        *err = "there are 1 to 8 panels in total";
        return false;
    }

    *g = (geometry_t){
        .panel_cols = (uint8_t)cols,
        .panel_rows = (uint8_t)rows,
        .panels_x = (uint8_t)across,
        .panels_y = (uint8_t)down,
    };

    unsigned used = 0;
    for (unsigned i = 0; i < across * down; i++) {
        unsigned sel;
        skip_space(&p);
        if (!read_number(&p, &sel) || sel >= GEOMETRY_MAX_PANELS) {
            *err = "expected a COL-SEL line from 0 to 7 for every panel";
            return false;
        }
        bool rotated = *p == 'r';
        if (rotated) {
            p++;
        }
        if (*p != '\0' && !isspace((unsigned char)*p)) {
            *err = "a panel is its COL-SEL line, followed by r if it is rotated";
            return false;
        }
        // Two panels on one line would both flip every dot meant for either.
        if (used & (1u << sel)) {
            *err = "two panels share a COL-SEL line";
            return false;
        }
        used |= 1u << sel;
        g->panels[i] = (panel_t){.sel = (uint8_t)sel, .rotated = rotated};
    }
    skip_space(&p);
    if (*p != '\0') {
        *err = "more panels listed than the panel count";
        return false;
    }

    g->width = (uint16_t)(cols * across);
    g->height = (uint16_t)(rows * down);
    g->stride = (uint16_t)((g->width + 7) / 8);
    g->frame_bytes = (uint16_t)(g->stride * g->height);
    return true;
}

void geometry_format(const geometry_t *g, char *buf, size_t size)
{
    int n = snprintf(buf, size, "%ux%u %ux%u", g->panel_cols, g->panel_rows, g->panels_x, g->panels_y);
    for (int i = 0; i < g->panels_x * g->panels_y && n >= 0 && (size_t)n < size; i++) {
        n += snprintf(buf + n, size - n, " %u%s", g->panels[i].sel, g->panels[i].rotated ? "r" : "");
    }
}
