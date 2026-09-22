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

static uint32_t pixels[160 * 144];

static uint32_t encode(GB_gameboy_t *gb, uint8_t r, uint8_t g, uint8_t b)
{
    (void) gb;
    return (r << 16) | (g << 8) | b;
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "ROM OUTPUT.bin [CGB_MODEL_HEX]\n"); return 2; }
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
    GB_set_turbo_mode(gb, true, false);
    unsigned frames = 0;
    while (frames < 600 && GB_read_memory(gb, 0xc0ff) != 0xa5) { GB_run_frame(gb); frames++; }
    bool done = GB_read_memory(gb, 0xc0ff) == 0xa5;
    FILE *file = fopen(argv[2], "wb");
    if (!file) { perror(argv[2]); return 2; }
    for (unsigned address = 0xc000; address < 0xc300; address++) fputc(GB_read_memory(gb, address), file);
    fclose(file);
    printf("{\"done\":%s,\"frames\":%u,\"model\":%u,\"cgb_mode\":%s}\n", done ? "true" : "false", frames,
           model, GB_is_cgb_in_cgb_mode(gb) ? "true" : "false");
    GB_dealloc(gb);
    return done ? 0 : 1;
}
