"""Resolved rendering experiments and stable build identities.

Flags are process-scoped. A requested path must exist before it can be built;
silently ignoring an experimental flag would invalidate comparisons.
"""
import hashlib
import json
import os

FLAGS = {
    "compact_strips": "COMPACT_STRIPS",
    "incremental_certificate": "INCREMENTAL_CERTIFICATE",
    "camera_setup": "CAMERA_SETUP",
    "dynamic_tile_cache": "DYNAMIC_TILE_CACHE",
    "cache_key_mix": "CACHE_KEY_MIX",
    "narrow_yields": "NARROW_YIELDS",
    "attribute_padding": "ATTRIBUTE_PADDING",
    "anchor_packets": "ANCHOR_PACKETS",
    "packet_bounds_reuse": "PACKET_BOUNDS_REUSE",
    "physical_depth": "PHYSICAL_DEPTH",
    "actor_precision": "ACTOR_PRECISION",
    "scanline_admission": "SCANLINE_ADMISSION",
    "door_identity": "DOOR_IDENTITY",
    "near_field": "NEAR_FIELD",
    "foreground_publication": "FOREGROUND_PUBLICATION",
    "hdma_streaming": "HDMA_STREAMING",
    "textured_walls": "TEXTURED_WALLS",
    "overlap_publication": "OVERLAP_PUBLICATION",
}
IMPLEMENTED = {"compact_strips", "incremental_certificate", "camera_setup", "dynamic_tile_cache", "cache_key_mix", "attribute_padding", "narrow_yields", "anchor_packets", "packet_bounds_reuse", "physical_depth", "actor_precision", "scanline_admission", "door_identity", "projection_storage", "near_field", "foreground_publication", "hdma_streaming", "textured_walls", "overlap_publication"}
DEFAULTS = {"compact_strips", "camera_setup", "narrow_yields", "attribute_padding"}
# HBlank-streamed publication follows the display profile: it is the compact
# and slim production path, and the legacy profile keeps its staged VBlank
# packets byte for byte. Textured walls are the slim Sable default wherever
# they can run. Both are resolved after the display, below.
PROFILE_DEFAULTS = {"hdma_streaming", "textured_walls"}


