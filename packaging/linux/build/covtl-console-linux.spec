# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller Linux (onedir) — equivalent de la chaine Windows
# (build-windows.ps1). Disposition auditee en B2 :
#   dist/linux/covtl-console/covtl-console          (executable ELF)
#   dist/linux/covtl-console/_internal/...           (arbre onedir 6.x)
# Donnees embarquees :
#   - covtl_console/ui/**        (l'interface servie par le pont)
#   - vtl_synth/data/**          (lexiques TSV 5 langues + speaker files)
#   - sandhi/data/**             (regles de liaison covtl-sandhi)
#   - cmudict                    (dictionnaire CMU, import dynamique)
#   - vocaltractlab_cython       (extension native manylinux, .so + resources)
import sys
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

hidden = [
    "covtl_console",
    "covtl_console.server",
    "covtl_console._synthproc",
    "covtl_console._launchguard",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "vtl_synth",
    "cmudict",
    "vocaltractlab_cython",
    "vocaltractlab_cython.utils",
    "vocaltractlab_cython.exceptions",
    "vocaltractlab_cython.resources",
]
hidden += collect_submodules("vtl_synth")
hidden += collect_submodules("sandhi")

datas = []
datas += collect_data_files("covtl_console")           # ui/index.html, css, js
datas += collect_data_files("vtl_synth")               # lexiques + speakers
datas += collect_data_files("sandhi")                  # regles de liaison
datas += collect_data_files("cmudict")                 # cmudict.dict
datas += copy_metadata("cmudict")                      # dist-info (metadata.version)
datas += collect_data_files("vocaltractlab_cython")    # resources/JD3.speaker etc.
datas += collect_data_files("matplotlib")              # polices / styles pour les modes video

a = Analysis(
    ["run_console.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "setuptools", "pip"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="covtl-console",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="covtl-console",
)
