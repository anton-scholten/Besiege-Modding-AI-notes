#!/usr/bin/env python3
"""Reads a Unity 5.4 asset bundle and prints the prefab hierarchies inside it.

    python3 tools/unbundle.py <bundle>                 every root, with components
    python3 tools/unbundle.py <bundle> Window          just the roots matching a name
    python3 tools/unbundle.py <bundle> Window --fields  ... and each component's fields

This is how UI Factory's `Window` prefab was read rather than guessed: which
children it has, which components sit on them, and what every serialised field on
those components is set to. `strings` on the bundle gets you names in file order;
this gets you the structure.

No dependencies beyond the standard library and `lz4` (Debian: python3-lz4). LZMA
blocks use the stdlib `lzma`.

What it does, in order: unwrap the UnityFS container (header, block table, blocks,
directory), parse the SerializedFile inside it (version 15, with type trees), then
read each object generically by walking its type tree. Unity's type trees carry
enough information to decode an object without knowing the class, which is what
makes this short.
"""

import lzma
import struct
import sys

try:
    import lz4.block
except ImportError:
    sys.exit("This needs lz4: apt install python3-lz4  (or pip install lz4)")


# ---------------------------------------------------------------- the container

def unwrap(path):
    """UnityFS -> the bytes of the SerializedFile inside it."""
    d = open(path, "rb").read()

    def cstr(o):
        e = d.index(b"\0", o)
        return d[o:e].decode(), e + 1

    sig, o = cstr(0)
    if sig != "UnityFS":
        raise SystemExit("not a UnityFS bundle: %s" % sig)
    (version,) = struct.unpack_from(">I", d, o); o += 4
    _unity, o = cstr(o)
    _revision, o = cstr(o)
    size, comp_info, raw_info, flags = struct.unpack_from(">qIII", d, o); o += 20

    blob = d[o:o + comp_info]; o += comp_info
    info = decompress(blob, raw_info, flags & 0x3F)

    q = 16  # skip the hash
    (count,) = struct.unpack_from(">i", info, q); q += 4
    blocks = []
    for _ in range(count):
        raw, comp, bflags = struct.unpack_from(">IIH", info, q); q += 10
        blocks.append((raw, comp, bflags))

    out = b""
    for raw, comp, bflags in blocks:
        out += decompress(d[o:o + comp], raw, bflags & 0x3F)
        o += comp
    return out


def decompress(chunk, raw_size, method):
    if method in (2, 3):                      # LZ4 / LZ4HC
        return lz4.block.decompress(chunk, uncompressed_size=raw_size)
    if method == 1:                           # LZMA, 5-byte props then raw data
        header = chunk[:5] + struct.pack("<Q", raw_size)
        return lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(
            header + chunk[5:])
    return chunk


# ------------------------------------------------------------- SerializedFile

# Unity's built-in string table for type-tree names, indexed by byte offset. An
# offset with the top bit set indexes this rather than the file's own buffer.
COMMON_STRINGS = (
    "AABB\0AnimationClip\0AnimationCurve\0AnimationState\0Array\0Base\0BitField\0"
    "bitset\0bool\0char\0ColorRGBA\0Component\0data\0deque\0double\0dynamic_array\0"
    "FastPropertyName\0first\0float\0Font\0GameObject\0Generic Mono\0GradientNEW\0"
    "GUID\0GUIStyle\0int\0list\0long long\0map\0Matrix4x4f\0MdFour\0MonoBehaviour\0"
    "MonoScript\0m_ByteSize\0m_Curve\0m_EditorClassIdentifier\0m_EditorHideFlags\0"
    "m_Enabled\0m_ExtensionPtr\0m_GameObject\0m_Index\0m_IsArray\0m_IsStatic\0"
    "m_MetaFlag\0m_Name\0m_ObjectHideFlags\0m_PrefabInternal\0m_PrefabParentObject\0"
    "m_Script\0m_StaticEditorFlags\0m_Type\0m_Version\0Object\0pair\0"
    "PPtr<Component>\0PPtr<GameObject>\0PPtr<Material>\0PPtr<MonoBehaviour>\0"
    "PPtr<MonoScript>\0PPtr<Object>\0PPtr<Prefab>\0PPtr<Sprite>\0PPtr<TextAsset>\0"
    "PPtr<Texture>\0PPtr<Texture2D>\0PPtr<Transform>\0Prefab\0Quaternionf\0Rectf\0"
    "RectInt\0RectOffset\0second\0set\0short\0size\0SInt16\0SInt32\0SInt64\0SInt8\0"
    "staticvector\0string\0TextAsset\0TextMesh\0Texture\0Texture2D\0Transform\0"
    "TypelessData\0UInt16\0UInt32\0UInt64\0UInt8\0unsigned int\0"
    "unsigned long long\0unsigned short\0vector\0Vector2f\0Vector3f\0Vector4f\0"
    "m_ScriptingClassIdentifier\0Gradient\0")

