#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble releases/COVTL-Console-Linux-x64.zip avec la porte d'hygiene B2
(C1-C4 portage Python) et actualise validation/SHA256SUMS.txt.

Chemins relatifs a la racine du bundle (le script vit dans build/) :
  - source  : <racine>/dist/linux/covtl-console        (sortie PyInstaller)
  - sortie  : <racine>/releases/COVTL-Console-Linux-x64.zip
  - sommes  : <racine>/validation/SHA256SUMS.txt
Porte C4 fail-closed : reouverture du ZIP, verification d'integrite et
recherche de residus (out/, __pycache__, *.pyc, *.log, .git*, .venv*).
"""
import hashlib
import pathlib
import sys
import zipfile

TOP = "COVTL-Console-Linux-x64"
EXCL_DIRS = {"__pycache__", "out"}
EXCL_PREF = (".git", ".venv")
EXCL_EXT = (".pyc", ".log")
ROOT = pathlib.Path(__file__).resolve().parent.parent


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(src: pathlib.Path) -> None:
    dst = ROOT / "releases" / f"{TOP}.zip"
    dst.parent.mkdir(parents=True, exist_ok=True)
    entries, skipped = [], []
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        parts = rel.parts
        if any(d in EXCL_DIRS for d in parts) \
                or any(part.startswith(EXCL_PREF) for part in parts) \
                or (p.is_file() and p.name.endswith(EXCL_EXT)):
            skipped.append(rel.as_posix())
            continue
        if p.is_file():
            entries.append(rel)

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in entries:
            z.write(src / rel, f"{TOP}/{rel.as_posix()}")

    with zipfile.ZipFile(dst) as z:
        names = z.namelist()
        residue = [n for n in names
                   if "/out/" in n or n.endswith(EXCL_EXT)
                   or "__pycache__" in n or ".git" in n or ".venv" in n]
        bad = z.testzip()
    ok = not residue and bad is None and len(entries)   # fail-closed: un zip vide = 22 octets
    h = sha256(dst)

    val = ROOT / "validation"
    val.mkdir(exist_ok=True)
    lines = [f"{h}  releases/{TOP}.zip"]
    for extra in sorted(val.iterdir()):
        if extra.name != "SHA256SUMS.txt":
            lines.append(f"{sha256(extra)}  validation/{extra.name}")
    (val / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")

    print(f"entrees: {len(names)} | exclusions: {len(skipped)} | integrite: "
          f"{'OK' if bad is None else 'CORROMPU'} | residus: {len(residue)}")
    print("PORTE B2/C4:", "CONFORME" if ok else "NON CONFORME")
    print(f"taille: {dst.stat().st_size:,} octets")
    print(f"sha256: {h}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    default_src = ROOT / "dist" / "linux" / TOP
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else default_src
    build(src)
