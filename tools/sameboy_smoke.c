/* Independent CPU/PPU smoke test using an unmodified SameBoy core.
 * Build: cc -I/path/to/SameBoy tools/sameboy_smoke.c
 *        /path/to/SameBoy/build/lib/libsameboy.a -lm -ldl -o build/sameboy_smoke
 * Usage: build/sameboy_smoke ROM OUTPUT_PREFIX [CGB_MODEL_HEX]
 * The tiny original bootstrap is NOT a Nintendo or SameBoy boot-ROM test.
 */
#include <Core/gb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t pixels[160 * 144];
static unsigned swaps, unsafe_dma, unsafe_flips, dma_starts, frame;
static unsigned presentations, reused, unsafe_presentations, unsafe_oam, visible_mask_writes;
static unsigned foreground_publications, mixed_world_oam;

static uint32_t encode(GB_gameboy_t *gb, uint8_t r, uint8_t g, uint8_t b)
{
    (void) gb;
    /* Compare in the project's documented linear RGB15->RGB24 convention.
     * SameBoy's disabled-correction channel expansion rounds differently. */
    r = (r >> 3) * 255 / 31;
    g = (g >> 3) * 255 / 31;
    b = (b >> 3) * 255 / 31;
    return (r << 16) | (g << 8) | b;
}

static bool write_hook(GB_gameboy_t *gb, uint16_t address, uint8_t value)
{
    uint8_t lcdc = GB_read_memory(gb, 0xff40);
    if (address == 0xff55 && !(value & 0x80) && (lcdc & 0x80)) {
        dma_starts++;
        if (GB_read_memory(gb, 0xff44) < 144) unsafe_dma++;
        if ((GB_read_memory(gb, 0xff53) & 31) < 2) {
            unsigned bank = GB_read_memory(gb, 0xff4f) & 1;
            for (unsigned i = 10; i < 26; ++i) {
                unsigned y = GB_read_memory(gb, 0xfe00 + i*4);
                if (y && y < 160 && ((GB_read_memory(gb, 0xfe03 + i*4) >> 3) & 1) == bank)
                    visible_mask_writes++;
            }
        }
    }
    if (address == 0xff46 && (lcdc & 0x80) &&
        (GB_read_memory(gb, 0xff44) < 144 || GB_read_memory(gb, 0xff44) >= 153)) unsafe_oam++;
    if (address == 0xff46 && value == 0xd0 && (lcdc & 0x80)) {
        for (unsigned i = 40; i < 160; ++i)
            if (GB_read_memory(gb, 0xd000+i) != GB_read_memory(gb, 0xfe00+i)) mixed_world_oam++;
    }
    if (address == 0xc8c3 && (lcdc & 0x80)) foreground_publications++;
    if (address == 0xc8b6 && (lcdc & 0x80)) {
        presentations++;
        reused += GB_read_memory(gb, 0xc8b5) != 0;
        if (GB_read_memory(gb, 0xff44) < 144 || GB_read_memory(gb, 0xff44) >= 153) unsafe_presentations++;
    }
    if (address == 0xff40 && (lcdc & value & 0x80) && ((lcdc ^ value) & 8)) {
        swaps++;
        if (GB_read_memory(gb, 0xff44) < 144) unsafe_flips++;
    }
    return true;
}

