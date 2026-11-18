# covtl — the COVTL articulatory speech synthesis suite

[![PyPI version](https://img.shields.io/pypi/v/covtl.svg)](https://pypi.org/project/covtl/)

`pip install covtl` installs the whole COVTL suite in one command:

| package | role |
|---|---|
| [`covtl-synth`](https://pypi.org/project/covtl-synth/) | the articulatory synthesis **engine** from text (Berthommier COVTL model + VocalTractLab): 5 speakers, 6 languages, expressive prosody, phonation modes (breathy / creaky / whisper), cross-word sandhi, polar video |
| [`covtl-console`](https://pypi.org/project/covtl-console/) | the local **web console** (FastAPI bridge + UI): `covtl-console` starts on http://127.0.0.1:8421 |
| [`covtl-sandhi`](https://pypi.org/project/covtl-sandhi/) | the **cross-word sandhi** rule package (Branch B) |

This distribution is a **meta-package**: it carries no code of its own,
only the coherent pin set of the three releases. Install the packages
individually if you only need one part (e.g. `pip install covtl-synth`
for the Python API alone).

## Quick start

```bash
pip install covtl
vtl-synth run "this is easy for us" -o ./out     # engine CLI
covtl-console                                     # web console (port 8421)
```

```python
from vtl_synth import Pipeline
result = Pipeline(tag_overrides={'*': {'voicing': 'breathy'}}).run(
    "this is easy for us", output_dir="./out")
```

The Python module is `vtl_synth`; the engine CLI is `vtl-synth`.

## License

GPL-3.0-or-later. See each package for its third-party notices
(VocalTractLab GPLv3, DVTD speakers CC0, cmudict BSD data / GPLv3 code).
