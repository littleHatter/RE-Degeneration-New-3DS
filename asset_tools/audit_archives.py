"""Inventory the supplied Resident Evil DTRZ archives without modifying them.

Python 3 standard library only. This reader supports the flat file/path records
and LZMA stream layout observed in these three archives, not every DZ variant.
"""
import argparse
import collections
import hashlib
import json
import lzma
import pathlib
import re
import struct


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normal(path):
    return "/".join(part for part in path.replace("\\", "/").split("/") if part and part != ".").casefold()


def validate_lua(chunk):
    """Consume exactly one Lua 5.1 little-endian/int32 chunk; never execute it."""
    if chunk[:12] != b"\x1bLua\x51\x00\x01\x04\x04\x04\x04\x01":
        raise ValueError("unsupported Lua chunk layout")
    pos = 12

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(chunk):
            raise ValueError("truncated Lua chunk")
        value = chunk[pos:pos+n]
        pos += n
        return value

    def count():
        value = struct.unpack("<I", take(4))[0]
        if value > len(chunk):
            raise ValueError("invalid Lua count")
        return value

    def string():
        value = take(count())
        if value and value[-1] != 0:
            raise ValueError("unterminated Lua string")

    def function(depth=0):
        if depth > 64:
            raise ValueError("excessive Lua nesting")
        string()
        take(12)  # line numbers and four one-byte function properties
        take(count() * 4)
        for _ in range(count()):
            tag = take(1)[0]
            if tag == 1:
                take(1)
            elif tag == 3:
                take(4)
            elif tag == 4:
                string()
            elif tag != 0:
                raise ValueError("invalid Lua constant type")
        for _ in range(count()):
            function(depth+1)
        take(count() * 4)
        for _ in range(count()):
            string()
            take(8)
        for _ in range(count()):
            string()

    function()
    if pos != len(chunk):
        raise ValueError("trailing bytes after Lua chunk")


def embedded_lua(content):
    found = []
    for match in re.finditer(rb"(?:levels|common|localisation)[/\\][A-Za-z0-9_./\\-]+\.lua\x00", content):
        start = match.end() + 4
        if content[start:start+4] != b"\x1bLua":
            continue
        size = struct.unpack_from("<I", content, match.end())[0]
        chunk = content[start:start+size]
        try:
            validate_lua(chunk)
        except (ValueError, struct.error):
            continue
        found.append({"path": normal(match.group()[:-1].decode("ascii"))[:-4] + ".luc",
                      "offset": start, "bytes": len(chunk), "sha256": sha(chunk),
                      "header_hex": chunk[:12].hex()})
    return found


def inspect(path):
    data = pathlib.Path(path).read_bytes()
    if data[:4] != b"DTRZ":
        raise ValueError(str(path) + ": expected DTRZ, not an encrypted outer container")
    count, dirs = struct.unpack_from("<HH", data, 4)
    if not 0 < count < 10000 or not 0 < dirs < 10000:
        raise ValueError("unsupported file/directory count")
    pos, names = 9, []
    for _ in range(count + dirs - 1):
        end = data.index(0, pos)
        raw = data[pos:end]
        names.append({"text": raw.decode("ascii", errors="backslashreplace"),
                      "ascii": all(32 <= ch < 127 for ch in raw)})
        pos = end + 1
    directory_names = [{"text": "", "ascii": True}] + names[count:]
    table = pos + count * 6 + 4
    if table + count * 16 > len(data):
        raise ValueError("truncated file table")
    marker, records = struct.unpack_from("<HH", data, pos + count * 6)
    if (marker, records) != (1, count):
        raise ValueError("unsupported path-table layout")
    result = {"filename": pathlib.Path(path).name, "bytes": len(data), "sha256": sha(data),
              "file_count": count, "directory_count": dirs, "entries": []}
    for i in range(count):
        directory_id, file_id, terminator = struct.unpack_from("<3H", data, pos + i * 6)
        name = names[i]
        directory = directory_names[directory_id] if directory_id < dirs else None
        path_valid = (file_id == i and terminator == 65535 and directory is not None
                      and directory["ascii"] and name["ascii"])
        relative = (directory["text"] + "/" if directory else "") + name["text"]
        entry = {"index": i, "name": name["text"], "path": normal(relative),
                 "path_valid": path_valid, "path_record_valid": file_id == i and terminator == 65535,
                 "directory_ascii": bool(directory and directory["ascii"])}
        offset, length, length2, flags = struct.unpack_from("<4I", data, table + i * 16)
        entry.update(offset=offset, declared_bytes=length, flags=flags)
        try:
            if not table + count * 16 <= offset < len(data) or length != length2 or length > 64 * 1024 * 1024:
                raise ValueError("invalid stream offset/length metadata")
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
            content = decoder.decompress(data[offset:], max_length=length + 1)
            if not decoder.eof or len(content) != length:
                raise ValueError("stream does not reach its declared length and end marker")
            entry.update(decompression="valid", decoded_bytes=len(content), decoded_sha256=sha(content),
                         prefix_hex=content[:16].hex(), lua_signature_count=content.count(b"\x1bLua"))
            entry["embedded_lua"] = embedded_lua(content)
            if content.startswith(b"\x1bLua"):
                entry["kind"] = "Lua bytecode"
            elif name["text"].endswith(".group.bin"):
                entry["kind"] = "resource group"
                entry["group_header_prefix"] = content[:6].hex()
            else:
                entry["kind"] = "other"
        except (ValueError, lzma.LZMAError) as error:
            entry.update(decompression="invalid", error=str(error))
        result["entries"].append(entry)
    return result


