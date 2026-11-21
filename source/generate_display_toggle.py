from pathlib import Path
from PIL import Image

art = Path("artwork")
with Path("display_toggle_art.h").open("w") as output:
    output.write("#pragma once\n#include <cstdint>\n\n")
    output.write("constexpr unsigned kToggleWidth = 72, kToggleHeight = 36;\n")
    for mode in ("Wide", "Standard"):
        with Image.open(art / f"Switch_to_{mode}.png") as source:
            pixels = source.convert("RGBA")
            if pixels.size != (72, 36):
                raise ValueError("Expected 72 x 36 toggle artwork")
            output.write(f"constexpr uint8_t kSwitchTo{mode}[] = {{\n")
            data = pixels.tobytes()
            for i in range(0, len(data), 24):
                output.write("    " + ", ".join(map(str, data[i:i+24])) + ",\n")
            output.write("};\n")
