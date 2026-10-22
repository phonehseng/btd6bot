"""Decode Bloons TD 6's simulation model (the `sim_model` TextAsset) into JSON.

What this is
------------
Every tower, upgrade, hero and bloon the game simulates is described by one
binary file: the 17 MB TextAsset `sim_model` inside the game_model bundle
(BloonsTD6_Data/StreamingAssets/aa/StandaloneWindows64/Full/
game_model_assets_all_<hash>.bundle). The game reads it with a generated
class, `GameModelLoader`, which is plain sequential BinaryReader code. There
is no schema in the file itself: the order of the values is only written down
in that loader's code.

So this tool does two things:

1. It *derives the file format* from the loader's code, as decompiled by
   Cpp2IL into ISIL (a simple instruction listing: numbered statements such
   as "Move rax, [rdx+552]" and "Call rax"). For every per-type routine
   `Set_v_<Type>_Fields` it works out, statement by statement, which
   BinaryReader method is called and into which field of the object the
   result is stored. The main `Load` routine gives the order of the sections.
   Nothing about the field order is typed in by hand.
2. It *replays* that format with its own small reader in Python and writes
   the parts the bot needs as JSON under data/game_model/: towers, upgrades,
   heroes and bloons from sim_model, English names from the localization
   bundle, and the difficulty price multipliers from the game_data bundle.
   btd6bot/gamemodel.py reads those files for the bot.

Rules followed (the project's own): only copies of the game's files are read
(from ~/.btd6bot_cache), nothing of the game is modified, no game code or
DLL is run, and no mod is used. The decompiled code is only read as text.
docs/game_model.md explains the format and this decoder in more detail.

Usage
-----
    python tools/decode_sim_model.py            # re-extract if the bundle changed
    python tools/decode_sim_model.py --force    # re-extract anyway
    python tools/decode_sim_model.py --sync-placement
                                                # copy footprints etc. into data/placement.json
    python tools/decode_sim_model.py --dump TowerModel DartMonkey
                                                # print one decoded object (debugging)

Inputs (all copies in ~/.btd6bot_cache, all read-only):
    bundles/game_model_assets_all_*.bundle      the sim_model TextAsset
    bundles/game_data_assets_all_*.bundle       difficulty / mode "Mod" assets
    bundles/localization_assets_all_*.bundle    the "English" text table
    il2cpp/out/isil/IsilDump/Assembly-CSharp/GameModelLoader.txt   (Cpp2IL ISIL)
    il2cpp/out/cs/DiffableCs/...                class declarations (field offsets)
    il2cpp/in/GameAssembly.dll                  only its PE header (load address)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

log = logging.getLogger("decode_sim_model")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "game_model"
CACHE = Path.home() / ".btd6bot_cache"
BUNDLE_CACHE = CACHE / "bundles"
CPP2IL_OUT = CACHE / "il2cpp" / "out"
ISIL_FILE = CPP2IL_OUT / "isil" / "IsilDump" / "Assembly-CSharp" / "GameModelLoader.txt"
DECL_ROOT = CPP2IL_OUT / "cs" / "DiffableCs"
LOADER_DECL = DECL_ROOT / "Assembly-CSharp" / "GameModelLoader.cs"
READER_DECL = DECL_ROOT / "mscorlib" / "System" / "IO" / "BinaryReader.cs"
OBJECT_DECL = DECL_ROOT / "mscorlib" / "System" / "Object.cs"
GAME_ASSEMBLY = CACHE / "il2cpp" / "in" / "GameAssembly.dll"

# Bump when the JSON written by this tool changes shape, so the next refresh
# re-extracts even though the game itself has not updated.
EXTRACT_VERSION = 1


# ===========================================================================
# 1. Reading Cpp2IL's output
# ===========================================================================
#
# The ISIL dump lists every method of GameModelLoader as
#
#     Method: System.Void Set_v_TowerModel_Fields(System.Int32 start, ...)
#     Disassembly: ... (x86 assembly, ignored here)
#     ISIL:
#         001 Move rdi, rcx
#         002 Call GameModelLoader.Set_v_EntityModel_Fields, rcx, rdx, r8
#         ...
#
# Each ISIL statement is "number opcode operands". We keep them as tuples.

def read_isil(path=ISIL_FILE):
    """{method name: [(statement number, opcode, operand text), ...]}.

    The method name is the bare identifier ("Set_v_TowerModel_Fields",
    "Load"), which is unique inside GameModelLoader."""
    methods, current, in_isil = {}, None, False
    statement = re.compile(r"\t(\d+) (\S+) ?(.*)$")
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("Method: "):
                m = re.search(r"([\w.`<>]+)\(", line)
                current = m.group(1).split(".")[-1] if m else line[8:]
                methods[current] = []
                in_isil = False
            elif line == "ISIL:":
                in_isil = True
            elif in_isil and current and line.startswith("\t"):
                m = statement.match(line)
                if m:
                    methods[current].append((int(m.group(1)), m.group(2), m.group(3)))
    return methods


# --- C# declarations (fields with their memory offsets, enums) -------------
#
# Cpp2IL's "DiffableCs" output has one file per class with lines such as
#     public float cost; //Field offset: 0x58
# The loader stores values with "Move [rbx+88], xmm0": offset 88 = 0x58 names
# the field. Only top-level members (one tab of indentation) belong to the
# class itself; deeper ones belong to nested compiler-generated classes.

_FIELD = re.compile(r"^\t(?P<mods>(?:(?:public|private|protected|internal|static|readonly|const|new|volatile)\s+)+)"
                    r"(?P<type>.+?)\s+(?P<name>[^\s;]+);\s*//Field offset: 0x(?P<off>[0-9A-Fa-f]+)")
_CLASS = re.compile(r"^(?:\w+\s+)*(?:class|struct)\s+(?P<name>[\w`]+)(?:<[^>]*>)?(?:\s*:\s*(?P<bases>.+))?$")
_ENUM_VALUE = re.compile(r"^\t(?P<name>\w+) = (?P<value>-?\d+),?")


class Declarations:
    """Index of Cpp2IL's class declaration files, read on demand."""

    def __init__(self, root=DECL_ROOT):
        self.root = root
        self.by_short = defaultdict(list)   # "TowerModel" -> [paths]
        for path in root.rglob("*.cs"):
            self.by_short[path.stem].append(path)
        self._cache = {}

    def find(self, short, full=None):
        """(declaration file, nested class name or None) for a class, or None.

        `full` ("Assets.Scripts.Models.Towers.TowerModel") picks between
        classes that share a short name. A nested class is written
        "Outer+Inner" by IL2CPP and lives inside Outer's file."""
        if full and "+" in full:
            outer_full, inner = full.rsplit("+", 1)
            outer = self.find(outer_full.split(".")[-1], outer_full)
            return (outer[0], inner) if outer else None
        paths = self.by_short.get(short, [])
        if full and len(paths) > 1:
            want = full.replace(".", "/") + ".cs"
            for p in paths:
                if p.as_posix().endswith(want):
                    return (p, None)
        return (paths[0], None) if paths else None

    def parse(self, key):
        """{'parent': name, 'fields': {offset: (name, type)}, 'enum': {value: name}}
        of the class `key` = (file, nested name or None) from find()."""
        if key in self._cache:
            return self._cache[key]
        path, nested = key
        info = {"parent": None, "fields": {}, "enum": {}}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if nested:   # keep only the nested class's block, one indent less
            block, inside = [], False
            for line in lines:
                if not inside and line.startswith("\t") and not line.startswith("\t\t"):
                    m = _CLASS.match(line[1:])
                    inside = bool(m and m.group("name") == nested)
                    if inside:
                        block.append(line[1:])
                    continue
                if inside:
                    if line == "\t}":
                        break
                    block.append(line[1:])
            lines, wanted = block, nested
        else:
            wanted = path.stem
        for line in lines:
            if not line.startswith("\t"):
                m = _CLASS.match(line)
                if m and m.group("name") == wanted:
                    bases = (m.group("bases") or "").split(",")
                    info["parent"] = bases[0].strip().split("<")[0] or None
                continue
            m = _FIELD.match(line)
            if m and "static" not in m.group("mods") and "const" not in m.group("mods"):
                info["fields"][int(m.group("off"), 16)] = (m.group("name"), m.group("type"))
                continue
            m = _ENUM_VALUE.match(line)
            if m:
                info["enum"][int(m.group("value"))] = m.group("name")
        self._cache[key] = info
        return info

    def enum(self, short):
        """{value: name} of an enum declared in its own file ({} if unknown)."""
        key = self.find(short)
        return self.parse(key)["enum"] if key else {}


