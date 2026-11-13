# SPDX-FileCopyrightText: 2026 COVTL packaging contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- mode: python ; coding: utf-8 -*-
"""covtl-console.spec — build PyInstaller **onedir** de COVTL Console.

Mission §12/§15/§16/§17 — règles appliquées :

  * onedir (jamais onefile) → ``dist/covtl-console/{covtl-console.exe,
    _internal/}`` ;
  * les hiddenimports sont MINIMAUX et justifiés : seul ``sandhi`` est
    listé (import paresseux derrière try/except dans
    ``vtl_synth/core/pipeline.py`` et ``covtl_console/server.py``) ;
    uvicorn/pydantic/imageio-ffmpeg/numpy/scipy/matplotlib/PIL sont
    couverts par les hooks officiels (pyinstaller-hooks-contrib) —
    aucun ajout arbitraire ;
  * les DONNÉES sont collectées explicitement (§16) : vtl_synth
    (speakers + registry + *_constants.py + lexiques + JD3), sandhi
    (listes), cmudict (dictionnaire + métadonnées .dist-info),
    imageio-ffmpeg (binaire ffmpeg), covtl_console/ui (frontend),
    vocaltractlab_cython (resources/JD3) ;
  * les BIBLIOTHÈQUES NATIVES (§17) : libVocalTractLabApi (VTL 2.4)
    embarquée explicitement via collect_dynamic_libs — le binding
    Cython de vocaltractlab-cython est collecté automatiquement
    (module d'extension importé) ;
  * AUCUNE exclusion : numpy, scipy, matplotlib (rendu polaire des
    modes vidéo), Pillow, ffmpeg sont nécessaires aux fonctionnalités
    de la console ;
  * ``vtl_synth`` en mode de collection ``py`` : ses sources restent
    des fichiers réels dans ``_internal/vtl_synth/`` car le moteur
    LIT ET ÉCRIT des fichiers .py à l'exécution (constants.py du
    speaker actif via speaker_registry, marqueur ACTIVE_SPEAKER,
    *_constants.py du registre) — dans une archive PYZ ces lectures
    échoueraient.

Construction (Windows x64, voir scripts/build-windows.ps1) :

    pip install covtl-console matplotlib pyinstaller
    pyinstaller packaging/pyinstaller/covtl-console.spec \
        --distpath dist/windows --workpath build/pyinstaller

Le même spec fonctionne sous Linux pour la validation (le binaire
libVocalTractLab est alors la variante .so du wheel manylinux).
"""

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

# ── 1. Données (§16) — explicites, une intention par entrée ──────────
datas = []

# vtl_synth : lexiques Wikipron (*.tsv + notices README_*), speaker de
# référence JD3, registre speakers (registry.json + *.speaker)…
datas += collect_data_files("vtl_synth")

# …et les *_constants.py du registre, fichiers .py de DONNÉES que
# collect_data_files filtre par défaut mais que speaker_registry lit
# sur disque (hash de cohérence, install_speaker) — ajout explicite.
import importlib.util as _ilu
_spec = _ilu.find_spec("vtl_synth")
if _spec is None or _spec.origin is None:
    raise SystemExit("vtl_synth n'est pas installé — "
                     "pip install covtl-console d'abord")
_vtl_dir = Path(_spec.origin).resolve().parent
_speakers = _vtl_dir / "data" / "speakers"
for _c in sorted(_speakers.glob("*_constants.py")):
    datas.append((str(_c), "vtl_synth/data/speakers"))

# covtl_console : le frontend (index.html, css/, js/) servi par
# StaticFiles — DOIT être sur disque dans _internal/covtl_console/ui.
datas += collect_data_files("covtl_console")

# sandhi (module d'import réel de covtl-sandhi) : listes d'exceptions.
datas += collect_data_files("sandhi")

# cmudict : la base du dictionnaire ARPAbet (data/cmudict.dict…).
datas += collect_data_files("cmudict")

# cmudict utilise importlib.metadata / pkg_resources pour localiser ses
# données. Sans le .dist-info dans le bundle, cmudict.dict() échoue
# avec « No package metadata was found for cmudict » — même quand
# data/cmudict.dict est physiquement présent. copy_metadata embarque le
# dossier cmudict-*.dist-info/, indispensable à la résolution.
datas += copy_metadata("cmudict")

# [N5/B1 round 2026-11-12] Sans dist-info dans le gelé, le serveur ne
# peut pas résoudre les versions par importlib.metadata ; le fallback
# amont (vtl_synth.__version__) couvre déjà engine_version, mais ces
# dist-info rendent la version exacte dans tous les cas (UI : « engine
# v1.1.0 », bridge = version du paquet).
datas += copy_metadata("vtl-synth")
datas += copy_metadata("covtl-console")

# imageio-ffmpeg : le binaire ffmpeg embarqué par le wheel
# (binaries/ffmpeg-*-x86_64*), résolu par get_ffmpeg_exe().
datas += collect_data_files("imageio_ffmpeg")

