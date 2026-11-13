#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 COVTL packaging contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""launcher.py — point d'entrée PyInstaller de COVTL Console.

Mission §13 — cahier des charges du launcher :

  * démarre FastAPI/Uvicorn via ``covtl_console.server.main`` (même
    chemin de code que ``python -m covtl_console`` et le script pip
    ``covtl-console``) ;
  * bind 127.0.0.1 uniquement (jamais 0.0.0.0) ;
  * choisit un port disponible : 8421 par défaut, puis 8422..8440 en
    cas de collision, puis port attribué par l'OS en dernier recours ;
  * attend que le serveur soit *réellement* disponible (poll
    ``/api/health``) avant d'ouvrir le navigateur ;
  * recharge=False, un seul worker (défaut de ``server.main`` :
    ``uvicorn.run(app, ...)`` sans reload ni workers) ;
  * résout les chemins de ressources de façon gelée **et** normale —
    ``sys._MEIPASS`` n'est utilisé que si l'application est gelée,
    jamais en mode développement ;
  * journalise à la fois dans la console et dans
    ``covtl-console.log`` à côté de l'exécutable ;
  * gère proprement Ctrl+C / fermeture.

Stratégie de fermeture (mission §14 — documentée, jamais simulée) :

    Double-clic → covtl-console.exe → serveur local → navigateur

  * Fermer l'onglet ou le navigateur N'ARRÊTE PAS le serveur : la
    détection de fermeture d'onglet n'est ni fiable ni portable
    (onglets multiples, navigation privée, veille…) et n'a volontairement
    PAS été implémentée ;
  * l'utilisateur quitte l'application par Ctrl+C dans la fenêtre
    console, ou en fermant cette fenêtre (arrêt du processus hôte).
  Le launcher affiche ce rappel au démarrage.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "COVTL Console"
DEFAULT_PORT = 8421
PORT_SPAN = 20              # 8421..8440
BROWSER_TIMEOUT_S = 180.0   # warm-up G2P à froid possible (lexiques)
LOG_NAME = "covtl-console.log"


# ──────────────────────────────────────────────────────────────────────
# Résolution des chemins — gelé ET normal (jamais _MEIPASS seul)
# ──────────────────────────────────────────────────────────────────────
def resolve_paths() -> tuple[Path, Path]:
    """Retourne (base_dir, internal_dir).

    base_dir     : répertoire de l'exécutable (gelé) ou racine du
                   projet (développement) — logs, sorties ``out/`` ;
    internal_dir : ``sys._MEIPASS`` (onedir: ``_internal/``) en mode
                   gelé, sinon base_dir — ressources embarquées.
    """
    if getattr(sys, "frozen", False):          # PyInstaller
        base = Path(sys.executable).resolve().parent
        internal = Path(getattr(sys, "_MEIPASS", base))
    else:                                       # développement
        here = Path(__file__).resolve()
        base = here.parents[2]                  # racine du projet
        internal = base
    return base, internal