# --- The BinaryReader's virtual method table --------------------------------
#
# The loader calls the reader through its vtable: "Move rax, [rdx+552]" then
# "Call rax". In this IL2CPP version a class's vtable starts 0x138 bytes into
# its class structure and every entry is 16 bytes (code pointer + method
# info), so byte offset = 0x138 + 16 * slot. Slots are numbered in declaration
# order of the virtual methods, after the 4 inherited from System.Object
# (Equals, Finalize, GetHashCode, ToString). The declaration order is the
# metadata token order in BinaryReader.cs, so the slot of each Read* method is
# derived from that file rather than typed in.

VTABLE_START = 0x138
VTABLE_ENTRY = 16


def reader_slots(path=READER_DECL, object_path=OBJECT_DECL):
    """{vtable byte offset: method name} and {slot number: method name}."""
    def virtual_methods(text):
        out = []   # (token, name)
        token = None
        for line in text.splitlines():
            m = re.search(r'\[Token\(Token = "0x([0-9A-F]+)"\)\]', line)
            if m:
                token = int(m.group(1), 16)
                continue
            m = re.match(r"\t(?:public|protected|private|internal)[^(]*\b(?:virtual|override|abstract)\b.*?\s(\w+)\(", line)
            if m and token is not None:
                out.append((token, m.group(1)))
            if line.strip() and not line.strip().startswith("["):
                token = None
        return [name for _, name in sorted(set(out))]

    inherited = 4
    if object_path.exists():   # System.Object's own virtual methods
        inherited = len(virtual_methods(object_path.read_text(encoding="utf-8", errors="replace"))) or 4
    names = virtual_methods(path.read_text(encoding="utf-8", errors="replace"))
    by_slot = {inherited + i: n for i, n in enumerate(names)}
    by_offset = {VTABLE_START + VTABLE_ENTRY * s: n for s, n in by_slot.items()}
    return by_offset, by_slot


def loader_fields(path=LOADER_DECL):
    """GameModelLoader's own layout: field offsets of br / m / mIndex, the
    BindingFlags constant used for reflection, and helper RVAs by name."""
    text = path.read_text(encoding="utf-8", errors="replace")
    fields = {m.group(2): int(m.group(3), 16)
              for m in re.finditer(r"(\w[\w\[\]]*) (\w+); //Field offset: 0x([0-9A-F]+)", text)}
    flags = re.search(r"bindFlags = (\d+)", text)
    rvas = {}
    for m in re.finditer(r'RVA = "0x([0-9A-F]+)".*?\n.*?\n\s*(?:private|public)[^(]*?\s(\w+)\(', text):
        rvas[int(m.group(1), 16)] = m.group(2)
    return {"reader": fields["br"], "table": fields["m"], "index": fields["mIndex"],
            "bind_flags": int(flags.group(1)) if flags else None, "rvas": rvas}


def image_base(dll=GAME_ASSEMBLY, default=0x180000000):
    """Preferred load address of GameAssembly.dll (from the PE header of the
    cached copy): ISIL call targets are absolute, the declarations give RVAs."""
    try:
        with open(dll, "rb") as f:
            head = f.read(4096)
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        return struct.unpack_from("<Q", head, pe + 24 + 24)[0]   # PE32+ ImageBase
    except (OSError, struct.error):
        return default


# ===========================================================================
# 2. Deriving the format from the loader's code
# ===========================================================================
#
# A tiny symbolic walk over a method's statements, in order, ignoring jumps
# (the generated code is straight-line apart from small if/else diamonds).
# It tracks what each register or stack slot holds, just enough to recognise:
#
#   "this"           the loader (rcx on entry)
#   "reader"         this.br                    ([this+0x10])
#   "table"          this.m, the object table   ([this+0x18])
#   "obj"            the object being filled    (an element of the table)
#   ("read", k)      the result of the k-th BinaryReader call
#   ("ref", k)       table[read k]: the k-th read was an object reference
#   ("fieldinfo", n) a FieldInfo from Type.GetField("n"), for private fields
#
# and to emit events: reads, stores into the object (by field offset or
# through FieldInfo.SetValue), comparisons of a read against 0 (the
# "ReadBoolean() ? null : ReadString()" pattern), and the call to the parent
# type's routine.

VOLATILE = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11",
            "xmm0", "xmm1", "xmm2", "xmm3", "xmm4", "xmm5")


class Walk:
    """Events of one method: see the comment above."""

    def __init__(self, body, layout, slots_by_offset, slots_by_number, bind_flags):
        self.layout = layout
        self.slots_by_offset = slots_by_offset
        self.slots_by_number = slots_by_number
        self.bind_flags = bind_flags
        self.val = {"rcx": "this"}
        self.events = []          # ("read", k, method) / ("store", target) / ("call", name) / ("loop_end", n)
        self.reads = []           # method name per read k
        self.cond = set()         # reads compared with 0 (bools guarding a string)
        self.is_ref = set()       # reads used as an index into the object table
        for n, op, args in body:
            self.step(n, op, args)

    # -- operands ----------------------------------------------------------
    def get(self, operand):
        operand = operand.strip()
        if operand.startswith('"'):
            return ("str", operand.strip('"'))
        if operand.startswith("typeof("):
            return ("type", operand[7:-1])
        if re.fullmatch(r"-?(0x[0-9A-Fa-f]+|\d+)", operand):
            return ("const", int(operand, 0))
        m = re.fullmatch(r"\[(\w+)\+(0x[0-9A-Fa-f]+|\d+)\]", operand)
        if m:
            base, off = self.val.get(m.group(1)), int(m.group(2), 0)
            if base == "this" and off == self.layout["reader"]:
                return "reader"
            if base == "this" and off == self.layout["table"]:
                return "table"
            if base == "reader" and off == 0:
                return "reader_vtable"
            if base == "reader_vtable":
                return ("reader_method", off)
            if base == "table":                     # [table + precomputed offset]
                return "obj"
            return self.val.get(operand)
        m = re.fullmatch(r"\[(\w+)\]", operand)
        if m:
            return "reader_vtable" if self.val.get(m.group(1)) == "reader" else None
        m = re.fullmatch(r"\[(\w+)\+(\w+)\]", operand)          # [r15+rbx]
        if m and "table" in (self.val.get(m.group(1)), self.val.get(m.group(2))):
            return "obj"
        m = re.fullmatch(r"\[(\w+)\+32\+(\w+)\*8\]", operand)   # table[index]
        if m and self.val.get(m.group(1)) == "table":
            index = self.val.get(m.group(2))
            if isinstance(index, tuple) and index[0] == "read":
                self.is_ref.add(index[1])
                return ("ref", index[1])
            return "obj"
        return self.val.get(operand)

    def put(self, operand, value):
        self.val[operand.strip()] = value

    # -- statements --------------------------------------------------------
    def read(self, method):
        k = len(self.reads)
        self.reads.append(method)
        self.events.append(("read", k, method))
        for r in VOLATILE:
            self.val.pop(r, None)
        self.val["rax"] = self.val["xmm0"] = ("read", k)

    def step(self, n, op, args):
        parts = [a.strip() for a in args.split(",")] if args else []
        if op in ("Move", "LoadAddress") and len(parts) >= 2:
            dst, src = parts[0], ",".join(parts[1:])
            m = re.fullmatch(r"\[(\w+)\+(0x[0-9A-Fa-f]+|\d+)\]", dst)
            if op == "Move" and m and self.val.get(m.group(1)) == "obj":
                self.events.append(("store", ("offset", int(m.group(2), 0))))
                return
            new = self.get(src) if op == "Move" else ("address", src)
            if self.val.get(dst) == "obj" and new == ("const", 0):
                return   # the "object is null" branch of a cast check: keep tracking the object
            self.put(dst, new)
        elif op == "Compare" and len(parts) == 2 and parts[1] == "0":
            v = self.val.get(parts[0])
            if isinstance(v, tuple) and v[0] == "read":
                self.cond.add(v[1])
        elif op == "Call" and parts:
            self.call(parts[0])
        elif op.startswith("Jump") or op == "Goto":
            m = re.search(r"\{(\d+)\}", args)
            if m and int(m.group(1)) < n:     # a backward jump closes a loop
                self.events.append(("loop_end", int(m.group(1))))

    def call(self, target):
        result = None
        if re.fullmatch(r"r\w+", target):                 # an indirect (virtual) call
            callee = self.val.get(target)
            if isinstance(callee, tuple) and callee[0] == "reader_method" and self.val.get("rcx") == "reader":
                self.read(self.slots_by_offset.get(callee[1], f"slot@{callee[1]}"))
                return
            # Type.GetField(name, bindFlags): a virtual call with a string
            # literal and the loader's BindingFlags constant
            name, flags = self.val.get("rdx"), self.val.get("r8")
            if isinstance(name, tuple) and name[0] == "str" and flags == ("const", self.bind_flags):
                result = ("fieldinfo", name[1])
        elif target.startswith("0x") and self.val.get("rdx") == "reader" \
                and isinstance(self.val.get("rcx"), tuple) and self.val["rcx"][0] == "const" \
                and self.val["rcx"][1] in self.slots_by_number:
            # IL2CPP's virtual-invoke helper (used in Load): rcx = slot number
            self.read(self.slots_by_number[self.val["rcx"][1]])
            return
        elif target == "FieldInfo.SetValue":
            info = self.val.get("rcx")
            self.events.append(("store", ("field", info[1] if isinstance(info, tuple) else None)))
        elif target.startswith("GameModelLoader."):
            self.events.append(("call", target.split(".", 1)[1]))
        else:
            self.events.append(("call", target))
        for r in VOLATILE:
            self.val.pop(r, None)
        if result is not None:
            self.val["rax"] = result


