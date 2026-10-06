#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_apparat.py — Rétablit les numéros d'appel de l'apparat de variantes que l'OCR a lus « U ».

Dans l'apparat de Kervyn de Lettenhove (« 1-2 Gens. — 3-4 Viel. — 5-6 Chose. »), les numéros
imprimés en très petits chiffres sont souvent lus « U ». Le numéro manquant se déduit de ses
voisins dans le même bloc, puisque l'apparat suit l'ordre des appels :

  « 1-2 Gens. 3-4 Viel. — U Chose. »           → « 5-6 Chose. »
  « 1-2 A quatre heures … U Dix. — 5 Se. »     → « 3-4 Dix. »
  « 3 Certainement. U La navie. 6-7 Bel et. »  → « 4-5 La navie. »

Écart d'un numéro → numéro simple ; de deux → intervalle ; sans numéro après, un intervalle
(le cas le plus courant). Le « U » est laissé et listé quand il ne suit aucun numéro sans ouvrir
le bloc, ou quand il ne s'appuie que sur un numéro deviné sans vrai numéro après. Seuls les blocs
<p class="variantes"> sont touchés.

Usage : python3 epub_apparat.py livre.epub -o livre-apparat.epub
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile

NUM = re.compile(r"(?<![\w-])(\d{1,2})(?:\s?[-_–]\s?(\d{1,2}))?(?![\w-])|(?<![\w-])U(?![\w'’-])")


def fix_block(text, report, where):
    toks = list(NUM.finditer(text))
    vals = []
    for m in toks:
        if m.group(0) == "U":
            vals.append(None)
        else:
            a = int(m.group(1))
            vals.append((a, int(m.group(2)) if m.group(2) else a))
    out, pos, guessed = [], 0, set()
    for k, m in enumerate(toks):
        if vals[k] is not None:
            continue
        pj = next((j for j in range(k - 1, -1, -1) if vals[j]), None)
        prev_end = vals[pj][1] if pj is not None else 0
        nxt = next((vals[j][0] for j in range(k + 1, len(vals)) if vals[j]), None)
        start = prev_end + 1
        # sans numéro avant, le « U » doit ouvrir le bloc ; un numéro lui-même deviné ne sert
        # d'appui que si un vrai numéro suit
        if (pj is None and re.search(r"\w", text[:m.start()])) or (pj in guessed and nxt is None):
            report.append("laissé : %s …%s…" % (where, text[max(0, m.start() - 30):m.end() + 20]))
            continue
        if nxt is None:
            new = (start, start + 1)
        elif nxt - start == 1:
            new = (start, start)
        elif nxt - start == 2:
            new = (start, start + 1)
        else:
            report.append("laissé : %s …%s…" % (where, text[max(0, m.start() - 30):m.end() + 20]))
            continue
        vals[k] = new
        guessed.add(k)
        rep = str(new[0]) if new[0] == new[1] else "%d-%d" % new
        report.append("%s « U » → « %s » …%s[%s]%s…" % (where, rep, text[max(0, m.start() - 25):m.start()],
                                                    rep, text[m.end():m.end() + 20]))
        out.append(text[pos:m.start()])
        out.append(rep)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description="Numéros d'appel lus « U » dans l'apparat de variantes.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output")
    ap.add_argument("--dry-run", action="store_true")
    opts = ap.parse_args()
    zin = zipfile.ZipFile(opts.epub)
    files = {n: zin.read(n) for n in zin.namelist()}
    report, n_changed = [], 0
    for name in [n for n in files if n.endswith((".xhtml", ".html", ".htm"))]:
        t = files[name].decode("utf-8")

        def blk(m):
            # seulement le texte hors balises du bloc
            inner = m.group(2)
            parts = re.split(r"(<[^>]+>)", inner)
            joined = "".join(p if not p.startswith("<") else "\x00" * 0 for p in parts)
            if "U" not in joined:
                return m.group(0)
            where = re.search(r'title="([^"]*)"', m.group(1))
            new_parts = []
            for p in parts:
                new_parts.append(p if p.startswith("<") else fix_block(p, report, where.group(1) if where else ""))
            return m.group(1) + "".join(new_parts) + m.group(3)
        new = re.sub(r'(<p class="variantes"[^>]*>)(.*?)(</p>)', blk, t, flags=re.S)
        if new != t:
            files[name] = new.encode("utf-8")
            n_changed += 1
    done = [r for r in report if not r.startswith("laissé")]
    print("Numéros d'appel rétablis dans l'apparat : %d" % len(done))
    for r in done[:12]:
        print("  " + r)
    left = [r for r in report if r.startswith("laissé")]
    if left:
        print("Laissés : %d" % len(left))
        for r in left[:10]:
            print("  " + r)
    if opts.dry_run:
        return
    out = opts.output or opts.epub
    fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out)))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for n, data in files.items():
            z.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, out)
    print("EPUB écrit : %s" % out)


if __name__ == "__main__":
    main()
