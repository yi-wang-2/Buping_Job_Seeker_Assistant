"""Read historical Chromium localStorage values directly from copied LevelDB tables."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


MAGIC = b"\x57\xfb\x80\x8b\x24\x75\x47\xdb"


def varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise ValueError("invalid varint")


def snappy(data: bytes) -> bytes:
    expected, pos = varint(data)
    output = bytearray()
    while pos < len(data) and len(output) < expected:
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:
            length = tag >> 2
            if length < 60:
                length += 1
            else:
                size = length - 59
                length = int.from_bytes(data[pos:pos + size], "little") + 1
                pos += size
            output.extend(data[pos:pos + length])
            pos += length
            continue
        if kind == 1:
            length = 4 + ((tag >> 2) & 7)
            offset = ((tag & 0xE0) << 3) | data[pos]
            pos += 1
        elif kind == 2:
            length = 1 + (tag >> 2)
            offset = int.from_bytes(data[pos:pos + 2], "little")
            pos += 2
        else:
            length = 1 + (tag >> 2)
            offset = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4
        if offset <= 0 or offset > len(output):
            raise ValueError("invalid snappy copy offset")
        for _ in range(length):
            output.append(output[-offset])
    if len(output) != expected:
        raise ValueError("truncated snappy block")
    return bytes(output)


def read_block(table: bytes, offset: int, size: int) -> bytes:
    raw = table[offset:offset + size]
    compression = table[offset + size]
    if compression == 0:
        return raw
    if compression == 1:
        return snappy(raw)
    raise ValueError(f"unsupported compression {compression}")


def entries(block: bytes):
    if len(block) < 4:
        return
    restart_count = struct.unpack_from("<I", block, len(block) - 4)[0]
    end = len(block) - 4 * (restart_count + 1)
    pos = 0
    previous = b""
    while pos < end:
        shared, pos = varint(block, pos)
        suffix_size, pos = varint(block, pos)
        value_size, pos = varint(block, pos)
        key = previous[:shared] + block[pos:pos + suffix_size]
        pos += suffix_size
        value = block[pos:pos + value_size]
        pos += value_size
        previous = key
        yield key, value


def block_handle(data: bytes) -> tuple[int, int]:
    offset, pos = varint(data)
    size, _ = varint(data, pos)
    return offset, size


def block_handle_with_end(data: bytes) -> tuple[int, int, int]:
    offset, pos = varint(data)
    size, end = varint(data, pos)
    return offset, size, end


def table_entries(path: Path):
    table = path.read_bytes()
    if len(table) < 48 or table[-8:] != MAGIC:
        return
    _, _, pos = block_handle_with_end(table[-48:-8])
    index_offset, index_size = block_handle(table[-48 + pos:-8])
    index = read_block(table, index_offset, index_size)
    for _, handle in entries(index):
        offset, size = block_handle(handle)
        yield from entries(read_block(table, offset, size))


def decode_value(value: bytes):
    payload = value[1:] if value[:1] in {b"\x00", b"\x01"} else value
    candidates = [payload.decode("utf-16le", "ignore"), payload.decode("utf-8", "ignore")]
    for text in candidates:
        start = text.find("[")
        if start >= 0:
            try:
                parsed, _ = json.JSONDecoder().raw_decode(text[start:])
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--key", default="myJobTrackerV4")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--merge-into", type=Path)
    args = parser.parse_args()
    found = []
    for path in sorted(args.directory.glob("*.ldb")):
        try:
            for key, value in table_entries(path):
                if args.key.encode() not in key:
                    continue
                records = decode_value(value)
                if records is not None:
                    found.append((path.name, records))
        except (IndexError, ValueError, struct.error):
            continue
    for filename, records in found:
        recent = [record for record in records if str(record.get("applied_at", "")).startswith(("2026-09-10", "2026-09-11"))]
        print(json.dumps({"file": filename, "count": len(records), "recent": recent}, ensure_ascii=False))
    if args.output and found:
        _, records = max(found, key=lambda item: len(item[1]))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.merge_into and found:
        _, recovered = max(found, key=lambda item: len(item[1]))
        current = json.loads(args.merge_into.read_text(encoding="utf-8"))
        known_ids = {str(record.get("id")) for record in current}
        missing = [record for record in recovered if str(record.get("id")) not in known_ids]
        merged = current + missing
        temporary = args.merge_into.with_suffix(args.merge_into.suffix + ".recovery.tmp")
        temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(args.merge_into)
        print(json.dumps({"merged": len(missing), "total": len(merged)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