# --- Field lists of the Set_v_<Type>_Fields routines ------------------------

# Short names for the primitive reads ("atoms") a field is made of.
ATOM = {"ReadBoolean": "bool", "ReadByte": "u8", "ReadSByte": "i8", "ReadInt16": "i16",
        "ReadUInt16": "u16", "ReadInt32": "i32", "ReadUInt32": "u32", "ReadInt64": "i64",
        "ReadUInt64": "u64", "ReadSingle": "f32", "ReadDouble": "f64", "ReadString": "str"}


def atoms_of(walk, reads):
    """Turn a run of reads into atoms. A ReadBoolean that is compared with 0
    and followed by a ReadString is the loader's nullable string,
    `br.ReadBoolean() ? null : br.ReadString()`: one atom "str?". An Int32
    used to index the object table is an object reference: atom "ref"."""
    out, i = [], 0
    while i < len(reads):
        k = reads[i]
        method = walk.reads[k]
        nxt = walk.reads[reads[i + 1]] if i + 1 < len(reads) else None
        if method == "ReadBoolean" and k in walk.cond and nxt == "ReadString":
            out.append("str?")
            i += 2
            continue
        atom = ATOM.get(method)
        if atom is None:
            raise ValueError(f"loader uses an unknown reader method {method}")
        out.append("ref" if atom == "i32" and k in walk.is_ref else atom)
        i += 1
    return out


def declared_fields(decls, short, full=None):
    """{offset: (name, type)} of a class and all its ancestors, following
    the "class X : Parent" lines of the declaration files."""
    out, seen = {}, set()
    key = decls.find(short, full)
    while key and key not in seen:
        seen.add(key)
        info = decls.parse(key)
        for off, f in info["fields"].items():
            out.setdefault(off, f)
        key = decls.find(info["parent"]) if info["parent"] else None
    return out


def analyse_set_routine(name, body, ctx, decls):
    """(parent routine or None, levels, full type name) of one
    Set_v_<Type>_Fields routine; levels = [[(field name, field type, atoms)]].

    Reads are grouped up to the next store into the object: e.g. three
    ReadSingle calls followed by a Vector3 constructor and one store are one
    field made of three atoms.

    A routine normally loops once over its objects. When a class sits under
    an abstract parent that has no routine of its own, the generator puts
    that parent's fields in an extra loop first; each loop is one "level",
    and the file holds a level's fields for every object before the next
    level starts."""
    walk = Walk(body, *ctx)
    type_name = name[len("Set_v_"):-len("_Fields")]
    # the full type name appears in the routine's cast check: typeof(A.B.TypeName)
    # (nested classes: typeof(A.B.Outer+Inner)). Types whose short name is not
    # unique are called by their full name with '_' for '.', e.g.
    # Set_v_Assets_Scripts_..._CreateEffectOnExpireModel_Fields
    def last(t):
        return re.split(r"[.+]", t)[-1]
    full = next((t for _, _, a in body for t in re.findall(r"typeof\(([\w.+]+)\)", a)
                 if last(t) == type_name or t.replace(".", "_") == type_name), None)
    short = last(full) if full else type_name
    declared = declared_fields(decls, short, full)
    by_name = {fname: ftype for fname, ftype in declared.values()}

    parent, levels, fields, pending = None, [], [], []
    for event in walk.events:
        if event[0] == "read":
            pending.append(event[1])
        elif event[0] == "call" and event[1].startswith("Set_v_") and parent is None and not levels and not fields:
            parent = event[1][len("Set_v_"):-len("_Fields")]
        elif event[0] == "store" and pending:
            kind, target = event[1]
            if kind == "offset":
                fname, ftype = declared.get(target, (f"@0x{target:X}", None))
            else:
                fname, ftype = target, by_name.get(target)
            fields.append((fname, ftype, atoms_of(walk, pending)))
            pending = []
        elif event[0] == "loop_end":
            if pending:
                raise ValueError(f"{name}: reads left over at the end of a loop - unknown pattern")
            if fields:
                levels.append(fields)
                fields = []
    if pending or fields:
        raise ValueError(f"{name}: reads outside the per-object loop - unknown pattern")
    return parent, levels, (full or type_name)


def read_pattern(name, body, ctx):
    """Atoms read by a helper routine, in order (one pass, no loops)."""
    walk = Walk(body, *ctx)
    return atoms_of(walk, list(range(len(walk.reads))))


# The generic helpers can't be told apart by their type parameter in ISIL
# (they are shared code), but their read sequence must be the one this
# decoder assumes. If a game update changes one, decoding stops here with a
# clear message instead of producing garbage.
GENERIC_HELPERS = {
    # name: (expected atoms, what it does)
    "CreateArraySet": (["i32", "i32"], "n sets; each: length -> new T[length]"),
    "CreateListSet": (["i32", "i32"], "n sets; each: capacity -> new List<T>(capacity)"),
    "CreateDictionarySet": (["i32", "i32"], "n sets; each: capacity -> new Dictionary<K,V>()"),
    "Create_Records": (["i32"], "count -> count new objects of one type"),
    "LinkArray": (["i32", "ref", "ref"], "n sets; each: array index, then one reference per slot"),
    "LinkList": (["i32", "ref", "ref"], "n sets; each: list index, then one reference per capacity"),
    "LinkDictionary": (["i32", "ref", "i32", "str", "ref"], "n sets; each: dict index, count, (key, reference)*"),
}


