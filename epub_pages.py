#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_pages.py — Les ancres de page (<a id="GBS.PA31"></a>, <a id="page-12"></a>)
marquent l'endroit où commence chaque page du livre papier. Elles servent à la
liste des pages du toc.ncx, qui permet aux liseuses d'afficher « page 31 » et
d'aller à une page précise. Quand Sigil régénère la table des matières, cette
liste disparaît et les ancres paraissent mortes.

Deux choix :
  (défaut)  rétablir la liste des pages à partir des ancres ;
  --purge   retirer les ancres de page que plus rien ne vise (le livre n'aura
            plus de numéros de page ; le texte n'est pas modifié).

Usage :
  python3 epub_pages.py livre.epub -o livre-pages.epub
  python3 epub_pages.py livre.epub -o livre-sans-ancres.epub --purge
"""

import argparse
import collections
import os
import posixpath
import re
import shutil
import sys
import tempfile
import zipfile
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epub_structure import (anchors_to_pagelist, decode_text, get_attr,  # noqa: E402
                            reorder_adjacent_anchors, resolve)

EMPTY_ANCHOR = r"""<a\s+id\s*=\s*["']({id})["']\s*(?:/>|>\s*</a>)"""


def main():
    ap = argparse.ArgumentParser(description="Liste des pages d'un EPUB : la rétablir ou purger ses ancres.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--purge", action="store_true",
                    help="retirer les ancres de page que rien ne vise, au lieu de rétablir la liste")
    opts = ap.parse_args()

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(zin.namelist())
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(zin.read(opf_path))[0]
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if get_attr(m.group(0), "href"):
                items[get_attr(m.group(0), "id")] = (resolve(opf_path, get_attr(m.group(0), "href")),
                                                     (get_attr(m.group(0), "media-type") or "").lower())
        spine = [items[i][0] for i in re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf)
                 if i in items and items[i][0] in names]
        ncx_path = next((p for p, mt in items.values() if mt == "application/x-dtbncx+xml"), None)
        texts = {p: zin.read(p).decode("utf-8", "replace") for p in spine}
        new_data = {}

        if opts.purge:
            # cibles encore visées par un lien, dans n'importe quel fichier
            refs = set()
            for n in names:
                if n.lower().endswith((".xhtml", ".html", ".htm", ".xml", ".ncx", ".opf")):
                    t = zin.read(n).decode("utf-8", "replace")
                    for m in re.finditer(r"""(?:href|src)\s*=\s*["']([^"']*#[^"']+)["']""", t):
                        path, frag = m.group(1).split("#", 1)
                        refs.add((resolve(n, path) if path else n, unquote(frag)))
            removed = collections.Counter()
            for p, t in texts.items():
                ids = re.findall(r"""\sid\s*=\s*["']((?:GBS\.|page-)[^"']+)["']""", t)
                dead = [i for i in ids if (p, i) not in refs]
                nt = t
                for i in dead:
                    # ancre vide : retirée ; id posé sur un paragraphe : seul l'attribut part
                    nt2 = re.sub(EMPTY_ANCHOR.format(id=re.escape(i)), "", nt)
                    if nt2 == nt:
                        nt2 = re.sub(r"""\s+id\s*=\s*["']%s["']""" % re.escape(i), "", nt, count=1)
                    nt = nt2
                    removed[p] += 1
                if nt != t:
                    # le texte lu ne doit pas bouger
                    strip = lambda s: re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", s))
                    if strip(nt) != strip(t):
                        sys.exit("ARRÊT : %s — le texte aurait changé ; rien n'a été écrit." % p)
                    new_data[p] = nt.encode("utf-8")
            print("Ancres de page retirées : %d (dans %d fichiers)" % (sum(removed.values()), len(removed)))
        else:
            if not ncx_path or ncx_path not in names:
                sys.exit("Pas de toc.ncx dans cet EPUB : liste des pages impossible à rétablir.")
            for p in spine:
                fixed = reorder_adjacent_anchors(texts[p])
                if fixed != texts[p]:
                    texts[p] = fixed
                    new_data[p] = fixed.encode("utf-8")
            if new_data:
                print("Ancres voisines remises dans l'ordre des pages : %d fichiers" % len(new_data))
            t, enc, bom = decode_text(zin.read(ncx_path))
            stats = collections.Counter()
            rebuilt = anchors_to_pagelist(t, ncx_path, spine, texts, stats)
            if rebuilt is None:
                sys.exit("Aucune ancre de page (GBS.…, page-…) dans le texte.")
            new_data[ncx_path] = bom + rebuilt.encode(enc)
            print("Liste des pages rétablie : %d pages" % stats["liste des pages reconstruite"])

        if not new_data:
            print("Rien à modifier.")
            return
        out = opts.output or src
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out)))
        os.close(fd)
        try:
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
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    print("EPUB écrit : %s" % out)


if __name__ == "__main__":
    main()
