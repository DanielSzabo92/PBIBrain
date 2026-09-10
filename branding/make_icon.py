"""Generate the small, original PBIBrain Windows icon without build dependencies."""

from pathlib import Path
import math
import struct
import zlib


def icon_png(size: int) -> bytes:
    # Supersampled connected nodes: a graph, readable down to a taskbar icon.
    def color(x: float, y: float) -> tuple[int, int, int, int]:
        radius = 0.19
        dx = max(abs(x - .5) - (.46 - radius), 0)
        dy = max(abs(y - .5) - (.46 - radius), 0)
        if math.hypot(dx, dy) > radius:
            return (0, 0, 0, 0)
        nodes = ((.30, .29), (.70, .41), (.37, .73))
        for index, (nx, ny) in enumerate(nodes):
            if math.hypot(x-nx, y-ny) < .098:
                return (113, 235, 195, 255) if index != 1 else (151, 198, 251, 255)
        for ax, ay, bx, by in ((*nodes[0], *nodes[1]), (*nodes[0], *nodes[2]), (*nodes[1], *nodes[2])):
            t = max(0, min(1, ((x-ax)*(bx-ax)+(y-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2)))
            if math.hypot(x-ax-t*(bx-ax), y-ay-t*(by-ay)) < .021:
                return (81, 160, 151, 255)
        return (20, 31, 38, 255)

    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            pixels = [color((x+(sx+.5)/4)/size, (y+(sy+.5)/4)/size) for sy in range(4) for sx in range(4)]
            raw.extend(round(sum(pixel[c] for pixel in pixels)/16) for c in range(4))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main() -> None:
    images = [(size, icon_png(size)) for size in (16, 32, 48, 64, 128, 256)]
    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, data in images:
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    Path(__file__).with_name("pbibrain.ico").write_bytes(directory + b"".join(data for _, data in images))


if __name__ == "__main__":
    main()
