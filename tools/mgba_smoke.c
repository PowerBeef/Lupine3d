/* Independent, unmodified mGBA CPU/PPU. Optional explicit diagnostic scene. */
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/internal/gb/input.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
    if (argc != 3 && argc != 4) return 2;
    struct mCore *core = mCoreFind(argv[1]);
    if (!core || !core->init(core)) return 2;
    mCoreInitConfig(core, "lupine-independent-test");
    mCoreConfigSetValue(&core->config, "cgb.model", "CGB");
    core->opts.useBios = false;
    core->opts.skipBios = true;
    core->setVideoBuffer(core, pixels, 160);
    if (!mCoreLoadFile(core, argv[1])) return 2;
    core->reset(core);
    bool foreground_test=argc==4 && !strcmp(argv[3],"--foreground");
    if (argc == 4 && !foreground_test) {
        FILE *input=fopen(argv[3],"rb"); if (!input) return 2;
        unsigned pc=fgetc(input);pc|=fgetc(input)<<8;
        unsigned count=fgetc(input);count|=fgetc(input)<<8;
        int32_t current_pc=0;unsigned steps=0;
        while (steps++<5000000) {
            core->readRegister(core,"pc",&current_pc);if ((unsigned)current_pc==pc) break;
            core->step(core);
        }
        if ((unsigned)current_pc!=pc) return 3;
        for (unsigned i=0;i<count;++i) {
            int bank=fgetc(input),lo=fgetc(input),hi=fgetc(input),value=fgetc(input);
            if (value==EOF) return 2;
            if (bank) core->busWrite8(core,0xff70,bank);
            core->busWrite8(core,lo|hi<<8,value);
        }
        fclose(input);core->busWrite8(core,0xff70,1);
        unsigned serial=core->busRead8(core,0xc8b6);steps=0;
        while (core->busRead8(core,0xc8b6)==serial && steps++<5000000) core->step(core);
        if (core->busRead8(core,0xc8b6)==serial) return 3;
        core->runFrame(core);core->runFrame(core);capture(argv[2],"scene");
        unsigned max_objects=0;
        for (unsigned line=0;line<144;++line) {
            unsigned objects=0;
            for (unsigned i=0;i<40;++i) {
                int y=core->busRead8(core,0xfe00+i*4)-16;
                if (y<=(int)line && (int)line<y+16)objects++;
            }
            if(objects>max_objects)max_objects=objects;
        }
        printf("{\"passed\":%s,\"diagnostic_ram_writes\":true,\"patch_count\":%u,\"max_oam_per_scanline\":%u,\"dma_write_instrumentation\":false}\n",max_objects<=10?"true":"false",count,max_objects);
        core->deinit(core);return max_objects<=10?0:1;
    }
    unsigned initial_y = 0, initial_angle = 0, swaps = 0, previous_page = 0;
    unsigned presentations = 0, previous_serial = 0;
    unsigned foreground_publications=0,previous_foreground=0,mixed_world_oam=0;
    uint8_t previous_world_oam[120]={0};
    for (unsigned frame = 0; frame < 480; ++frame) {
        unsigned keys = 0;
        if ((frame >= 60 && frame < 120) || (frame >= 190 && frame < 250)) keys = 1 << GB_KEY_UP;
        if (frame == 125 || frame == 225) keys |= 1 << GB_KEY_B;
        if (frame >= 260 && frame < 320) keys = 1 << GB_KEY_RIGHT;
        if (frame == 330 || frame == 360) keys = 1 << GB_KEY_A;
        if (foreground_test && frame>=320)
            keys=(1<<GB_KEY_RIGHT) | (1<<(((frame/48)&1)?GB_KEY_UP:GB_KEY_DOWN)) | (frame%24==8?(1<<GB_KEY_A):0);
        core->setKeys(core, keys);
        core->runFrame(core);
        unsigned page = core->busRead8(core, 0xff40) & 8;
        if (page != previous_page) ++swaps;
        previous_page = page;
        unsigned serial = core->busRead8(core, 0xc8b6);
        if (foreground_test) {
            unsigned foreground=core->busRead8(core,0xc8c3);
            foreground_publications+=(foreground-previous_foreground)&255;
            for(unsigned i=0;i<120;++i) {
                uint8_t value=core->busRead8(core,0xfe28+i);
                if(foreground!=previous_foreground && serial==previous_serial && value!=previous_world_oam[i])mixed_world_oam++;
                previous_world_oam[i]=value;
            }
            previous_foreground=foreground;
        }
        presentations += (serial - previous_serial) & 255;
        previous_serial = serial;
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
    bool passed = moved && turned && opened && swaps >= 10 && presentations >= 30 && !overflow && !mixed_world_oam && (!foreground_test || foreground_publications>0);
    printf("{\"passed\":%s,\"lcd_frames\":480,\"page_swaps\":%u,\"presentations\":%u,\"moved\":%s,\"turned\":%s,\"starting_door_open\":%s,\"input_queue_overflow\":%u,\"foreground_publications\":%u,\"mixed_world_oam\":%u,\"bootstrap\":\"mGBA built-in skip-BIOS\",\"dma_write_instrumentation\":false}\n",
           passed ? "true" : "false", swaps, presentations, moved ? "true" : "false", turned ? "true" : "false", opened ? "true" : "false", overflow,foreground_publications,mixed_world_oam);
    core->deinit(core);
    return passed ? 0 : 1;
}