def compare(original, protected, android):
    paths = collections.defaultdict(list)
    names = collections.defaultdict(list)
    scripts = collections.defaultdict(list)
    for entry in android["entries"]:
        if entry["path_valid"]:
            paths[entry["path"]].append(entry)
        names[entry["name"].casefold()].append(entry)
        for script in entry.get("embedded_lua", []):
            scripts[script["path"]].append(dict(script, container=entry["path"]))
    rows = []
    for entry in protected["entries"]:
        exact = paths.get(entry["path"], []) if entry["path_valid"] else []
        candidates = exact or names.get(entry["name"].casefold(), [])
        mode = "exact path" if exact else "filename candidate" if candidates else "no standalone entry in supplied Android archive"
        row = {"ngage_index": entry["index"], "ngage_path": entry["path"],
               "ngage_path_valid": entry["path_valid"], "ngage_decompression": entry["decompression"],
               "declared_ngage_bytes": entry["declared_bytes"], "match": mode,
               "android_candidates": [{"path": e["path"], "decompression": e["decompression"],
                                       "decoded_bytes": e.get("decoded_bytes"),
                                       "group_header_prefix": e.get("group_header_prefix"),
                                       "lua_signature_count": e.get("lua_signature_count", 0)} for e in candidates]}
        if len(candidates) == 1 and entry["decompression"] == "valid" and candidates[0]["decompression"] == "valid":
            other = candidates[0]
            row["same_decoded_bytes"] = entry["decoded_sha256"] == other["decoded_sha256"]
            if "group_header_prefix" in entry and "group_header_prefix" in other:
                row["same_group_header_prefix"] = entry["group_header_prefix"] == other["group_header_prefix"]
        # A successful decode or name match is deliberately never called runtime compatibility.
        row["runtime_compatible"] = "unverified"
        script_matches = scripts.get(entry["path"], []) if entry["path_valid"] else []
        script_match_mode = "exact path" if script_matches else "none"
        if not script_matches and entry["name"].endswith(".luc"):
            script_matches = [s for group in scripts.values() for s in group
                              if pathlib.PurePosixPath(s["path"]).name == entry["name"].casefold()]
            script_match_mode = "filename candidate" if script_matches else "none"
        row["embedded_android_lua"] = script_matches
        row["embedded_lua_match"] = script_match_mode
        if len(script_matches) == 1 and entry["decompression"] == "valid":
            row["embedded_lua_same_bytes"] = entry["decoded_sha256"] == script_matches[0]["sha256"]
        rows.append(row)
    common = []
    for entry in original["entries"]:
        matches = paths.get(entry["path"], [])
        if entry["path_valid"] and len(matches) == 1 and entry["decompression"] == "valid":
            other = matches[0]
            if other["decompression"] == "valid":
                common.append({"path": entry["path"], "ngage_bytes": entry["decoded_bytes"],
                               "android_bytes": other["decoded_bytes"],
                               "same_decoded_bytes": entry["decoded_sha256"] == other["decoded_sha256"],
                               "ngage_group_prefix": entry.get("group_header_prefix"),
                               "android_group_prefix": other.get("group_header_prefix")})
    return {"archives": {"ngage_main": original, "ngage_protected": protected, "android_main": android},
            "protected_comparison": rows, "common_main_entries": common,
            "limits": ["Filename-only matches are candidates, not confirmed path matches.",
                       "Declared lengths in transformed N-Gage metadata are not independently verified.",
                       "Different resource headers are observed; their version semantics are not inferred.",
                       "Missing standalone Lua files may be embedded, renamed, elsewhere in Android, or absent.",
                       "No automatic texture conversion or runtime compatibility claim is made."]}


