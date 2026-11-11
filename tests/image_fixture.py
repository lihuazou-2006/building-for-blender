"""Create an original synthetic PNG fixture; no bundled photo is required."""
import struct
import zlib


def make_test_image(path):
    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload +
                struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))
    size = 512
    rows = []
    for y in range(size):
        pixels = bytearray()
        for x in range(size):
            pixels.extend((x % 256, y % 256, (x + y) % 256))
        rows.append(b'\x00' + pixels)
    data = (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))
    path.write_bytes(data)
    return path