def resolve(environ=None):
    env = os.environ if environ is None else environ
    result = {}
    for name, flag in FLAGS.items():
        if name in PROFILE_DEFAULTS: continue
        enabled = name in DEFAULTS
        # Preserve historical diagnostic commands. An explicit incompatible
        # request still fails below; only the implicit production default adapts.
        if name == "compact_strips" and env.get("LUPINE3D_FOLDED", "1") == "0": enabled = False
        if name == "camera_setup" and env.get("LUPINE3D_PREPARED_RAYS", "1") == "0": enabled = False
        if name == "narrow_yields" and env.get("LUPINE3D_REPROJECTION", "0") == "1": enabled = False
        value = env.get("LUPINE3D_" + flag, "1" if enabled else "0")
        if value not in ("0", "1"):
            raise ValueError(f"LUPINE3D_{flag} must be 0 or 1")
        result[name] = value == "1"
        if result[name] and name not in IMPLEMENTED:
            raise ValueError(f"{name} has not been implemented; refusing an ineffective flag")
    storage = env.get("LUPINE3D_PROJECTION_STORAGE", "direct")
    if storage not in ("direct", "paged256", "hybrid256"):
        raise ValueError("Unknown projection storage format")
    if storage != "direct" and "projection_storage" not in IMPLEMENTED:
        raise ValueError("Projection compaction has not been implemented")
    result["projection_storage"] = storage
    # The owner accepted the compact art tradeoff. Historical incompatible
    # diagnostics retain their implicit legacy profile; explicit conflicts fail.
    legacy_diagnostic = (env.get("LUPINE3D_REPROJECTION", "0") == "1"
                         or env.get("LUPINE3D_FIXED_SIM", "1") == "0"
                         or result["foreground_publication"])
    display = env.get("LUPINE3D_DISPLAY", "legacy" if legacy_diagnostic else "slim")
    art = env.get("LUPINE3D_ART", "legacy" if display == "legacy" or legacy_diagnostic else "sable-v2")
    animation = env.get("LUPINE3D_ART_ANIMATION", "1" if art == "sable-v2" else "0")
    if display not in ("legacy", "compact", "slim") or art not in ("legacy", "sable-v2"):
        raise ValueError("DISPLAY must be legacy/compact/slim; ART must be legacy/sable-v2")
    if animation not in ("0", "1") or (animation == "1" and art != "sable-v2"):
        raise ValueError("ART_ANIMATION requires sable-v2 art and a 0/1 value")
    if (display != "legacy" or art == "sable-v2") and (result["foreground_publication"] or env.get("LUPINE3D_REPROJECTION", "0") == "1"):
        raise ValueError("Compact display/new art exclude the experimental foreground/reprojection lanes")
    if (display != "legacy" or art == "sable-v2") and env.get("LUPINE3D_FIXED_SIM", "1") == "0":
        raise ValueError("Compact display/new art require accepted fixed simulation ticks")
    result.update(display=display, art=art, art_animation=animation == "1")
    streaming = env.get("LUPINE3D_HDMA_STREAMING", "0" if display == "legacy" else "1")
    if streaming not in ("0", "1"):
        raise ValueError("LUPINE3D_HDMA_STREAMING must be 0 or 1")
    result["hdma_streaming"] = streaming == "1"
    if result["hdma_streaming"] and (result["foreground_publication"] or env.get("LUPINE3D_REPROJECTION", "0") == "1"):
        raise ValueError("HBlank-streamed publication excludes the experimental foreground/reprojection lanes")
    # Textured walls (docs/TEXTURED_WALLS.md) compose every wall tile into a
    # ring the HBlank stream drains, so they need streaming; their texture
    # coordinates borrow the physical-depth window, so the two exclude each other.
    # They are the slim Sable default; the diagnostics they cannot run with
    # (the unfolded oracle, physical depth, anchor packets, no streaming)
    # adapt the implicit default to flat walls, and LUPINE3D_TEXTURED_WALLS=0
    # builds the flat slim profile. An explicit request that cannot run fails.
    textured_default = (display == "slim" and art == "sable-v2" and result["hdma_streaming"]
                        and not result["physical_depth"] and not result["anchor_packets"]
                        and env.get("LUPINE3D_FOLDED", "1") != "0")
    textured = env.get("LUPINE3D_TEXTURED_WALLS", "1" if textured_default else "0")
    if textured not in ("0", "1"):
        raise ValueError("LUPINE3D_TEXTURED_WALLS must be 0 or 1")
    result["textured_walls"] = textured == "1"
    if result["textured_walls"] and (display != "slim" or art != "sable-v2"):
        raise ValueError("Textured walls require the slim display and Sable art")
    if result["textured_walls"] and not result["hdma_streaming"]:
        raise ValueError("Textured walls require HBlank-streamed publication")
    if result["textured_walls"] and (result["physical_depth"] or result["anchor_packets"] or env.get("LUPINE3D_FOLDED", "1") == "0"):
        raise ValueError("Textured walls exclude physical depth, anchor packets and the unfolded diagnostic")
    # Overlapped publication hands the streamed VBlank tail to the VBlank
    # interrupt so the next update casts while it waits (docs/PERFORMANCE_PHASE5.md).
    if result["overlap_publication"] and not result["hdma_streaming"]:
        raise ValueError("Overlapped publication hands off the streamed tail; it requires HBlank streaming")
    if result["compact_strips"] and env.get("LUPINE3D_FOLDED", "1") == "0":
        raise ValueError("Compact strips require folded rendering; disable COMPACT_STRIPS for the unfolded oracle")
    if result["anchor_packets"] and (env.get("LUPINE3D_Q14", "1") == "0" or env.get("LUPINE3D_PREPARED_RAYS", "1") == "0"):
        raise ValueError("Anchor packets require Q14 ordering and prepared ray records")
    if result["packet_bounds_reuse"] and not result["anchor_packets"]:
        raise ValueError("Packet-bound reuse requires anchor packets")
    if result["cache_key_mix"] and not result["dynamic_tile_cache"]:
        raise ValueError("Cache-key mixing requires the dynamic-tile cache")
    if result["near_field"] and env.get("LUPINE3D_Q14", "1") == "0":
        raise ValueError("Near-field projection requires Q14 plane ordering")
    if result["camera_setup"] and env.get("LUPINE3D_PREPARED_RAYS", "1") == "0":
        raise ValueError("Camera setup hoisting requires prepared ray records")
    if result["narrow_yields"] and env.get("LUPINE3D_REPROJECTION", "0") == "1":
        raise ValueError("Narrow yields have no reprojection context contract; use generic yields")
    if result["foreground_publication"] and (not result["scanline_admission"] or env.get("LUPINE3D_REPROJECTION", "0") == "1"):
        raise ValueError("Foreground publication requires scanline admission and excludes reprojection")
    if result["foreground_publication"] and env.get("LUPINE3D_FIXED_SIM", "1") == "0":
        raise ValueError("Foreground events require fixed-tick simulation")
    return result


def identity(configuration):
    return hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


RENDER_CONFIG = resolve()