static void capture(const char *prefix, const char *label)
{
    char path[4096];
    snprintf(path, sizeof(path), "%s_%s.ppm", prefix, label);
    FILE *file = fopen(path, "wb");
    if (!file) { perror(path); exit(2); }
    fprintf(file, "P6\n160 144\n255\n");
    for (unsigned i = 0; i < 160 * 144; i++) {
        fputc(pixels[i] >> 16, file);
        fputc(pixels[i] >> 8, file);
        fputc(pixels[i], file);
    }
    fclose(file);
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "ROM OUTPUT_PREFIX [CGB_MODEL_HEX]\n"); return 2; }
    GB_model_t model = argc > 3 ? strtoul(argv[3], NULL, 16) : GB_MODEL_CGB_E;
    GB_gameboy_t *gb = GB_init(GB_alloc(), model);
    if (!gb || GB_load_rom(gb, argv[1])) return 2;
    unsigned char boot[0x100] = {0};
    const unsigned char startup[] = {
        0xf3, 0x31, 0xfe, 0xff, 0xaf, 0xe0, 0x0f, 0xea, 0xff, 0xff,
        0x3e, 0x91, 0xe0, 0x40, 0xc3, 0xfc, 0x00
    };
    memcpy(boot, startup, sizeof(startup));
    boot[0xfc] = 0x3e; boot[0xfd] = 0x11; boot[0xfe] = 0xe0; boot[0xff] = 0x50;
    GB_load_boot_rom_from_buffer(gb, boot, sizeof(boot));
    GB_set_pixels_output(gb, pixels);
    GB_set_rgb_encode_callback(gb, encode);
    GB_set_color_correction_mode(gb, GB_COLOR_CORRECTION_DISABLED);
    GB_set_write_memory_callback(gb, write_hook);
    GB_set_turbo_mode(gb, true, false);
    bool foreground_test=argc>4 && !strcmp(argv[4],"--foreground");
    if (argc > 4 && !foreground_test) {
        /* Explicit diagnostic frozen-scene lane; the normal controller lane
         * above/below retains its no-RAM-patch behavior. Format: LE PC/count,
         * then count records [bank, address low, address high, value]. */
        FILE *input = fopen(argv[4], "rb");
        if (!input) return 2;
        unsigned pc = fgetc(input); pc |= fgetc(input) << 8;
        unsigned count = fgetc(input); count |= fgetc(input) << 8;
        unsigned steps = 0;
        while (GB_get_registers(gb)->pc != pc && steps++ < 5000000) GB_run(gb);
        if (GB_get_registers(gb)->pc != pc) return 3;
        for (unsigned i=0; i<count; ++i) {
            int bank=fgetc(input), lo=fgetc(input), hi=fgetc(input), value=fgetc(input);
            if (value == EOF) return 2;
            if (bank) GB_write_memory(gb, 0xff70, bank);
            GB_write_memory(gb, lo | hi << 8, value);
        }
        fclose(input); GB_write_memory(gb, 0xff70, 1);
        unsigned serial=GB_read_memory(gb,0xc8b6); steps=0;
        while (GB_read_memory(gb,0xc8b6)==serial && steps++<5000000) GB_run(gb);
        if (GB_read_memory(gb,0xc8b6)==serial) return 3;
        GB_run_frame(gb); GB_run_frame(gb); capture(argv[2],"scene");
        unsigned max_objects=0;
        for (unsigned line=0; line<144; ++line) {
            unsigned objects=0;
            for (unsigned i=0; i<40; ++i) {
                int y=GB_read_memory(gb,0xfe00+i*4)-16;
                if (y<=(int)line && (int)line<y+16) objects++;
            }
            if (objects>max_objects) max_objects=objects;
        }
        bool passed=!unsafe_dma && !unsafe_oam && !visible_mask_writes && !mixed_world_oam && max_objects<=10;
        printf("{\"passed\":%s,\"diagnostic_ram_writes\":true,\"patch_count\":%u,\"max_oam_per_scanline\":%u,\"unsafe_gdma_starts\":%u,\"unsafe_oam_starts\":%u,\"visible_mask_writes\":%u,\"mixed_world_oam\":%u}\n",
               passed?"true":"false",count,max_objects,unsafe_dma,unsafe_oam,visible_mask_writes,mixed_world_oam);
        GB_dealloc(gb); return passed?0:1;
    }
    unsigned initial_angle = 0, initial_y = 0;
    for (frame = 0; frame < 480; frame++) {
        unsigned keys = 0;
        if (frame >= 60 && frame < 120) keys = GB_KEY_UP_MASK;
        if (frame >= 190 && frame < 250) keys = GB_KEY_UP_MASK;
        if (frame == 125 || frame == 225) keys |= GB_KEY_B_MASK; /* one-frame pulses */
        if (frame >= 260 && frame < 320) keys = GB_KEY_RIGHT_MASK;
        if (frame == 330 || frame == 360) keys = GB_KEY_A_MASK;
        if (foreground_test && frame>=320)
            keys=GB_KEY_RIGHT_MASK | (((frame/48)&1)?GB_KEY_UP_MASK:GB_KEY_DOWN_MASK) | (frame%24==8?GB_KEY_A_MASK:0);
        GB_set_key_mask(gb, keys);
        GB_run_frame(gb);
        if (frame == 59) {
            initial_angle = GB_read_memory(gb, 0xd144);
            initial_y = GB_read_memory(gb, 0xd142) | GB_read_memory(gb, 0xd143) << 8;
            capture(argv[2], "start");
        }
        if (frame == 239) capture(argv[2], "door_route");
    }
    capture(argv[2], "final");
    unsigned angle = GB_read_memory(gb, 0xd144);
    unsigned y = GB_read_memory(gb, 0xd142) | GB_read_memory(gb, 0xd143) << 8;
    bool door_open = GB_read_memory(gb, 0xd764) == 2;
    bool passed = presentations >= 30 && reused > 0 && swaps >= 10 && dma_starts >= 30
        && !unsafe_dma && !unsafe_flips && !unsafe_presentations && !unsafe_oam && !visible_mask_writes
        && !mixed_world_oam && (!foreground_test || foreground_publications>0)
        && angle != initial_angle && y != initial_y && door_open && GB_is_cgb_in_cgb_mode(gb);
    printf("{\"passed\":%s,\"model\":%u,\"lcd_frames\":%u,\"page_swaps\":%u,"
           "\"gdma_starts\":%u,\"unsafe_gdma_starts\":%u,\"unsafe_page_flips\":%u,"
           "\"presentations\":%u,\"reused_presentations\":%u,\"unsafe_presentations\":%u,\"unsafe_oam_starts\":%u,\"visible_mask_writes\":%u,"
           "\"foreground_publications\":%u,\"mixed_world_oam\":%u,\"moved\":%s,\"turned\":%s,\"starting_door_open\":%s,\"bootstrap\":\"original minimal synthetic bootstrap\"}\n",
           passed ? "true" : "false", model, frame, swaps, dma_starts, unsafe_dma,
           unsafe_flips, presentations, reused, unsafe_presentations, unsafe_oam, visible_mask_writes,
           foreground_publications, mixed_world_oam,
           y != initial_y ? "true" : "false", angle != initial_angle ? "true" : "false",
           door_open ? "true" : "false");
    GB_dealloc(gb);
    return passed ? 0 : 1;
}