# vocaltractlab_cython : uniquement resources/ (JD3.speaker chargé par
# la DLL à l'initialisation) — les .c/.pyx/.h de build ne servent à rien.
_vtlc = _ilu.find_spec("vocaltractlab_cython")
if _vtlc is None or _vtlc.origin is None:
    raise SystemExit("vocaltractlab_cython n'est pas installé")
_vtlc_dir = Path(_vtlc.origin).resolve().parent
_res = _vtlc_dir / "resources"
if not _res.is_dir():
    raise SystemExit(f"resources/ absent de vocaltractlab_cython : {_vtlc_dir}")
datas.append((str(_res), "vocaltractlab_cython/resources"))

# ── 1bis. Licences et notices des distributions embarquées (§17) ────
# PyInstaller ne collecte pas les dist-info : sans ce bloc, le
# standalone n'embarquerait NI la licence GPL des trois paquets COVTL,
# NI la GPLv3 du paquet cmudict (distincte de la licence BSD des
# données CMUdict, déjà présente via cmudict/data/LICENSE), NI les
# notices corrigées. Tout est copié dans _internal/licenses/<dist>/.
import importlib.metadata as _imd


def _dist_info_dir(dist):
    for _f in dist.files or []:
        if ".dist-info/" in str(_f):
            _p = Path(str(_f.locate()))
            for _q in [_p, *_p.parents]:
                if _q.name.endswith(".dist-info"):
                    return _q
    return None


for _name in ("vtl-synth", "covtl-console", "covtl-sandhi", "cmudict",
              "imageio-ffmpeg", "vocaltractlab-cython"):
    try:
        _dist = _imd.distribution(_name)
    except _imd.PackageNotFoundError:
        raise SystemExit(f"{_name} n'est pas installé — "
                         f"pip install covtl-console d'abord")
    _di = _dist_info_dir(_dist)
    if _di is None:
        raise SystemExit(f"dist-info introuvable pour {_name}")
    _licdir = _di / "licenses"
    if _licdir.is_dir():
        for _lf in sorted(_licdir.iterdir()):
            if _lf.is_file():
                datas.append((str(_lf), f"licenses/{_name}"))
    else:  # distribution plus ancienne sans répertoire licenses/
        for _lf in (_di / "LICENSE", _di / "LICENSE.txt"):
            if _lf.is_file():
                datas.append((str(_lf), f"licenses/{_name}"))

# ── 2. Bibliothèques natives (§17) ────────────────────────────────────
# libVocalTractLabApi.{so,dll} — le cœur natif VocalTractLab 2.4,
# chargé par le module d'extension VocalTractLabApi du wheel (RPATH).
# Collecte explicite : PyInstaller ne suit pas toujours les liens
# RPATH intra-package.
binaries = collect_dynamic_libs("vocaltractlab_cython")

# ── 3. Hiddenimports (§15) — minimaux et justifiés ───────────────────
hiddenimports = [
    # import paresseux try/except (pipeline.py, server.py).
    # collect_submodules : sandhi charge dynamiquement ses sous-modules
    # de langue (sandhi.fr, sandhi.en, …) via importlib.import_module()
    # — invisible à l'analyse statique, d'où le ModuleNotFoundError
    # observé au smoke test. On collecte tout le package.
]
hiddenimports += collect_submodules("sandhi")
# vocaltractlab_cython : le module d'extension Cython importe ses
# sous-modules (utils, exceptions) EN RUNTIME via l'API C Python —
# invisible à l'analyse statique (constaté au build de validation :
# « No module named 'vocaltractlab_cython.utils' »). Collecte
# systématique du package entier (§17).
hiddenimports += collect_submodules("vocaltractlab_cython")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # AUCUNE exclusion de module utile. Tkinter et tests ne sont
        # pas importés par le graphe ; on ne touche à rien d'autre.
    ],
    noarchive=False,
    # vtl_synth en fichiers .py réels : lecture/écriture runtime de
    # constants.py / ACTIVE_SPEAKER / registre (voir docstring).
    module_collection_mode={
        "vtl_synth": "py",
    },
)
pyz = PYZ(a.pure)

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
    console=True,               # fenêtre console = logs visibles (§13)
    disable_windowed_traceback=False,
    # PyInstaller 6.x ignore les variables d'environnement PYTHON*
    # (PYTHONUTF8, PYTHONIOENCODING). Sans cette option, sys.stdout
    # utilise cp1252 quand il est redirigé (pipe du smoke test,
    # fichier) — la bannière « ═══ » plante alors avec
    # UnicodeEncodeError. 'X utf8' force le mode UTF-8 (PEP 540) dans
    # le bootloader, quel que soit l'environnement d'exécution.
    options=[('X utf8', None, 'OPTION')],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="covtl-console",       # → dist/<name>/covtl-console(.exe) + _internal/
    mode="onedir",
)