def extract_candidates(report, android_path, destination):
    """Stage candidates separately; never overwrite a game installation."""
    archive = report["archives"]["android_main"]
    data = pathlib.Path(android_path).read_bytes()
    if sha(data) != archive["sha256"]:
        raise ValueError("Android archive changed after inspection")
    wanted = {candidate["path"] for row in report["protected_comparison"]
              for candidate in row["android_candidates"]}
    wanted_scripts = {script["path"] for row in report["protected_comparison"]
                      for script in row["embedded_android_lua"]}
    manifest = []

    def save(relative, payload, source, kind):
        path = pathlib.PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or ":" in relative:
            raise ValueError("unsafe candidate path")
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        manifest.append({"path": relative, "source": source, "kind": kind,
                         "bytes": len(payload), "sha256": sha(payload),
                         "runtime_compatible": "unverified"})

    for entry in archive["entries"]:
        scripts = [s for s in entry.get("embedded_lua", []) if s["path"] in wanted_scripts]
        if entry["path"] not in wanted and not scripts:
            continue
        if entry["decompression"] != "valid" or not entry["path_valid"]:
            continue
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        content = decoder.decompress(data[entry["offset"]:], max_length=entry["decoded_bytes"]+1)
        if sha(content) != entry["decoded_sha256"]:
            raise ValueError("candidate changed during extraction")
        if entry["path"] in wanted:
            save(entry["path"], content, entry["path"], "resource group candidate")
        for script in scripts:
            chunk = content[script["offset"]:script["offset"]+script["bytes"]]
            validate_lua(chunk)
            save(script["path"], chunk, entry["path"], "embedded Lua candidate")
    (destination / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def markdown(report):
    lines = ["# Resident Evil archive audit", "", "## Archive validation", "",
             "| Archive | Entries | Valid streams | Invalid streams | Invalid paths |",
             "|---|---:|---:|---:|---:|"]
    for key, archive in report["archives"].items():
        good = sum(e["decompression"] == "valid" for e in archive["entries"])
        invalid_paths = sum(not e["path_valid"] for e in archive["entries"])
        lines.append(f"| {key} | {archive['file_count']} | {good} | {archive['file_count']-good} | {invalid_paths} |")
    counts = collections.Counter(r["match"] for r in report["protected_comparison"])
    lines += ["", "## Coverage of all protected entries", ""]
    lines += [f"- {key}: **{value}**" for key, value in counts.items()]
    embedded = [row for row in report["protected_comparison"] if row["embedded_android_lua"]]
    identical = [row for row in embedded if row.get("embedded_lua_same_bytes")]
    lines += [f"- Embedded Android Lua matches: **{len(embedded)}** (counted separately from standalone files)",
              f"- Embedded Lua matches byte-identical to a valid N-Gage script: **{len(identical)}**"]
    lines += ["", "A match establishes availability, not runtime compatibility.", "",
              "| N-Gage protected path | Stream | Android match | Android decoded bytes |",
              "|---|---|---|---:|"]
    for row in report["protected_comparison"]:
        size = ", ".join(str(e.get("decoded_bytes", "?")) for e in row["android_candidates"])
        lines.append(f"| `{row['ngage_path']}` | {row['ngage_decompression']} | {row['match']} | {size or '—'} |")
    lines += ["", "## Shared resource groups", "",
              "| Path | N-Gage decoded bytes | Android decoded bytes | Header prefixes (N-Gage / Android) |",
              "|---|---:|---:|---|"]
    for row in report["common_main_entries"]:
        if row["ngage_group_prefix"]:
            lines.append(f"| `{row['path']}` | {row['ngage_bytes']} | {row['android_bytes']} | `{row['ngage_group_prefix']}` / `{row['android_group_prefix']}` |")
    lines += ["", "## Embedded Lua coverage", "",
              "| N-Gage script | Android container | Chunk bytes | Same bytes as valid N-Gage script |",
              "|---|---|---:|---|"]
    for row in embedded:
        for script in row["embedded_android_lua"]:
            same = row.get("embedded_lua_same_bytes", "N-Gage stream unavailable")
            lines.append(f"| `{row['ngage_path']}` | `{script['container']}` | {script['bytes']} | {same} |")
    lines += ["", "## Limits", ""] + ["- " + s for s in report["limits"]]
    lines += ["", "The direct Android-main experiment reached the first rendered frame, then the original",
              "N-Gage engine stopped with `Out of T-Pages`. Texture dimensions have not been decoded",
              "by this inventory; larger decoded groups alone do not establish the cause of that error."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ngage-main", required=True, type=pathlib.Path)
    parser.add_argument("--ngage-protected", required=True, type=pathlib.Path)
    parser.add_argument("--android-main", required=True, type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("audit_output"))
    parser.add_argument("--extract-candidates", action="store_true",
                        help="Stage validated Android groups and embedded Lua under output/candidates")
    args = parser.parse_args()
    report = compare(inspect(args.ngage_main), inspect(args.ngage_protected), inspect(args.android_main))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.extract_candidates:
        report["staged_candidates"] = extract_candidates(report, args.android_main, args.output / "candidates")
    (args.output / "inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output / "comparison.md").write_text(markdown(report), encoding="utf-8")
    counts = collections.Counter(r["match"] for r in report["protected_comparison"])
    print(json.dumps(dict(counts), indent=2))
    print("Wrote", args.output.resolve())


if __name__ == "__main__":
    main()
