"""Reading the streamed supplementary zip.

The endpoint returns an archive whose sizes sit in trailing descriptors, so entries are found by
scanning local headers. Every failure mode of that scan produces a file that looks fine: a
truncated deflate stream decompresses without raising, a stored entry with no recorded size runs
into whatever follows it, and the header signature occurs inside compressed data. Each of those
would be cached, hashed and served as a retrieved figure, so the tests here are about rejection.
"""
import io
import struct
import sys
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.article_figures import _entries

PNG = b'\x89PNG\r\n\x1a\n' + b'figure bytes ' * 800


def archive(files, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def streamed(name, data, compression=zipfile.ZIP_DEFLATED):
    """A local entry whose header carries zeros and whose sizes follow it, as the endpoint sends."""
    body = zlib.compress(data, 9)[2:-4] if compression == zipfile.ZIP_DEFLATED else data
    header = struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, 0x08, compression, 0, 0, 0, 0, 0,
                         len(name), 0) + name.encode()
    descriptor = struct.pack('<III', zlib.crc32(data), len(body), len(data))
    return header + body + b'PK\x07\x08' + descriptor


class ReadTests(unittest.TestCase):
    def test_a_whole_archive_reads_every_file(self):
        blob = archive({'a.png': PNG, 'b.jpg': PNG[:200]})
        self.assertEqual(_entries(blob), {'a.png': PNG, 'b.jpg': PNG[:200]})

    def test_a_streamed_entry_reads_from_its_trailing_descriptor(self):
        for compression in (zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED):
            with self.subTest(compression=compression):
                self.assertEqual(_entries(streamed('a.png', PNG, compression)), {'a.png': PNG})

    def test_a_stored_entry_does_not_absorb_what_follows_it(self):
        blob = archive({'a.png': PNG}, zipfile.ZIP_STORED)
        self.assertEqual(_entries(blob)['a.png'], PNG, 'the central directory is not part of the file')

    def test_a_truncated_download_is_dropped_rather_than_served_short(self):
        blob = archive({'a.png': PNG})
        cut = _entries(blob[:len(blob) // 2])
        self.assertNotIn('a.png', cut, 'a partial deflate stream decompresses without raising')

    def test_one_broken_entry_does_not_lose_the_others(self):
        blob = archive({'a.png': PNG, 'b.png': PNG[:600]})
        head = blob.find(b'PK\x03\x04', 4)  # the second entry
        name_length, extra = struct.unpack('<HH', blob[head + 26:head + 30])
        at = head + 30 + name_length + extra + 4  # inside its compressed data
        broken = blob[:at] + bytes([blob[at] ^ 0xFF]) + blob[at + 1:]
        result = _entries(broken)
        self.assertEqual(result.get('a.png'), PNG, 'the intact entry is still read')
        self.assertNotIn('b.png', result)

    def test_the_header_signature_inside_file_data_creates_no_entry(self):
        # Stored, so the signature survives into the archive exactly as written.
        blob = archive({'a.png': b'lead' + b'PK\x03\x04' + b'\x00' * 40 + b'tail'}, zipfile.ZIP_STORED)
        result = _entries(blob)
        self.assertEqual(len(result), 1, 'the false match must not become a second file')
        self.assertEqual(result['a.png'], b'lead' + b'PK\x03\x04' + b'\x00' * 40 + b'tail',
                         'and must not truncate the real one')

    def test_an_entry_whose_bytes_changed_is_dropped(self):
        blob = archive({'a.png': PNG}, zipfile.ZIP_STORED)
        at = blob.find(PNG)
        self.assertEqual(_entries(blob[:at] + b'X' + blob[at + 1:]), {},
                         'the recorded CRC is what says the bytes are the published ones')

    def test_an_empty_or_headerless_blob_reads_as_nothing(self):
        self.assertEqual(_entries(b''), {})
        self.assertEqual(_entries(b'not a zip at all'), {})
        self.assertEqual(_entries(b'PK\x03\x04'), {}, 'a header cut off mid-way is not an entry')


if __name__ == '__main__':
    unittest.main()
