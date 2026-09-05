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
}
IMPLEMENTED = {"compact_strips", "incremental_certificate", "camera_setup", "dynamic_tile_cache", "cache_key_mix", "attribute_padding", "narrow_yields", "anchor_packets", "packet_bounds_reuse", "physical_depth", "actor_precision", "scanline_admission", "door_identity", "projection_storage", "near_field", "foreground_publication"}
DEFAULTS = {"compact_strips", "camera_setup", "narrow_yields", "attribute_padding"}


def resolve(environ=None):
    env = os.environ if environ is None else environ
    result = {}
    for name, flag in FLAGS.items():
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