COMMON = {}
_off = 0
for _s in COMMON_STRINGS.split("\0"):
    COMMON[_off] = _s
    _off += len(_s) + 1


class Reader(object):
    def __init__(self, d, o=0):
        self.d, self.o = d, o

    def u8(self):
        v = self.d[self.o]; self.o += 1; return v

    def i8(self):
        v, = struct.unpack_from("<b", self.d, self.o); self.o += 1; return v

    def i16(self):
        v, = struct.unpack_from("<h", self.d, self.o); self.o += 2; return v

    def u16(self):
        v, = struct.unpack_from("<H", self.d, self.o); self.o += 2; return v

    def i32(self):
        v, = struct.unpack_from("<i", self.d, self.o); self.o += 4; return v

    def u32(self):
        v, = struct.unpack_from("<I", self.d, self.o); self.o += 4; return v

    def i64(self):
        v, = struct.unpack_from("<q", self.d, self.o); self.o += 8; return v

    def f32(self):
        v, = struct.unpack_from("<f", self.d, self.o); self.o += 4; return v

    def f64(self):
        v, = struct.unpack_from("<d", self.d, self.o); self.o += 8; return v

    def cstr(self):
        e = self.d.index(b"\0", self.o)
        s = self.d[self.o:e].decode("utf8", "replace"); self.o = e + 1; return s

    def align(self, n=4):
        self.o = (self.o + n - 1) // n * n


class Node(object):
    __slots__ = ("type", "name", "size", "index", "is_array", "level", "meta",
                 "children")

    def __init__(self):
        self.children = []


def read_type_tree(r):
    count = r.i32()
    buffer_size = r.i32()
    flat = []
    for _ in range(count):
        n = Node()
        r.i16()                       # node version
        n.level = r.u8()
        n.is_array = r.u8()
        type_off, name_off = r.u32(), r.u32()
        n.size, n.index, n.meta = r.i32(), r.i32(), r.i32()
        flat.append((n, type_off, name_off))
    names = r.d[r.o:r.o + buffer_size]; r.o += buffer_size

    def name_at(off):
        if off & 0x80000000:
            return COMMON.get(off & 0x7FFFFFFF, "?")
        return names[off:names.index(b"\0", off)].decode()

    for n, t, m in flat:
        n.type, n.name = name_at(t), name_at(m)

    root = flat[0][0]
    stack = [root]
    for n, _, _ in flat[1:]:
        while len(stack) > n.level:
            stack.pop()
        stack[-1].children.append(n)
        stack.append(n)
    return root


def parse(data):
    meta_size, file_size, version, data_offset = struct.unpack_from(">IIII", data, 0)
    if version != 15:
        print("warning: SerializedFile version %d, this was written for 15" % version,
              file=sys.stderr)
    r = Reader(data, 20)
    r.cstr()                          # unity version
    r.i32()                           # target platform
    has_trees = r.u8() != 0
    if not has_trees:
        raise SystemExit("bundle has no type trees; nothing generic can be read")

    types = {}
    for _ in range(r.i32()):
        class_id = r.i32()
        if class_id < 0:
            r.o += 16                 # script id
        r.o += 16                     # old type hash
        types[class_id] = read_type_tree(r)

    objects = []
    for _ in range(r.i32()):
        r.align(4)
        path_id = r.i64()
        start, size, type_id = r.u32(), r.u32(), r.i32()
        class_id, r.o = r.i16(), r.o + 2
        r.o += 3                      # script type index (2) + stripped (1)
        objects.append(dict(path_id=path_id, start=data_offset + start, size=size,
                            type_id=type_id, class_id=class_id))
    return data, types, objects