class LoaderProgram:
    """Everything derived from GameModelLoader's code: the section order of
    Load and the field list of every type."""

    def __init__(self, isil=None, decls=None):
        self.isil = isil if isil is not None else read_isil()
        self.decls = decls or Declarations()
        layout = loader_fields()
        by_offset, by_number = reader_slots()
        self.ctx = (layout, by_offset, by_number, layout["bind_flags"])
        base = image_base()
        self.helpers = {base + rva: name for rva, name in layout["rvas"].items()}

        # every Set_v_<Type>_Fields routine -> parent routine + its own levels
        self.types = {}
        for name, body in self.isil.items():
            if name.startswith("Set_v_") and name.endswith("_Fields"):
                parent, levels, full = analyse_set_routine(name, body, self.ctx, self.decls)
                self.types[name[6:-7]] = {"parent": parent, "levels": levels, "full_name": full,
                                          "short": re.split(r"[.+]", full)[-1]}
        self._levels = {}

        # helpers: check the generic ones, derive the element format of the typed ones
        self.typed_readers = {}
        for name, body in self.isil.items():
            if name in GENERIC_HELPERS:
                got = read_pattern(name, body, self.ctx)
                want = GENERIC_HELPERS[name][0]
                if got != want:
                    raise ValueError(f"{name} reads {got}, this decoder expects {want}: the loader changed")
            elif name.startswith("Read_"):
                atoms = read_pattern(name, body, self.ctx)
                # every typed reader is: number of sets, then per set a length
                # and that many elements; the element is the rest of the reads
                if atoms[:2] != ["i32", "i32"] or len(atoms) < 3:
                    raise ValueError(f"{name}: unexpected read pattern {atoms}")
                kind = "dict" if name.endswith("_Dictionary") else "list" if name.startswith("Read_l_") else "array"
                self.typed_readers[name] = {"kind": kind, "element": atoms[2:]}

        self.steps = self._load_steps()

    def _load_steps(self):
        """The order of sections in the file, from the Load routine:
        [("table_size",), ("CreateArraySet",), ("Read_a_Int32_Array",), ...,
         ("Create_Records",)*, ("set", Type)*, ("LinkArray",)*, ..., ("root",)]"""
        walk = Walk(self.isil["Load"], *self.ctx)
        steps, pending_reads = [], []
        for event in walk.events:
            if event[0] == "read":
                if event[2] != "ReadInt32":
                    raise ValueError(f"Load reads {event[2]} directly; expected only Int32s")
                pending_reads.append(event[1])
                continue
            if event[0] != "call":
                continue
            target = event[1]
            name = self.helpers.get(int(target, 16)) if target.startswith("0x") else target
            if not (name and (name.startswith("Set_v_") or name in GENERIC_HELPERS
                              or name in self.typed_readers)):
                continue    # runtime plumbing (metadata init, write barriers, ...)
            if not steps:  # the first Int32 is the size of the object table
                if len(pending_reads) != 1:
                    raise ValueError("Load: expected one Int32 (table size) before the first section")
                steps.append(("table_size",))
            if name.startswith("Set_v_"):
                if len(pending_reads) != 2:
                    raise ValueError(f"Load: {name} should get (start, count) from two Int32 reads")
                steps.append(("set", name[6:-7]))
            elif name in GENERIC_HELPERS or name in self.typed_readers:
                steps.append((name,))
            pending_reads = []
        if len(pending_reads) != 1:
            raise ValueError("Load: expected one final Int32 (index of the GameModel)")
        steps.append(("root",))
        return steps

    def levels(self, type_name):
        """Field lists in the order the file holds them for one Set section:
        the root ancestor's routine first (each routine calls its parent's
        before its own loops), then each loop of the routines below it."""
        if type_name not in self._levels:
            chain = []
            t = type_name
            while t:
                chain.append(t)
                t = self.types[t]["parent"]
            self._levels[type_name] = [lv for t in reversed(chain) for lv in self.types[t]["levels"]]
        return self._levels[type_name]

    def schema(self):
        """Plain-JSON summary of the derived format (written next to the data)."""
        return {
            "steps": [list(s) for s in self.steps],
            "typed_readers": self.typed_readers,
            "types": {t: {"parent": v["parent"], "full_name": v["full_name"],
                          "levels": [[[f, ft, a] for f, ft, a in lv] for lv in v["levels"]]}
                      for t, v in sorted(self.types.items())},
        }


# ===========================================================================
# 3. Replaying the format
# ===========================================================================

class Obj(dict):
    """One decoded model object: its fields as a dict, plus its type name."""
    __slots__ = ("type",)

    def __init__(self):
        super().__init__()
        self.type = None

    def __repr__(self):
        return f"<{self.type} {self.get('_name')!r}>"

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other


class Stream:
    """BinaryReader semantics over a bytes object (little endian)."""

    def __init__(self, data):
        self.data = data
        self.pos = 0

    def i32(self):
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def string(self):
        # .NET writes the byte length as a 7-bit encoded integer first
        length, shift = 0, 0
        while True:
            b = self.data[self.pos]
            self.pos += 1
            length |= (b & 0x7F) << shift
            shift += 7
            if b < 0x80:
                break
        s = self.data[self.pos:self.pos + length].decode("utf-8", errors="replace")
        self.pos += length
        return s


_UNPACK = {"bool": ("<?", 1), "u8": ("<B", 1), "i8": ("<b", 1), "i16": ("<h", 2), "u16": ("<H", 2),
           "i32": ("<i", 4), "ref": ("<i", 4), "u32": ("<I", 4), "i64": ("<q", 8), "u64": ("<Q", 8),
           "f32": ("<f", 4), "f64": ("<d", 8)}

_FLOAT_TEXT = {}


def short_float(v):
    """The shortest decimal that is the same 32-bit float as v (18.299999237
    is stored as 18.3). Floats repeat a lot, so results are cached."""
    r = _FLOAT_TEXT.get(v)
    if r is None:
        if v != v or v in (float("inf"), float("-inf")):
            return v          # NaN / infinity: nothing shorter to find
        exact = struct.pack("<f", v)
        r = next((x for x in (round(v, k) for k in range(10)) if struct.pack("<f", x) == exact), v)
        if r == int(r) and abs(r) < 2 ** 31:
            r = float(int(r))
        _FLOAT_TEXT[v] = r
    return r


def decode(data, program, trace=None):
    """Replay the loader's sections over `data`. Returns (root object, table).

    trace: optional callback(step, byte position, extra) for debugging."""
    s = Stream(data)
    table, index = [None], 1      # m[0] stays null; the constructor sets mIndex = 1
    containers = {}                # table index -> ("array"/"list", length)
    unpack = struct.unpack_from

    def atom(a):
        if a == "str?":
            flag = data[s.pos]
            s.pos += 1
            return None if flag else s.string()
        if a == "str":
            return s.string()
        fmt, size = _UNPACK[a]
        v = unpack(fmt, data, s.pos)[0]
        s.pos += size
        if a == "ref":
            return table[v]
        if a == "f32":
            return short_float(v)
        return v

    def value(atoms):
        return atom(atoms[0]) if len(atoms) == 1 else [atom(a) for a in atoms]

    for step in program.steps:
        name = step[0]
        if name == "table_size":
            table = [None] * s.i32()
        elif name in ("CreateArraySet", "CreateListSet"):
            for _ in range(s.i32()):
                n = s.i32()
                table[index] = [None] * n
                containers[index] = n
                index += 1
        elif name == "CreateDictionarySet":
            for _ in range(s.i32()):
                s.i32()                     # capacity hint only
                table[index] = {}
                index += 1
        elif name in program.typed_readers:
            reader = program.typed_readers[name]
            element = reader["element"]
            for _ in range(s.i32()):
                n = s.i32()
                if reader["kind"] == "dict":
                    table[index] = {atom(element[0]): value(element[1:]) for _ in range(n)}
                else:
                    table[index] = [value(element) for _ in range(n)]
                index += 1
        elif name == "Create_Records":
            for _ in range(s.i32()):
                table[index] = Obj()
                index += 1
        elif name == "set":
            start, count = s.i32(), s.i32()
            if trace:
                trace(step, s.pos, (start, count))
            objs = table[start:start + count]
            for o in objs:
                if not isinstance(o, Obj) or o.type is not None:
                    raise ValueError(f"{step[1]}: table slot {start}.. is not a fresh object")
                o.type = step[1]
            # one level at a time (parents first), each for all the objects
            for fields in program.levels(step[1]):
                for o in objs:
                    for fname, _, atoms in fields:
                        o[fname] = value(atoms)
        elif name in ("LinkArray", "LinkList"):
            for _ in range(s.i32()):
                target = s.i32()
                items = table[target]
                for j in range(containers[target]):
                    items[j] = table[s.i32()]
        elif name == "LinkDictionary":
            for _ in range(s.i32()):
                target = table[s.i32()]
                for _ in range(s.i32()):
                    key = s.string()
                    target[key] = table[s.i32()]
        elif name == "root":
            root = table[s.i32()]
        else:
            raise ValueError(f"no decoder for section {name}")
    # Two cheap proofs that the derived format is right: every byte is used,
    # and every object created by Create_Records was filled by some Set section.
    if s.pos != len(data):
        raise ValueError(f"decoded {s.pos} of {len(data)} bytes: the format does not match")
    unfilled = sum(1 for o in table if isinstance(o, Obj) and o.type is None)
    if unfilled:
        raise ValueError(f"{unfilled} objects were created but never filled")
    return root, table


