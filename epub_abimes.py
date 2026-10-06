#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_abimes.py — Répare les mots que l'OCR a rendus illisibles (« d~pen~sHce », « <'M7Mmi »,
« moK~; », souvent l'italique) d'après une autre numérisation de la même édition (EPUB, PDF
ou texte), par leur contexte : le mot sain qui précède et celui qui suit doivent se retrouver
côte à côte dans la référence, séparés d'un à trois mots ; ceux-ci remplacent le mot abîmé
s'ils sont eux-mêmes lisibles et si le contexte n'apparaît qu'une fois dans la référence.

  « la dépendance » ici : … — t'appar<eytaKce, d~pen~sHce.' icil al rei …
  référence (Google) :      … — Vappartenance, la dépendance: ici! al rei …
  → « l'appartenance, la dépendance: icil al rei » (les mots sains de l'EPUB restent)

Usage : python3 epub_abimes.py livre.epub reference.epub -o livre-2.epub
"""
import argparse
import collections
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epub_reference import reference_text  # noqa: E402

TOKEN = re.compile(r"\S+")
DAMAGED = re.compile(r"[~<>{}|]|[a-zà-ÿ][A-Z]+[a-zà-ÿ]|\d[a-zA-Z]{2,}|[a-zA-Z]{2,}\d")
CLEAN = re.compile(r"^[«(\[]?[A-Za-zÀ-ÿ'’-]+[.,;:!?)\]»]*$")


def core(w):
    return re.sub(r"^[«(\[]+|[.,;:!?)\]»]+$", "", w).lower().replace("’", "'")


def main():
    ap = argparse.ArgumentParser(description="Mots illisibles réparés d'après une autre numérisation.")
    ap.add_argument("epub")
    ap.add_argument("reference")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--files", default="", help="fichiers XHTML à traiter (motif), défaut : tous")
    opts = ap.parse_args()
    ref = TOKEN.findall(reference_text(opts.reference, 1, 0))
    rcore = [core(w) for w in ref]
    pos = collections.defaultdict(list)
    for i, c in enumerate(rcore):
        pos[c].append(i)
    z = zipfile.ZipFile(opts.epub)
    files = {n: z.read(n) for n in z.namelist()}
    stats = collections.Counter()
    examples = []
    for name in [n for n in files if n.endswith(".xhtml") and opts.files in n]:
        t = files[name].decode("utf-8")
        parts = re.split(r"(<[^>]+>)", t)
        for k, seg in enumerate(parts):
            if seg.startswith("<") or not DAMAGED.search(seg):
                continue
            toks = list(TOKEN.finditer(seg))
            out, last, j = [], 0, 0
            while j < len(toks):
                if not DAMAGED.search(toks[j].group(0)):
                    j += 1
                    continue
                # suite de mots abîmés [j, e) entre deux mots sains
                e = j
                while e < len(toks) and (DAMAGED.search(toks[e].group(0)) or not CLEAN.match(toks[e].group(0))):
                    e += 1
                run = e - j
                stats["abîmés"] += sum(1 for q in range(j, e) if DAMAGED.search(toks[q].group(0)))
                if j == 0 or e >= len(toks) or run > 4:
                    j = e
                    continue
                prev, nxt = toks[j - 1].group(0), toks[e].group(0)
                hits = []
                for i in pos.get(core(prev), []):
                    for gap in range(1, run + 3):
                        if i + gap + 1 < len(ref) and rcore[i + gap + 1] == core(nxt):
                            hits.append(ref[i + 1:i + gap + 1])
                            break
                orig = " ".join(toks[q].group(0) for q in range(j, e))
                if len(hits) == 1 and all(CLEAN.match(x) or re.fullmatch(r"[\d,.;:]+", x) for x in hits[0]) \
                        and (re.search(r"\d", orig) or not re.search(r"\d", " ".join(hits[0]))) \
                        and len(hits[0]) <= run + 1:
                    new = " ".join(hits[0]).replace("’", "'")
                    out.append(seg[last:toks[j].start()] + new)
                    last = toks[e - 1].end()
                    stats["réparés"] += run
                    if len(examples) < 25:
                        examples.append("%s → %s" % (" ".join(toks[q].group(0) for q in range(j, e)), new))
                j = e
            if out:
                parts[k] = "".join(out) + seg[last:]
        files[name] = "".join(parts).encode("utf-8")
    with zipfile.ZipFile(opts.output, "w") as zo:
        zo.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for n, data in files.items():
            zo.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
    print("Mots abîmés : %d — réparés : %d" % (stats["abîmés"], stats["réparés"]))
    for e in examples:
        print("  " + e)
    print("EPUB écrit : %s" % opts.output)


if __name__ == "__main__":
    main()
