#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build covtl-console-standalone.html — the whole console in ONE file.

The console is written as ES modules (no bundler, per the design brief);
this script inlines them into a single HTML file that works from file://.
Each module becomes a factory registered in a tiny module registry; the
transform is purely textual:

    import { a, b as c } from './m.js'   →  const { a, b: c } = __mods.m
    import * as R   from './m.js'        →  const R = __mods.m
    export const/function/class X ...    →  const/function/class X ...
    (the module body is wrapped and its exported names returned)
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORDER = [  # dependency order (data first, app last)
    "js/data.js", "js/demo-engine.js", "js/render.js", "js/api.js",
    "js/polar.js", "js/spectrogram.js", "js/compiler.js", "js/app.js",
]


def transform(path: Path) -> tuple[str, list[str]]:
    src = path.read_text(encoding="utf-8")
    exports: list[str] = []

    def strip_import(m: re.Match) -> str:
        clause, mod = m.group(1), m.group(2)
        name = Path(mod).name.replace(".js", "")
        clause = clause.strip()
        if clause.startswith("*"):
            alias = clause.split(" as ")[-1].strip()
            return f"const {alias} = __mods[{name!r}];"
        inner = clause.strip("{} ").strip()
        specs = []
        for part in inner.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, alias = [p.strip() for p in part.split(" as ")]
                specs.append(f"{orig}: {alias}")
            else:
                specs.append(part)
        return f"const {{ {', '.join(specs)} }} = __mods[{name!r}];"

    src = re.sub(r"import\s+(\{[^}]*\}|\*\s+as\s+\w+)\s+from\s+'([^']+)'",
                 strip_import, src)

    for kind in ("const", "let", "function", "class"):
        for name in re.findall(rf"export\s+{kind}\s+([A-Za-z_$][\w$]*)", src):
            exports.append(name)
        src = src.replace(f"export {kind} ", f"{kind} ")
    # async function exports
    for name in re.findall(r"export\s+async\s+function\s+([A-Za-z_$][\w$]*)", src):
        exports.append(name)
    src = re.sub(r"export\s+async\s+function\s+", "async function ", src)
    return src, exports


def build() -> Path:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "css" / "app.css").read_text(encoding="utf-8")

    modules = []
    for rel in ORDER:
        body, exports = transform(ROOT / rel)
        name = Path(rel).stem
        ret = ", ".join(f"{e}: {e}" for e in dict.fromkeys(exports))
        modules.append(
            f"__mods[{name!r}] = (function () {{\n{body}\n"
            f"return {{ {ret} }};\n}})();"
        )
    js = "\n".join(modules)

    html = html.replace('<link rel="stylesheet" href="css/app.css">',
                        f"<style>\n{css}\n</style>")
    html = html.replace('<script type="module" src="js/app.js"></script>',
                        "<script>window.onerror = function (m) {"
                        "document.title = 'JS ERROR: ' + m; return false; };"
                        "window.addEventListener('unhandledrejection', function (e) {"
                        "document.title = 'REJECT: ' + e.reason; });</script>\n"
                        f"<script>\nconst __mods = {{}};\n{js}\n</script>")
    out = ROOT / "covtl-console-standalone.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KiB)")
    return out


if __name__ == "__main__":
    build()
