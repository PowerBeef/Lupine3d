/* Independent, unmodified mGBA CPU/PPU execution. No ROM/RAM patches. */
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/internal/gb/input.h>
#include <stdio.h>
#include <stdlib.h>

static mColor pixels[160 * 144];
static void capture(const char *prefix, const char *label) {
    char path[4096];
    snprintf(path, sizeof(path), "%s_%s.ppm", prefix, label);
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); exit(2); }
    fprintf(f, "P6\n160 144\n255\n");
    for (unsigned i = 0; i < 160 * 144; ++i) {
        /* Normalize both cores to the project's linear RGB15 convention. */
        for (unsigned shift = 0; shift < 24; shift += 8)
            fputc(((pixels[i] >> shift & 255) >> 3) * 255 / 31, f);
    }
    fclose(f);
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    struct mCore *core = mCoreFind(argv[1]);
    if (!core || !core->init(core)) return 2;
    mCoreInitConfig(core, "lupine-independent-test");
    mCoreConfigSetValue(&core->config, "cgb.model", "CGB");
    core->opts.useBios = false;
    core->opts.skipBios = true;
    core->setVideoBuffer(core, pixels, 160);
    if (!mCoreLoadFile(core, argv[1])) return 2;
    core->reset(core);
    unsigned initial_y = 0, initial_angle = 0, swaps = 0, previous_page = 0;
    for (unsigned frame = 0; frame < 480; ++frame) {
        unsigned keys = 0;
        if ((frame >= 60 && frame < 120) || (frame >= 190 && frame < 250)) keys = 1 << GB_KEY_UP;
        if (frame == 125 || frame == 225) keys |= 1 << GB_KEY_B;
        if (frame >= 260 && frame < 320) keys = 1 << GB_KEY_RIGHT;
        if (frame == 330 || frame == 360) keys = 1 << GB_KEY_A;
        core->setKeys(core, keys);
        core->runFrame(core);
        unsigned page = core->busRead8(core, 0xff40) & 8;
        if (page != previous_page) ++swaps;
        previous_page = page;
        if (frame == 59) {
            initial_angle = core->rawRead8(core, 0xd144, 1);
            initial_y = core->rawRead16(core, 0xd142, 1);
            capture(argv[2], "start");
        }
        if (frame == 239) capture(argv[2], "door_route");
    }
    capture(argv[2], "final");
    bool moved = core->rawRead16(core, 0xd142, 1) != initial_y;
    bool turned = core->rawRead8(core, 0xd144, 1) != initial_angle;
    bool opened = core->rawRead8(core, 0xd764, 1) == 2;
    unsigned overflow = core->busRead8(core, 0xc8d4);
    bool passed = moved && turned && opened && swaps >= 30 && !overflow;
    printf("{\"passed\":%s,\"lcd_frames\":480,\"page_swaps\":%u,\"moved\":%s,\"turned\":%s,\"starting_door_open\":%s,\"input_queue_overflow\":%u,\"bootstrap\":\"mGBA built-in skip-BIOS\",\"dma_write_instrumentation\":false}\n",
           passed ? "true" : "false", swaps, moved ? "true" : "false", turned ? "true" : "false", opened ? "true" : "false", overflow);
    core->deinit(core);
    return passed ? 0 : 1;
}
