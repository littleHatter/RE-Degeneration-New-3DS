from pathlib import Path
from struct import pack
from zlib import compress

from PIL import Image


def load(name, size):
    with Image.open(Path("artwork") / f"Renderer_{name}.png") as source:
        if source.size != size:
            raise ValueError(f"{name} must be {size[0]} by {size[1]}")
        return source.convert("RGBA")


screen = load("Base", (320, 240))
screen.alpha_composite(load("No", (160, 120)), (0, 120))
screen.alpha_composite(load("Yes", (160, 120)), (160, 120))
pixels = screen.convert("RGB").load()
framebuffer = bytearray()
for x in range(320):
    for y in range(239, -1, -1):
        r, g, b = pixels[x, y]
        framebuffer.extend(pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | b >> 3))

data = compress(framebuffer, 9)
with Path("renderer_menu_art.h").open("w") as output:
    output.write("#pragma once\n#include <cstdint>\n\nconstexpr uint8_t kRendererMenuArt[] = {\n")
    for i in range(0, len(data), 24):
        output.write("    " + ", ".join(map(str, data[i:i + 24])) + ",\n")
    output.write("};\n")
