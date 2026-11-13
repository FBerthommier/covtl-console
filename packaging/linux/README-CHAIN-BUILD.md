# COVTL-Rebuild-Linux-x64 — bundle de reconstruction

Bundle autonome et réutilisable : **le binaire Linux livré ET tout ce qu'il
faut pour le vérifier et le reconstruire à l'identique** (Python 3.12,
Linux x86-64).

## Contenu

```
COVTL-Rebuild-Linux-x64/
├── rebuild.sh                          ← une commande pour tout reconstruire
├── README-CHAIN-BUILD.md               ← ce document
├── releases/
│   └── COVTL-Console-Linux-x64.zip     ← le binaire livré (onedir PyInstaller,
│                                          267 entrées, porte d'hygiène B2 CONFORME)
├── build/                              ← chaîne de build reproductible
│   ├── covtl-console-linux.spec          (correctif n°2 : imports cachés + données)
│   ├── run_console.py                    (correctif n°1 : détournement du spawn)
│   ├── patch-fix3-brokenprocesspool.py   (correctif n°3 : import manquant, idempotent)
│   ├── zip-release-b2.py                 (emballage + porte d'hygiène B2/C4)
│   ├── smoke.sh                          (smoke de validation)
│   ├── requirements-build.txt            (phase 1, PyPI, versions plancher)
│   └── requirements-freeze.txt           (environnement exact de la build livrée)
└── validation/                         ← preuves de la build livrée
    ├── SHA256SUMS.txt                    (empreinte du ZIP binaire + fichiers ici)
    ├── pyinstaller-linux.log             (journal de référence du build)
    └── preuve-synthese.wav               (sortie réelle du smoke : 44 100 Hz mono)
```

## Utilisation

```bash
# Exécuter simplement l'application :
unzip releases/COVTL-Console-Linux-x64.zip
./COVTL-Console-Linux-x64/covtl-console          # http://127.0.0.1:8421

# Vérifier l'intégrité :
cd validation && sha256sum -c SHA256SUMS.txt

# Reconstruire à l'identique (~3-4 min, Python 3.12 requis) :
bash rebuild.sh
# avec validation fonctionnelle complète (démarrage + synthèse réelle) :
RUN_SMOKE=1 bash rebuild.sh
```

`rebuild.sh` enchaîne : venv neuf → phase 1 (dépendances réelles depuis PyPI)
→ phase 2 (chaîne covtl depuis TestPyPI, versions épinglées) → `pip check` →
correctif n°3 → build PyInstaller → (smoke optionnel) → emballage avec porte
d'hygiène B2. La release régénérée écrase `releases/COVTL-Console-Linux-x64.zip`
et `validation/SHA256SUMS.txt` est actualisé. Le freeze réel de chaque
reconstruction est conservé dans `build/requirements-freeze-run.txt` pour
comparaison avec `requirements-freeze.txt`.

## Les trois correctifs embarqués dans la chaîne

1. **`run_console.py` — détournement du spawn du worker** (`_mp_spawn_worker_argv`).
   Le rthook PyInstaller 6.22.3 ne détournait pas la commande `-c` du spawn
   multiprocessing : le process worker ré-exécutait le script entier et
   mourrait sur l'argparse du serveur → `BrokenProcessPool` immédiat sur
   toute synthèse. Le worker exécute désormais `spawn_main` et sort.
2. **`covtl-console-linux.spec` — imports cachés et données**.
   `collect_submodules("vtl_synth"/"sandhi")`, sous-modules de
   `vocaltractlab_cython`, `collect_data_files` pour l'UI, les lexiques
   TSV 5 langues, les 5 speakers, les règles sandhi, le dictionnaire CMU,
   et `copy_metadata("cmudict")` (sinon `metadata.version()` échoue en gelé).
3. **`patch-fix3-brokenprocesspool.py` — import manquant dans `server.py`**
   (paquet installé, appliqué après `pip install`, avant le build).
   `server.py` référençait `BrokenProcessPool` dans son gestionnaire de job
   sans l'importer : le fallback N2 levait `NameError` à la première erreur
   enfant. Une ligne : `from concurrent.futures.process import
   BrokenProcessPool`.

## Procédure manuelle (équivalente à rebuild.sh)

```bash
python3 -m venv .venv-build && .venv-build/bin/pip install --upgrade pip
# Phase 1 — PyPI (TestPyPI héberge un parasite FASTAPI-1.0 qui casse la
# résolution directe de covtl-console) :
.venv-build/bin/pip install -r build/requirements-build.txt
# Phase 2 — chaîne covtl depuis TestPyPI :
.venv-build/bin/pip install --index-url https://test.pypi.org/simple/ "covtl-console==3.1.4"
.venv-build/bin/pip check

python3 build/patch-fix3-brokenprocesspool.py .venv-build
.venv-build/bin/pyinstaller build/covtl-console-linux.spec --noconfirm \
    --distpath dist/linux --workpath build/pyinstaller

bash build/smoke.sh dist/linux/covtl-console/covtl-console  # si souhaité
python3 build/zip-release-b2.py
```

## Notes

- Le ZIP binaire ne contient aucune source ni script : code compilé (PYZ),
  libs natives (`libVocalTractLabApi.so`, extension cp312 de
  `vocaltractlab_cython`, ffmpeg), données (lexiques, speakers, CMU, sandhi)
  et UI (9 fichiers texte, SVG inline — aucune image bitmap).
- Validation de la build livrée : install deux phases, `pip check` propre,
  smoke sur binaire gelé (`/api/status` HTTP 200, backend live, 5 speakers,
  synthèse `proof` → job `done`, WAV 44 100 Hz mono), 267 entrées,
  0 résidu, intégrité ZIP OK.
- Les durées de synthèse dépendent de la machine (le test lent de la suite
  pytest dépasse son propre timeout de 900 s sur un environnement à 2 cœurs
  partagés — ce n'est pas une régression fonctionnelle).
