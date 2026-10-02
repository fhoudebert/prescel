#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_typo.py — Applique la typographie française (typo_fr.py) au texte d'un EPUB :
espace insécable avant ; : ! ? » et après «, aucune espace avant . , … ) ] ni après ( [,
une espace après la ponctuation quand un mot suit, « ... » → « … », tiret de dialogue.
Les règles passent par-dessus les balises d'italique ; seules les espaces, « ... » et le
tiret changent : le texte est vérifié lettre à lettre avant l'écriture.

Usage :
  python3 epub_typo.py livre.epub -o livre-typo.epub
"""

import argparse
import collections
import os
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epub_longs import Doc, EPUB2, decode_text, fix_doctype, get_attr, resolve  # noqa: E402
from typo_fr import typo_pieces, letters_only  # noqa: E402

BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "dt", "dd"}


def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def slots(block):
    """Nœuds de texte d'un bloc, dans l'ordre (sans descendre dans un bloc imbriqué)."""
    out = [(block, "text")]

    def walk(el):
        for ch in el:
            if lname(ch) in BLOCKS:
                continue
            out.append((ch, "text"))
            walk(ch)
            out.append((ch, "tail"))
    walk(block)
    return out


def main():
    ap = argparse.ArgumentParser(description="Typographie française d'un EPUB.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    opts = ap.parse_args()
    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(zin.namelist())
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(zin.read(opf_path))[0]
        ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf)
        EPUB2[0] = not (ver and ver.group(1).startswith("3"))
        new_data, changed = {}, collections.Counter()
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if (get_attr(m.group(0), "media-type") or "") != "application/xhtml+xml":
                continue
            p = resolve(opf_path, get_attr(m.group(0), "href") or "")
            if p not in names:
                continue
            try:
                d = Doc(p, *decode_text(zin.read(p)))
            except ET.ParseError:
                continue
            if d.body is None:
                continue
            before = letters_only("".join(d.body.itertext()))
            n = 0
            for block in [e for e in d.body.iter() if lname(e) in BLOCKS]:
                sl = slots(block)
                texts = [getattr(h, a) or "" for h, a in sl]
                new = typo_pieces(texts)
                for (h, a), old, nw in zip(sl, texts, new):
                    if nw != old:
                        setattr(h, a, nw or None)
                        n += 1
            if letters_only("".join(d.body.itertext())) != before:
                sys.exit("ARRÊT : le texte de %s aurait changé ; rien n'a été écrit." % p)
            if n or fix_doctype(d.prefix) != d.prefix:
                new_data[p] = d.serialize()
                changed[p] = n
        out = opts.output or src
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out)))
        os.close(fd)
        with zipfile.ZipFile(tmp, "w") as zout:
            for info in sorted(infos, key=lambda i: i.filename != "mimetype"):
                data = new_data.get(info.filename)
                if data is None:
                    data = zin.read(info)
                if info.filename == "mimetype":
                    info.compress_type = zipfile.ZIP_STORED
                zout.writestr(info, data, compress_type=info.compress_type)
        shutil.copymode(src, tmp)
        os.replace(tmp, out)
    print("Nœuds de texte retouchés : %d (dans %d fichiers)" % (sum(changed.values()), len(changed)))
    print("EPUB écrit : %s" % out)


if __name__ == "__main__":
    main()