# ===========================================================================
# 4. From model objects to the bot's tables
# ===========================================================================
#
# The decoded GameModel has, among others:
#   towers   every TowerModel: one per tower *and* upgrade combination
#            ("DartMonkey", "DartMonkey-100", ..., "DartMonkey-205"), and one
#            per hero level ("Quincy", "Quincy 2", ..., "Quincy 20")
#   upgrades every UpgradeModel (name, cost, XP cost, path, tier)
#   bloons   every BloonModel ("Red" ... "Bad", with Camo/Regrow/Fortified variants)
#   towerSet / heroSet   the shop lists, in shop order
#
# What a tower can do is read from the objects under its TowerModel:
#   AttackModel        one attack; its AttackFilterModel says whom it may target
#   ProjectileModel    what it fires; its filters say whom it may hit
#   DamageModel        damage, and immuneBloonProperties: the bloon properties
#                      (Lead, Black, White, Purple, Frozen) it can NOT damage
#   DamageModifierForTagModel   extra damage against a tag ("Moabs", "Ceramic")
#   FilterInvisible*Model       with isActive = true: camo bloons are filtered out
#   AbilityModel       an activated ability (left out of the "always on" facts)

COSMETIC = ("Sound", "Effect", "Display", "Animation", "Eject", "BuffIndicator")
CAPABILITY_FLAGS = ("Lead", "Black", "White", "Purple", "Frozen")   # BloonProperties names

# The game stores a damage type only as the set of properties it cannot
# damage. The community names for the common sets (BTD6 wiki), for reading;
# any other set is written out as "not Lead/Purple".
DAMAGE_TYPE_NAMES = {
    frozenset(): "normal", frozenset({"Lead", "Frozen"}): "sharp", frozenset({"Lead"}): "shatter",
    frozenset({"Black"}): "explosion", frozenset({"Lead", "White"}): "cold",
    frozenset({"White"}): "glacier", frozenset({"Purple"}): "energy",
}