def read_value(r, node):
    t = node.type
    align = (node.meta & 0x4000) != 0
    if t in ("SInt32", "int"):                       v = r.i32()
    elif t in ("UInt32", "unsigned int", "Type*"):   v = r.u32()
    elif t in ("SInt16", "short"):                   v = r.i16()
    elif t in ("UInt16", "unsigned short"):          v = r.u16()
    elif t == "SInt8":                               v = r.i8()
    elif t in ("UInt8", "char"):                     v = r.u8()
    elif t == "bool":                                v = r.u8() != 0
    elif t == "float":                               v = r.f32()
    elif t == "double":                              v = r.f64()
    elif t in ("SInt64", "long long"):               v = r.i64()
    elif t in ("UInt64", "unsigned long long", "FileSize"): v = r.i64()
    elif t == "string":
        n = r.i32()
        v = r.d[r.o:r.o + n].decode("utf8", "replace"); r.o += n
        r.align(4)
    elif node.is_array:
        n = r.i32()
        v = [read_value(r, node.children[1]) for _ in range(n)]
    elif node.children and node.children[0].is_array:
        v = read_value(r, node.children[0])
    else:
        v = {}
        for c in node.children:
            v[c.name] = read_value(r, c)
    if align:
        r.align(4)
    return v


# --------------------------------------------------------------------- output

CLASSES = {1: "GameObject", 4: "Transform", 224: "RectTransform",
           222: "CanvasRenderer", 114: "MonoBehaviour", 115: "MonoScript",
           28: "Texture2D", 213: "Sprite", 21: "Material", 48: "Shader",
           223: "Canvas", 142: "AssetBundle", 128: "Font"}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    want = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None
    fields = "--fields" in sys.argv

    data, types, objects = parse(unwrap(sys.argv[1]))

    by_id = {}
    for o in objects:
        try:
            o["v"] = read_value_root(data, o, types)
        except Exception as e:                 # a class we cannot decode is not fatal
            o["v"] = {"__error": str(e)}
        by_id[o["path_id"]] = o

    def script_name(o):
        s = o["v"].get("m_Script")
        if isinstance(s, dict):
            m = by_id.get(s.get("m_PathID"))
            if m:
                return m["v"].get("m_ClassName", "?")
        return "?"

    def go_of(rect):
        return by_id.get(rect["v"]["m_GameObject"]["m_PathID"])

    def components(go):
        out = []
        for c in go["v"].get("m_Component", []):
            pid = (c["component"]["m_PathID"] if "component" in c
                   else c["second"]["m_PathID"])
            comp = by_id.get(pid)
            if comp is None:
                continue
            name = CLASSES.get(comp["class_id"], str(comp["class_id"]))
            if comp["class_id"] == 114:
                name = script_name(comp)
            out.append((name, comp))
        return out

    def dump(rect, depth=0):
        go = go_of(rect)
        v = rect["v"]
        geometry = ""
        if rect["class_id"] == 224:
            a, b = v["m_AnchorMin"], v["m_AnchorMax"]
            sd, ap, pv = v["m_SizeDelta"], v["m_AnchoredPosition"], v["m_Pivot"]
            geometry = ("  anchors=(%g,%g)-(%g,%g) size=(%g,%g) pos=(%g,%g) pivot=(%g,%g)"
                        % (a["x"], a["y"], b["x"], b["y"], sd["x"], sd["y"],
                           ap["x"], ap["y"], pv["x"], pv["y"]))
        comps = components(go)
        print("  " * depth + go["v"].get("m_Name", "?") +
              "  [" + ", ".join(n for n, _ in comps) + "]" + geometry)
        if fields:
            for name, comp in comps:
                if comp["class_id"] != 114:
                    continue
                print("  " * (depth + 1) + "-- " + name)
                for k, val in comp["v"].items():
                    if k.startswith("m_Object") or k in ("m_GameObject", "m_Script",
                                                         "m_PrefabInternal",
                                                         "m_PrefabParentObject"):
                        continue
                    print("  " * (depth + 2) + "%-26s %s" % (k, str(val)[:120]))
        for child in v.get("m_Children", []):
            kid = by_id.get(child["m_PathID"])
            if kid:
                dump(kid, depth + 1)

    for o in objects:
        if o["class_id"] not in (4, 224):
            continue
        if o["v"].get("m_Father", {}).get("m_PathID") != 0:
            continue
        go = go_of(o)
        if go is None:
            continue
        if want and want.lower() not in go["v"].get("m_Name", "").lower():
            continue
        dump(o)
        print()


def read_value_root(data, o, types):
    r = Reader(data, o["start"])
    tree = types[o["type_id"]]
    return dict((c.name, read_value(r, c)) for c in tree.children)


if __name__ == "__main__":
    main()
