# Third-party notices

covtl-console is licensed GPL-3.0-or-later (see [LICENSE](LICENSE)).

This repository contains **only** the console application: HTML, CSS,
JavaScript, the FastAPI bridge (`server.py`) and the single-file bundler.
It does **not** redistribute any third-party code, data or binaries by
itself. All engine-side components — VocalTractLab 2.4 natives, speaker
definition files, the Wikipron pronunciation lexicons (**CC BY-SA 3.0**),
CMUdict, `vocaltractlab-cython`, and the language packs — are obtained by
installing [covtl-pipeline](https://github.com/FBerthommier/covtl-pipeline),
which manages those dependencies and carries their full notices.

The authoritative third-party notice list therefore lives in the engine:

> <https://github.com/FBerthommier/covtl-pipeline/blob/main/THIRD_PARTY_NOTICES.md>

In a local clone, the same file is `THIRD_PARTY_NOTICES.md` at the root of
the covtl-pipeline repository. If you redistribute audio, lexicon data or
speaker files produced or obtained through the engine, comply with that
document (in particular the CC BY-SA 3.0 Share-Alike terms attached to the
Wikipron-derived `xx_lexicon.tsv` files).