def camel_words(name):
    """'DartMonkey' -> 'Dart Monkey', 'ObynGreenfoot' -> 'Obyn Greenfoot'."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def squash(text):
    return "".join(c for c in str(text).lower() if c.isalnum())


class ModelView:
    """Questions about the decoded model, phrased for the bot."""

    def __init__(self, root, program, names=None):
        self.root, self.program = root, program
        self.names = names or {}                           # English texts, see read_english()
        self.towers = {t["_name"]: t for t in root["towers"]}
        self.upgrades = {u["_name"]: u for u in root["upgrades"]}
        self.bloons = {b["_name"]: b for b in root["bloons"]}
        decls = program.decls
        self.tower_sets = decls.enum("TowerSet")          # 1 -> "Primary", 16 -> "Hero", ...
        self.area_types = decls.enum("AreaType")          # 1 -> "water", 2 -> "land", ...
        self.properties = decls.enum("BloonProperties")   # 1 -> "Lead", 2 -> "Black", ...
        self.flag_bit = {name: bit for bit, name in self.properties.items()}
        self._ancestors = {}
        self._flags = {}

    def display(self, game_id, section):
        """The English name the game shows for an id, from the localization
        file ("Metal Freeze" -> "Cold Snap"); a spaced-out id without it."""
        texts = self.names.get(section) or {}
        return texts.get(game_id) or self.names.get("*", {}).get(game_id) or camel_words(game_id)

    # -- types -------------------------------------------------------------
    def is_a(self, obj, base):
        """True when obj's type is `base` or derives from it (by the loader's
        routine chain, which mirrors the class hierarchy)."""
        t = obj.type
        if t not in self._ancestors:
            chain, x = set(), t
            while x:
                chain.add(self.program.types[x]["short"])
                x = self.program.types[x]["parent"]
            self._ancestors[t] = chain
        return base in self._ancestors[t]

    def walk(self, start, abilities=False, stop=None):
        """Every model object reachable from `start` (each once), skipping
        cosmetic ones and, unless asked, ability subtrees. `stop` names a
        type whose objects (other than start) are neither returned nor entered."""
        seen, stack = set(), [start]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
                continue
            if not isinstance(x, Obj) or id(x) in seen:
                continue
            seen.add(id(x))
            if x is not start and (any(c in x.type for c in COSMETIC)
                                   or (not abilities and self.is_a(x, "AbilityModel"))
                                   or (stop and self.is_a(x, stop))):
                continue
            yield x
            for key, v in x.items():
                if key != "childDependants" and isinstance(v, (Obj, list)):
                    stack.append(v)

    # -- capabilities ------------------------------------------------------
    @staticmethod
    def blocks_camo(filters):
        """An active FilterInvisible... filter removes camo bloons."""
        return any(isinstance(f, Obj) and "Invisible" in f.type and f.get("isActive") for f in filters or ())

    def projectile_filters(self, projectile):
        out = list(projectile.get("filters") or [])
        for b in projectile.get("behaviors") or []:
            if isinstance(b, Obj) and self.is_a(b, "ProjectileFilterModel"):
                out += b.get("filters") or []
        return out

    def flag_names(self, mask):
        return [name for bit, name in sorted(self.properties.items()) if bit and mask & bit]

    @staticmethod
    def hits_nothing(filters):
        """FilterAllModel filters out every bloon: a carrier projectile (a
        bomb in flight) that only does something through what it spawns."""
        return any(isinstance(f, Obj) and f.type == "FilterAllModel" for f in filters or ())

    @staticmethod
    def is_damage(o):
        """A damage source: anything with damage > 0 and the immunity mask
        (DamageModel, and damage-over-time models)."""
        return "immuneBloonProperties" in o and (o.get("damage") or 0) > 0

    def own_damage(self, projectile):
        """Damage sources a projectile carries itself (also through effects
        it puts on bloons), not counting the projectiles it spawns."""
        return [o for o in self.walk(projectile, stop="ProjectileModel") if self.is_damage(o)]

    def capabilities(self, tower):
        """What a TowerModel does without activating abilities.

        camo: some attack is allowed to target camo bloons (no active
        invisibility filter) and fires a projectile that may hit camo bloons
        and does damage - the game's "camo detection".
        hits_camo: some damaging projectile may hit camo bloons, targeted or
        not (a Spike Factory's spikes pop the camo bloons that run over them).
        decamo: something removes camo from bloons for good
        (RemoveBloonModifiersModel.cleanseCamo: Shimmer, Signal Flare, ...).
        pops: some damage that can land (not inside a projectile that hits
        nothing) lacks that immunity bit."""
        camo = False
        for attack in (o for o in self.walk(tower) if self.is_a(o, "AttackModel")):
            attack_filters = [f for o in self.walk(attack) if self.is_a(o, "AttackFilterModel")
                              for f in o.get("filters") or []]
            if self.blocks_camo(attack_filters):
                continue
            for p in (o for o in self.walk(attack) if self.is_a(o, "ProjectileModel")):
                filters = self.projectile_filters(p)
                if not self.blocks_camo(filters) and not self.hits_nothing(filters) and self.own_damage(p):
                    camo = True
                    break
            if camo:
                break
        objects = list(self.walk(tower))
        hits_camo = camo or any(
            self.is_a(p, "ProjectileModel") and not self.blocks_camo(self.projectile_filters(p))
            and not self.hits_nothing(self.projectile_filters(p)) and self.own_damage(p)
            for p in objects)
        dead = {id(d) for p in objects if self.is_a(p, "ProjectileModel")
                and self.hits_nothing(self.projectile_filters(p)) for d in self.own_damage(p)}
        damage = [o for o in objects if self.is_damage(o) and id(o) not in dead]
        masks = sorted({int(d.get("immuneBloonProperties") or 0) for d in damage})
        pops = {flag.lower(): any(not (m & self.flag_bit[flag]) for m in masks) for flag in CAPABILITY_FLAGS}
        bonus = {}
        for o in objects:
            if self.is_a(o, "DamageModifierForTagModel"):
                for tag in o.get("tags") or [o.get("tag")]:
                    if not tag:
                        continue
                    b = bonus.setdefault(tag.strip(), {"add": 0.0, "mult": 1.0})
                    b["add"] = max(b["add"], o.get("damageAddative") or 0.0)
                    b["mult"] = max(b["mult"], o.get("damageMultiplier") or 1.0)
        types = []
        for m in masks:
            # only the five bloon properties of normal play (not Glass/Immune)
            names = [n for n in self.flag_names(m) if n in CAPABILITY_FLAGS]
            types.append(DAMAGE_TYPE_NAMES.get(frozenset(names)) or "not " + "/".join(names))
        return {
            "camo": camo,
            "hits_camo": hits_camo,
            "pops": pops if damage else {k: False for k in pops},
            "damage_types": sorted(set(types)),
            "damage_bonus": {k: bonus[k] for k in sorted(bonus)},
            "decamo": any(self.is_a(o, "RemoveBloonModifiersModel") and o.get("cleanseCamo") for o in objects),
            "gives_camo": any(self.is_a(o, "VisibilitySupportModel") for o in objects),
            "gives_damage_type": any(self.is_a(o, "DamageTypeSupportModel") for o in objects),
            "abilities": [{"name": a.get("displayName"), "cooldown": a.get("cooldown")}
                          for a in self.walk(tower, abilities=True) if self.is_a(a, "AbilityModel")],
        }

    def flags(self, model):
        """flags_of(capabilities(model)), cached per model."""
        if id(model) not in self._flags:
            self._flags[id(model)] = self.flags_of(self.capabilities(model))
        return self._flags[id(model)]

    @staticmethod
    def flags_of(cap):
        """The yes/no facts of a capability dict as a short list of words."""
        words = ["camo"] if cap["camo"] else []
        words += ["hits_camo"] if cap["hits_camo"] else []
        words += [k for k, v in cap["pops"].items() if v]
        words += [w for w in ("decamo", "gives_camo", "gives_damage_type") if cap[w]]
        if any("Moab" in tag for tag in cap["damage_bonus"]):
            words.append("moab_bonus")
        return words

    # -- placement ---------------------------------------------------------
    def placement(self, tower):
        fp = tower.get("footprint")
        if isinstance(fp, Obj) and "xWidth" in fp:
            footprint = {"shape": "rectangle", "width": fp["xWidth"], "height": fp["yWidth"]}
        elif isinstance(fp, Obj) and "radius" in fp:
            footprint = {"shape": "circle", "radius": fp["radius"]}
        else:
            footprint = {"shape": "none"}
        return {
            "radius": tower["radius"],              # EntityModel.radius: what GetTowerSize uses
            "footprint": footprint,
            "placement": [self.area_types.get(a, str(a)) for a in tower.get("areaTypes") or []],
            "range": tower["range"],
            "global_range": bool(tower.get("isGlobalRange")),
        }

    # -- towers and upgrades -------------------------------------------------
    def path_models(self, base_name, path):
        """[(UpgradeModel, TowerModel after it)] for tiers 1..5 of one path,
        following the UpgradePathModel links ("DartMonkey" -> "DartMonkey-100" -> ...)."""
        out, current = [], self.towers[base_name]
        while True:
            want = list(current["tiers"])
            want[path] += 1
            step = next((u for u in current.get("upgrades") or []
                         if u["tower"] in self.towers and list(self.towers[u["tower"]]["tiers"]) == want), None)
            if step is None:
                return out
            current = self.towers[step["tower"]]
            out.append((self.upgrades[step["upgrade"]], current))


def bot_ids(names_by_id, game_ids):
    """{game id: bot id}: a game tower matches the bot entry whose display
    name squashes to the same letters ("Dart Monkey" ~ "DartMonkey"). Game
    towers the bot does not know get a snake_case id from their own name."""
    by_letters = {squash(name): key for key, name in names_by_id.items()}
    by_letters.update({squash(key): key for key in names_by_id})
    out = {}
    for gid in game_ids:
        out[gid] = by_letters.get(squash(gid)) or re.sub(r"\W+", "_", camel_words(gid)).lower()
    return out


def export_towers(view, bot_towers):
    """towers.json and upgrades.json content, keyed by the bot's tower ids."""
    towers, upgrades = {}, {}
    shop = [d for d in view.root["towerSet"] if d.get("towerId") in view.towers]
    ids = bot_ids({k: v["name"] for k, v in bot_towers.items()}, [d["towerId"] for d in shop])
    for shop_index, details in enumerate(shop):
        gid = details["towerId"]
        model = view.towers[gid]
        cap = view.capabilities(model)
        max_tiers = [details.get("pathOneMax", 0), details.get("pathTwoMax", 0), details.get("pathThreeMax", 0)]
        entry = {
            "game_id": gid,
            "name": view.display(gid, "TowerNames"),
            "category": view.tower_sets.get(model["towerSet"], str(model["towerSet"])).lower(),
            "shop_index": shop_index,
            "available": details.get("towerCount", -1) != 0 and max(max_tiers) > 0,
            "cost": model["cost"],
            **view.placement(model),
            **{k: cap[k] for k in ("camo", "hits_camo", "pops", "damage_types", "damage_bonus",
                                   "decamo", "gives_camo", "gives_damage_type", "abilities")},
            "max_tiers": max_tiers,
        }
        # every upgrade combination the game has a model for, as flag words
        crosspaths = {}
        for name, t in view.towers.items():
            if t.get("baseId") == gid and not t.get("isParagon") and name.startswith(gid + "-"):
                code = name[len(gid) + 1:]
                if code.isdigit() and len(code) == 3:
                    crosspaths[code] = view.flags(t)
        crosspaths["000"] = view.flags(model)
        entry["crosspaths"] = dict(sorted(crosspaths.items()))
        towers[ids[gid]] = entry

        paths = []
        for p in range(3):
            tiers, previous = [], set(crosspaths["000"])
            for tier, (up, after) in enumerate(view.path_models(gid, p), start=1):
                if up["path"] != p or up["tier"] != tier - 1:
                    raise ValueError(f"{gid}: upgrade {up['_name']} is path {up['path']} tier {up['tier']}, "
                                     f"expected {p} / {tier - 1}")
                c = view.capabilities(after)
                flags = ModelView.flags_of(c)
                tiers.append({
                    "tier": tier,
                    "id": up["_name"],
                    "name": view.display(up["_name"], "UpgradeNames"),
                    "cost": up["cost"],
                    "xp": up["xpCost"],
                    "model": after["_name"],
                    "range": after["range"],
                    "camo": c["camo"],
                    "hits_camo": c["hits_camo"],
                    "pops": c["pops"],
                    "damage_types": c["damage_types"],
                    "damage_bonus": c["damage_bonus"],
                    "decamo": c["decamo"],
                    "gives_camo": c["gives_camo"],
                    "gives_damage_type": c["gives_damage_type"],
                    "abilities": c["abilities"],
                    "gains": [f for f in flags if f not in previous],
                })
                previous = set(flags)
            paths.append(tiers)
        upgrades[ids[gid]] = {"game_id": gid, "paths": paths}
    return towers, upgrades


def export_heroes(view, bot_heroes):
    heroes = {}
    details = [d for d in view.root["heroSet"] if d.get("towerId") in view.towers]
    ids = bot_ids({k: v["name"] for k, v in bot_heroes.items()}, [d["towerId"] for d in details])
    for shop_index, d in enumerate(details):
        gid = d["towerId"]
        levels = sorted((t for t in view.towers.values() if t.get("baseId") == gid and view.is_a(t, "TowerModel")
                         and t.get("towerSet") == next(k for k, v in view.tower_sets.items() if v == "Hero")),
                        key=lambda t: t["tier"])
        first = levels[0]
        abilities, first_level = [], {}
        for t in levels:
            cap = view.capabilities(t)
            for a in cap["abilities"]:
                if a["name"] not in {x["name"] for x in abilities}:
                    abilities.append({"level": t["tier"], **a})
            for word in ModelView.flags_of(cap):
                first_level.setdefault(word, t["tier"])
        cap1 = view.capabilities(first)
        heroes[ids[gid]] = {
            "game_id": gid,
            "name": view.display(gid, "HeroNames"),
            "shop_index": shop_index,
            "cost": first["cost"],
            **view.placement(first),
            "monkey_money": d.get("monkeyMoneyCost"),
            "unlock_player_level": d.get("visiblePlayerLevel"),
            "max_level": d.get("upgradeMax"),
            "camo": cap1["camo"],
            "hits_camo": cap1["hits_camo"],
            "pops": cap1["pops"],
            "damage_types": cap1["damage_types"],
            "first_level_with": first_level,
            "abilities": abilities,
        }
    return heroes


def export_bloons(view):
    """bloons.json content, keyed by the game's bloon id ("CeramicRegrowCamo")."""
    def children(b):
        out = Counter()
        for x in b.get("behaviors") or []:
            if isinstance(x, Obj) and isinstance(x.get("children"), list):
                out.update(c for c in x["children"] if isinstance(c, str))
        return out

    rbe_cache = {}

    def rbe(name, stack=()):
        """Red Bloon Equivalent: its own health plus everything inside it."""
        if name in rbe_cache:
            return rbe_cache[name]
        b = view.bloons.get(name)
        if b is None or name in stack:
            return None
        total = b["maxHealth"]
        for child, n in children(b).items():
            sub = rbe(child, stack + (name,))
            if sub is None:
                return None
            total += n * sub
        rbe_cache[name] = total
        return total

    red_speed = view.bloons["Red"]["speed"] if "Red" in view.bloons else None
    out = {}
    for name, b in view.bloons.items():
        props = int(b.get("bloonProperties") or 0)
        out[name] = {
            "base": (b.get("baseId") or name).lower(),
            "speed": b["speed"],
            "speed_vs_red": round(b["speed"] / red_speed, 4) if red_speed else None,
            "health": b["maxHealth"],
            "layer": b["layerNumber"],
            "children": dict(children(b)),
            "rbe": rbe(name),
            "leak_damage": b["leakDamage"],
            "immune": [n.lower() for n in view.flag_names(props)],
            "camo": bool(b["isCamo"]),
            "regrow": bool(b["isGrow"]),
            "fortified": bool(b["isFortified"]),
            "moab_class": bool(b["isMoab"]),
            "boss": bool(b["isBoss"]),
            "radius": b["radius"],
            "tags": list(b.get("tags") or []),
        }
    return out


# --- Difficulty prices (from the game_data bundle, not sim_model) ----------
#
# Each difficulty and mode is a "Mod" asset in the game_data bundle listing
# its mutators; GlobalCostModModel(multiplier) changes prices. Its Mutate
# routine adds (multiplier - 1) x the unmodded price, so the mods of a game
# (its difficulty, then its mode) add up: Impoppable is played on Hard,
# 1 + 0.08 + 0.12 = 1.2. btd6bot/gamemodel.py has the exact rounding.

def read_difficulty_mods(game_data_bundle, monoscripts):
    """{mod name: {"cost_multipliers": [...], "start_round": n, "end_round": n}}"""
    import UnityPy  # only needed for extraction
    env = UnityPy.load(str(monoscripts), str(game_data_bundle))
    out = {}
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        mb = o.read()
        script = mb.m_Script.read() if mb.m_Script else None
        if script is None or script.m_ClassName != "Mod":
            continue
        tree = o.read_typetree()
        entry = {"cost_multipliers": []}
        for ref in (tree.get("references") or {}).get("RefIds") or []:
            cls, data = (ref.get("type") or {}).get("class"), ref.get("data") or {}
            if cls == "GlobalCostModModel":
                entry["cost_multipliers"].append(short_float(data["multiplier"]))
            elif cls == "StartingRoundModModel":
                entry["start_round"] = data.get("round")
            elif cls == "EndRoundModModel":
                entry["end_round"] = data.get("round")
        out[tree["m_Name"]] = entry
    return dict(sorted(out.items()))


# ===========================================================================
# 5. Keeping data/game_model up to date
# ===========================================================================

def read_sim_model(bundle):
    """The sim_model TextAsset's bytes from a (cached) game_model bundle."""
    import UnityPy  # only needed for extraction
    env = UnityPy.load(str(bundle))
    for o in env.objects:
        if o.type.name == "TextAsset":
            asset = o.read()
            if asset.m_Name == "sim_model":
                script = asset.m_Script
                # UnityPy hands binary TextAssets over as a str with the raw
                # bytes escaped as surrogates; this turns it back into bytes
                return script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
    raise ValueError(f"no sim_model TextAsset in {bundle.name}")


BUNDLES = {   # what we read, by file name pattern in the game's bundle folder
    "model": "game_model_assets_all_*.bundle",       # sim_model
    "data": "game_data_assets_all_*.bundle",         # difficulty and mode Mods
    "loc": "localization_assets_all_*.bundle",       # English names
    "mono": "*_monoscripts_*.bundle",                # script names for MonoBehaviours
}


def find_bundles(install=None):
    """{"model"/"data"/"loc"/"mono": cached copy or None}. Copies the game's
    current bundles into the cache when the game folder can be found (only
    when changed), else uses whatever copies the cache already has."""
    sys.path.insert(0, str(ROOT))
    try:
        from btd6bot.gamefiles import _cached, bundle_dir, find_install
    finally:
        sys.path.pop(0)
    install = install or find_install()
    found = {}
    for key, pattern in BUNDLES.items():
        src = sorted(bundle_dir(install).glob(pattern)) if install else []
        found[key] = _cached(src[0]) if src else (sorted(BUNDLE_CACHE.glob(pattern)) or [None])[-1]
    return found


def read_english(loc_bundle):
    """{section: {id: English text}} from the localization bundle's
    "English" TextAsset (XML: <TowerNames><T id="DartMonkey">Dart Monkey</T>...),
    plus "*": every id from every section."""
    import UnityPy  # only needed for extraction
    import xml.etree.ElementTree as ET
    env = UnityPy.load(str(loc_bundle))
    for o in env.objects:
        if o.type.name == "TextAsset":
            asset = o.read()
            if asset.m_Name != "English":
                continue
            text = asset.m_Script
            raw = text.encode("utf-8", "surrogateescape") if isinstance(text, str) else bytes(text)
            root = ET.fromstring(raw.lstrip(b"\xef\xbb\xbf"))     # without a byte order mark
            out, everything = {}, {}
            for section in root.iter():
                entries = {t.get("id"): (t.text or "").strip() for t in section.findall("T") if t.get("id")}
                if entries:
                    out.setdefault(section.tag, {}).update(entries)
                    for k, v in entries.items():
                        everything.setdefault(k, v)
            out["*"] = everything
            return out
    return {}


def bot_tables():
    """The bot's own tower and hero tables (for its ids and display names)."""
    sys.path.insert(0, str(ROOT))
    try:
        from btd6bot import towers as bot
    finally:
        sys.path.pop(0)
    return bot.TOWERS, bot.HEROES


def write_json(name, obj, compact=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, separators=(",", ":")) if compact else json.dumps(obj, indent=1, ensure_ascii=False)
    (OUT_DIR / name).write_text(text + "\n", encoding="utf-8")


def extract(bundles, sim_model=None):
    """Derive the format, decode, and write every JSON file. Returns a summary.

    bundles: find_bundles() result; sim_model: bytes to use instead of the
    model bundle's TextAsset. Everything is computed before anything is
    written, so a failure leaves the previous files untouched."""
    t0 = time.time()
    model_bundle, data_bundle = bundles.get("model"), bundles.get("data")
    data = sim_model if sim_model is not None else read_sim_model(model_bundle)
    program = LoaderProgram()
    root, table = decode(data, program)
    names = read_english(bundles["loc"]) if bundles.get("loc") else {}
    view = ModelView(root, program, names)
    bot_towers, bot_heroes = bot_tables()
    towers, upgrades = export_towers(view, bot_towers)
    files = {
        "towers.json": towers,
        "upgrades.json": upgrades,
        "heroes.json": export_heroes(view, bot_heroes),
        "bloons.json": export_bloons(view),
    }
    if data_bundle is not None and bundles.get("mono") is not None:
        files["difficulties.json"] = read_difficulty_mods(data_bundle, bundles["mono"])
    for name, content in files.items():
        write_json(name, content)
    write_json("loader_schema.json", program.schema(), compact=True)
    summary = {
        "bundle": model_bundle.name if model_bundle else None,
        "game_data_bundle": data_bundle.name if data_bundle else None,
        "localization_bundle": bundles["loc"].name if bundles.get("loc") else None,
        "version": EXTRACT_VERSION,
        "sim_model_sha1": hashlib.sha1(data).hexdigest(),
        "sim_model_bytes": len(data),
        "objects": sum(1 for o in table if isinstance(o, Obj)),
        "types_in_loader": len(program.types),
        "towers": len(towers), "upgrades": sum(len(p) for u in upgrades.values() for p in u["paths"]),
        "heroes": len(files["heroes.json"]), "bloons": len(files["bloons.json"]),
        "seconds": round(time.time() - t0, 1),
    }
    write_json("source.json", summary)
    log.info("game model extracted: %d towers, %d upgrades, %d heroes, %d bloons from %d objects (%.1f s)",
             summary["towers"], summary["upgrades"], summary["heroes"], summary["bloons"],
             summary["objects"], summary["seconds"])
    return summary


def refresh(install=None, force=False):
    """Re-extract when the game_model bundle changed (a game update) or this
    tool's output format did. Returns True if it extracted. Safe to call at
    every start: without the Cpp2IL output it only logs why it can't."""
    bundles = find_bundles(install)
    model_bundle = bundles["model"]
    if model_bundle is None:
        log.warning("game_model bundle not found - game model not refreshed")
        return False
    try:
        old = json.loads((OUT_DIR / "source.json").read_text(encoding="utf-8"))
        if not force and old.get("bundle") == model_bundle.name and old.get("version") == EXTRACT_VERSION:
            return False
    except (OSError, ValueError):
        pass
    if not ISIL_FILE.exists():
        log.warning("the game model changed but %s is missing: re-run Cpp2IL (docs/game_model.md)", ISIL_FILE)
        return False
    try:
        extract(bundles)
    except (ValueError, KeyError) as e:
        # most likely a game update changed the loader: keep the old data
        log.warning("could not decode the new game model (%s); keeping the previous data", e)
        return False
    return True


# ===========================================================================
# 6. Keeping data/placement.json in step
# ===========================================================================
#
# data/placement.json is hand-written (line of sight, strategy notes) but
# also repeats a few numbers the game model now gives exactly. This copies
# them over, so both files agree (tests/test_game_model_offline.py checks).

PLACEMENT_FILE = ROOT / "data" / "placement.json"
SIZE_WORDS = {1: "small", 2: "medium", 3: "large", 4: "xl"}


def placement_fields(entry):
    """The placement.json fields that mirror a towers.json / heroes.json entry."""
    sys.path.insert(0, str(ROOT))
    try:
        from btd6bot.gamemodel import size_class
    finally:
        sys.path.pop(0)
    where = [s for s in entry["placement"] if s in ("land", "water")]
    return {
        "footprint_radius": entry["radius"],
        "footprint": SIZE_WORDS[size_class(entry["radius"])],
        "placement": "land_or_water" if len(where) == 2 else (where[0] if where else "land"),
        "display_range": entry["range"],
    }


def sync_placement():
    """Rewrite the mirrored fields of data/placement.json from data/game_model.
    Returns the list of (id, field, old, new) changes."""
    with open(PLACEMENT_FILE, encoding="utf-8", newline="") as f:   # keep its line endings
        raw = f.read()
    doc = json.loads(raw)
    decoded = {**json.loads((OUT_DIR / "towers.json").read_text(encoding="utf-8")),
               **json.loads((OUT_DIR / "heroes.json").read_text(encoding="utf-8"))}
    changes = []
    for key, entry in doc.get("towers", {}).items():
        if key not in decoded:
            continue
        for field, new in placement_fields(decoded[key]).items():
            # ranges of map-wide towers stay as written (their range is not a radius)
            if field == "display_range" and entry.get("range_type") != "radius":
                continue
            if entry.get(field) != new:
                changes.append((key, field, entry.get(field), new))
                entry[field] = new
    conv = doc.setdefault("conventions", {})
    conv["footprint"] = ("the game's size class from footprint_radius (TowerModel.GetTowerSize): "
                         "small <= 6, medium 7, large 8, xl above; Ace, Heli Pilot, Banana Farm and "
                         "Rosalia have rectangular footprints (see data/game_model)")
    conv["game_model"] = ("footprint_radius, footprint, placement and the display_range of radius towers "
                          "are copied from data/game_model (the game's own model) by "
                          "`python tools/decode_sim_model.py --sync-placement`; edit them there, not here")
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    with open(PLACEMENT_FILE, "w", encoding="utf-8", newline="\r\n" if "\r\n" in raw else "\n") as f:
        f.write(text)
    return changes


def dump(type_name, object_name):
    """Print one decoded object (fields, one level deep) - for exploring."""
    data = read_sim_model(find_bundles()["model"])
    root, table = decode(data, LoaderProgram())
    for o in table:
        if isinstance(o, Obj) and o.type == type_name and object_name in (o.get("_name"), o.get("id")):
            for k, v in o.items():
                if isinstance(v, Obj):
                    v = f"<{v.type} {v.get('_name')!r}>"
                elif isinstance(v, list):
                    v = [f"<{x.type} {x.get('_name')!r}>" if isinstance(x, Obj) else x for x in v]
                print(f"{k} = {v}")
            return
    print("not found")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="extract even if the bundle did not change")
    ap.add_argument("--dump", nargs=2, metavar=("TYPE", "NAME"), help="print one decoded object")
    ap.add_argument("--sync-placement", action="store_true",
                    help="copy footprints, surfaces and ranges into data/placement.json")
    args = ap.parse_args()
    if args.dump:
        dump(*args.dump)
    elif args.sync_placement:
        for change in sync_placement():
            print("placement.json %s.%s: %r -> %r" % change)
    else:
        print("extracted" if refresh(force=args.force) else "up to date (or not possible, see log)")
