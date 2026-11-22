"""Convert the supplied RGBA map artwork to the 3DS compositor's header."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent
declarations = ["#pragma once", "#include <cstdint>"]
for name, filename, size in (
    ("kMapOpen", "OpenMap.png", (32, 28)),
    ("kMapClose", "closemap.png", (32, 28)),
    ("kMapZone", "mapzone.png", (304, 176)),
    ("kMapLocked", "locked.png", (10, 10)),
    ("kMapUnlocked", "unlocked.png", (10, 10)),
    ("kMapPlayer", "player.png", (12, 12)),
    ("kMapMerchant", "merchant.png", (12, 12)),
    ("kMapObjective", "objective.png", (12, 12)),
    ("kMapTreasure", "treasure.png", (12, 12)),
    ("kMapUnavailable", "unavailable.png", (304, 176)),

):
    with Image.open(root / "artwork" / filename) as image:
        if image.size != size:
            raise ValueError(f"{filename} must be {size[0]} × {size[1]}")
        pixels = image.convert("RGBA").tobytes()
    declarations.append(f"inline constexpr uint8_t {name}[] = {{")
    for offset in range(0, len(pixels), 32):
        declarations.append(",".join(map(str, pixels[offset:offset + 32])) + ",")
    declarations.append("};")
(root / "map_art.h").write_text("\n".join(declarations) + "\n")
