/* Run a micro-ROM in an unmodified SameBoy core and dump WRAM $C000-$C2FF.
 *
 * Used by tools/harness_conformance.py: the ROM writes its final CPU state and
 * scratch memory into that window and then sets $C0FF to $A5. The dump is the
 * ground truth the project's own SM83 model (tools/sm83emu.py) is compared
 * with, instruction form by instruction form. The same original synthetic
 * bootstrap as tools/sameboy_smoke.c is used; this is not a boot-ROM test.
 *
 * Build: cc -I/path/to/SameBoy tools/sameboy_dump.c
 *        /path/to/SameBoy/build/lib/libsameboy.a -lm -ldl -o build/sameboy_dump
 * Usage: build/sameboy_dump ROM OUTPUT.bin [CGB_MODEL_HEX]
 */
#include <Core/gb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint32_t pixels[160 * 144];

/* SameBoy randomises power-on RAM, so $C0FF can already read $A5 before the
 * program runs (about one power-on image in 250). Completion is the ROM's own
 * write of $A5 there, seen by this hook, never a read of the byte. */
static bool finished_written;
static bool write_hook(GB_gameboy_t *gb, uint16_t address, uint8_t value)
{
    (void) gb;
    if (address == 0xc0ff && value == 0xa5) finished_written = true;
    return true;
}

static uint32_t encode(GB_gameboy_t *gb, uint8_t r, uint8_t g, uint8_t b)
{
    (void) gb;
    return (r << 16) | (g << 8) | b;
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "ROM OUTPUT.bin [CGB_MODEL_HEX]\n"); return 2; }
    GB_model_t model = argc > 3 ? strtoul(argv[3], NULL, 16) : GB_MODEL_CGB_E;
    /* LUPINE3D_SAMEBOY_SEED fixes the power-on RAM, as in sameboy_smoke.c. */
    const char *seed_text = getenv("LUPINE3D_SAMEBOY_SEED");
    unsigned long long seed = seed_text ? strtoull(seed_text, NULL, 10) : (unsigned long long)time(NULL);
    GB_random_seed(seed);
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
    GB_set_write_memory_callback(gb, write_hook);
    GB_set_turbo_mode(gb, true, false);
    unsigned frames = 0;
    while (frames < 600 && !finished_written) { GB_run_frame(gb); frames++; }
    bool done = finished_written && GB_read_memory(gb, 0xc0ff) == 0xa5;
    FILE *file = fopen(argv[2], "wb");
    if (!file) { perror(argv[2]); return 2; }
    for (unsigned address = 0xc000; address < 0xc300; address++) fputc(GB_read_memory(gb, address), file);
    fclose(file);
    printf("{\"done\":%s,\"frames\":%u,\"model\":%u,\"cgb_mode\":%s,\"seed\":%llu}\n", done ? "true" : "false", frames,
           model, GB_is_cgb_in_cgb_mode(gb) ? "true" : "false", seed);
    GB_dealloc(gb);
    return done ? 0 : 1;
}