# ──────────────────────────────────────────────────────────────────────
# Journal console + fichier
# ──────────────────────────────────────────────────────────────────────
class Tee:
    """Écrit dans le flux d'origine ET dans le fichier de log.

    Toute méthode/attribut inconnu (``isatty``, ``fileno``,
    ``writelines``, ``encoding``…) est délégué au flux d'origine :
    uvicorn.config configure son formatter avec ``sys.stdout.isatty()``
    — un proxy partiel fait planter le démarrage (vu au build de
    validation Linux).
    """

    def __init__(self, original, log_file: Path):
        self.original = original
        self.log = log_file.open("a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        try:
            self.log.write(text)
        except OSError:
            pass                                # disque plein : console seule
        return self.original.write(text)

    def flush(self) -> None:
        self.log.flush()
        self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


def _force_utf8_streams() -> None:
    """Force UTF-8 sur stdout/stderr avant toute écriture.

    Windows : quand stdout est redirigé (pipe, fichier — cas du smoke
    test avec subprocess.PIPE), Python utilise l'encodage local
    (cp1252) au lieu de l'UTF-8 de la console. La bannière
    ``═══ COVTL Console ═══`` et les accents français ne sont alors
    plus encodables → UnicodeEncodeError au démarrage.

    ``reconfigure(encoding="utf-8", errors="replace")`` corrige le
    flux en place sans le remplacer ; ``errors="replace"`` évite
    qu'un caractère imprévu ne fasse planter le launcher à nouveau.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass                            # flux détaché ou fermé


def setup_logging(base: Path) -> None:
    _force_utf8_streams()
    log_file = base / LOG_NAME
    sys.stdout = Tee(sys.stdout, log_file)      # type: ignore[assignment]
    sys.stderr = Tee(sys.stderr, log_file)      # type: ignore[assignment]
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n═══ {APP_NAME} — session {stamp} ═══")
    print(f"journal : {log_file}")


# ──────────────────────────────────────────────────────────────────────
# Diagnostic cmudict — chargement effectif dans le bundle
# ──────────────────────────────────────────────────────────────────────
def diagnose_cmudict() -> None:
    """Vérifie que cmudict.dict est réellement chargeable au runtime.

    Symptôme visé : dans l'exe, le G2P anglais produit des séquences
    aberrantes (« thi.sisseasy fo.rus » au lieu de « Di.sizzi.zi.fO.R@s »)
    parce que cmudict n'est pas chargé. Le fichier est physiquement dans
    _internal/cmudict/data/ (collect_data_files l'a copié), mais
    cmudict utilise pkg_resources / importlib.resources pour le
    localiser — mécanisme qui échoue dans un bundle PyInstaller même
    quand le fichier est présent.

    Ce diagnostic n'interrompt pas le démarrage : il affiche le
    résultat dans la console et dans covtl-console.log, pour que la
    cause soit visible sans instrumentation supplémentaire.
    """
    print("[launcher] diagnostic cmudict :")
    try:
        import cmudict  # noqa: F401
    except Exception as exc:                    # noqa: BLE001
        print(f"[launcher]   import cmudict : ÉCHEC — {exc}")
        return

    # 1. Où cmudict croit-il que ses données se trouvent ?
    # (audit N5 : cmudict 1.1.3 n'expose pas .where() — l'attribut
    # n'existe plus ; le diagnostic affichait un « ÉCHEC » bruyant
    # alors que dict() fonctionne. Absence bénigne, pas une panne.)
    try:
        where = cmudict.where() if hasattr(cmudict, "where") else None
        if where is None:
            print("[launcher]   cmudict.where() : absente de cette "
                  "version de cmudict (bénigne — dict() fait foi)")
        else:
            print(f"[launcher]   cmudict.where() = {where}")
    except Exception as exc:                    # noqa: BLE001
        print(f"[launcher]   cmudict.where() : ÉCHEC — {exc}")
        where = None

    # 2. Le fichier existe-t-il réellement à cet endroit ?
    if where is not None:
        try:
            p = Path(where)
            if p.is_file():
                print(f"[launcher]   fichier présent : {p.stat().st_size} octets")
            else:
                print(f"[launcher]   fichier ABSENT : {p}")
        except Exception as exc:                # noqa: BLE001
            print(f"[launcher]   vérification fichier : ÉCHEC — {exc}")

    # 3. Le dictionnaire se charge-t-il réellement ?
    try:
        d = cmudict.dict()
        n = len(d)
        sample = next(iter(d.items()), None)
        print(f"[launcher]   cmudict.dict() : {n} entrées"
              + (f", exemple {sample[0]} → {sample[1]}" if sample else ""))
        if n == 0:
            print("[launcher]   ATTENTION : dictionnaire vide — G2P anglais "
                  "basculera sur un fallback dégradé")
    except Exception as exc:                    # noqa: BLE001
        print(f"[launcher]   cmudict.dict() : ÉCHEC — {exc}")
        import traceback
        traceback.print_exc()


# ──────────────────────────────────────────────────────────────────────
# Choix du port (collision → suivant ; tout busy → port OS)
# ──────────────────────────────────────────────────────────────────────
def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def choose_port(cli_port: int | None) -> int:
    if cli_port:
        return int(cli_port)
    for p in range(DEFAULT_PORT, DEFAULT_PORT + PORT_SPAN + 1):
        if port_is_free(p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])          # dernier recours : port OS


def parse_cli_port() -> int | None:
    """``--port N`` (et ``--port=N``) — sans invention d'options."""
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--port="):
            return a.split("=", 1)[1]
    return None


# ──────────────────────────────────────────────────────────────────────
# Ouverture du navigateur quand le serveur répond
# ──────────────────────────────────────────────────────────────────────
def open_browser_when_ready(url: str, ready_event: threading.Event) -> None:
    def _poll() -> None:
        deadline = time.time() + BROWSER_TIMEOUT_S
        health = f"{url}/api/health"
        while time.time() < deadline and not ready_event.is_set():
            try:
                with urllib.request.urlopen(health, timeout=3) as r:
                    if r.status == 200:
                        print(f"[launcher] serveur prêt — ouverture de {url}")
                        try:
                            webbrowser.open(url)
                        except Exception as exc:            # noqa: BLE001
                            print(f"[launcher] navigateur impossible ({exc}) "
                                  f"— ouvrez {url} manuellement")
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        if not ready_event.is_set():
            print(f"[launcher] le serveur n'est pas devenu disponible — "
                  f"ouvrez {url} manuellement si la fenêtre reste active")

    threading.Thread(target=_poll, name="browser-opener", daemon=True).start()


# ──────────────────────────────────────────────────────────────────────
# Staging ASCII (B1, cause racine amont : VocalTractLabBackend ouvre
# resources/JD3.speaker par un chemin étroit char* décodé en CP_ACP —
# voir download/Rapport_vocaltractlab_cython_chemins_non-ASCII.pdf)
# ──────────────────────────────────────────────────────────────────────
def _stage_to_ascii(base: Path) -> Path | None:
    """Chemin de l'exe non-ASCII : copie incrémentale de l'application
    vers %TEMP%\\covtl-console-ascii et retourne ce répertoire.

    La cause racine B1 est l'ouverture ANSI (CP_ACP) de
    resources/JD3.speaker par le backend C++ au moment de l'import du
    paquet natif — le seul remède côté application est que TOUTE
    l'application (exe + _internal) réside à un chemin ASCII. Copie
    incrémentale (robocopy /XO) : les lancements suivants sont
    instantanés. Retourne None si le chemin est déjà ASCII ou si le
    staging est impossible — la garde de démarrage refuse alors comme
    documenté (exit 80).
    """
    try:
        str(base).encode("ascii")
        return None                              # déjà ASCII
    except UnicodeEncodeError:
        pass
    temp = Path(os.environ.get("TEMP", r"C:\Temp"))
    try:
        str(temp).encode("ascii")
    except UnicodeEncodeError:
        return None                              # TEMP accentué : staging impossible
    dest = temp / "covtl-console-ascii"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        import subprocess as _sp
        r = _sp.run(["robocopy", str(base), str(dest),
                     "/E", "/XO", "/NFL", "/NDL", "/NJH", "/NP",
                     "/R:1", "/W:1"], capture_output=True)
        if r.returncode >= 8:
            return None
        if not (dest / "covtl-console.exe").is_file():
            return None
        return dest
    except OSError:
        return None


def main() -> int:
    base, _internal = resolve_paths()

    # B1 — staging ASCII : un chemin d'exe non-ASCII tuerait le process
    # au premier import d'extension (cause racine amont VocalTractLab).
    # On copie l'application vers un chemin ASCII et on relance l'exe
    # staging dans une nouvelle console : l'instance relancée a un
    # chemin ASCII (elle ne re-stage pas) et tourne normalement.
    staged = _stage_to_ascii(base)
    if staged is not None:
        staged_exe = staged / "covtl-console.exe"
        print(f"[launcher] chemin non-ASCII détecté ({base})")
        print(f"[launcher] l'application tourne depuis le staging ASCII : "
              f"{staged}")
        print("[launcher] relance de l'application depuis ce chemin…")
        import subprocess as _sp
        _sp.Popen([str(staged_exe), *sys.argv[1:]],
                  cwd=str(staged),
                  creationflags=_sp.CREATE_NEW_CONSOLE)
        return 0

    # Les sorties de la console atterrissent dans <exe>/out (le serveur
    # écrit dans Path.cwd()/"out") — prévisible pour un double-clic.
    try:
        os.chdir(base)
    except OSError:
        pass

    setup_logging(base)
    print(f"[launcher] répertoire de base : {base}")

    # Diagnostic cmudict AVANT l'import du serveur : si le dictionnaire
    # n'est pas chargeable, on le voit tout de suite dans les logs,
    # avant même le warm-up G2P.
    diagnose_cmudict()

    # import APRÈS la mise en place des logs : le warm-up de la console
    # (lexiques, règles G2P) journalise lui aussi.
    from covtl_console.server import main as server_main

    port = choose_port(parse_cli_port())
    url = f"http://127.0.0.1:{port}"
    stopping = threading.Event()
    open_browser_when_ready(url, stopping)

    print(f"[launcher] {APP_NAME} démarre sur {url}")
    print("[launcher] pour quitter : Ctrl+C dans cette fenêtre "
          "(fermer l'onglet du navigateur N'ARRÊTE PAS le serveur)")

    try:
        # Même chemin que le script pip / python -m covtl_console :
        # warm-up synchrone puis uvicorn (reload désactivé, 1 worker,
        # bind 127.0.0.1) — blocant jusqu'à l'arrêt.
        server_main(["--port", str(port)])
    except KeyboardInterrupt:
        print("\n[launcher] Ctrl+C reçu — arrêt du serveur…")
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"[launcher] le serveur s'est arrêté (code {exc.code})")
    except Exception as exc:                    # noqa: BLE001
        print(f"[launcher] ERREUR FATALE : {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        _pause_on_error()
        return 1
    finally:
        stopping.set()
    print("[launcher] arrêté proprement.")
    return 0


def _pause_on_error() -> None:
    """Fenêtre console ouverte par double-clic : laisse lire l'erreur."""
    if getattr(sys, "frozen", False):
        try:
            input("\nAppuyez sur Entrée pour fermer… ")
        except (EOFError, OSError):
            pass


if __name__ == "__main__":
    # [N2 gelé, constaté au rebuild-test B1/B2 du 2026-11-12] Le pool de
    # synthèse (ProcessPoolExecutor, N2) spawn ses workers en relançant
    # covtl-console.exe ; sans freeze_support(), l'enfant ré-exécute le
    # launcher complet (une SECONDE instance serveur démarre, p. ex. sur
    # 8421) et le job n'aboutit jamais. freeze_support() reconnaît
    # l'enfant (--multiprocessing-fork), exécute le worker et sort ;
    # inerte dans tout autre contexte.
    import multiprocessing

    multiprocessing.freeze_support()

    # [C2a, port Linux] Le rthook PyInstaller 6.22.3 ne détourne pas la
    # commande "-c" du SPAWN de worker (il ne couvre que resource_tracker
    # et forkserver) : si le bootloader n'a pas déjà dévié l'enfant, ce
    # dernier ré-exécute ce script et meurt sur l'argparse. La garde
    # ci-dessous détecte ce motif d'argv et exécute spawn_main. Elle est
    # AUTO-INERTE : sur Windows nominal le bootloader a déjà dévié, elle
    # est du code mort — port symétrique de la chaîne Linux
    # (packaging/linux/run_console.py).
    def _mp_spawn_worker_argv(argv):
        if "-c" not in argv:
            return None
        i = argv.index("-c")
        if len(argv) > i + 1 and argv[i + 1].startswith(
                "from multiprocessing.spawn import spawn_main"):
            return argv[i + 1]
        return None

    _cmd = _mp_spawn_worker_argv(sys.argv)
    if _cmd is not None:
        exec(_cmd)
        sys.exit(0)

    sys.exit(main())