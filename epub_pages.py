#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_pages.py — Les ancres de page (<a id="GBS.PA31"></a>, <a id="page-12"></a>)
marquent l'endroit où commence chaque page du livre papier. Elles servent à la
liste des pages du toc.ncx, qui permet aux liseuses d'afficher « page 31 » et
d'aller à une page précise. Quand Sigil régénère la table des matières, cette
liste disparaît et les ancres paraissent mortes.

Deux choix :
  (défaut)  rétablir la liste des pages à partir des ancres (elle est refaite
            entièrement : les pages dont l'ancre a disparu en sortent), retirer
            les id en double et réparer les entrées de table qui visent une
            ancre disparue ;
  --purge   retirer les ancres de page que plus rien ne vise (le livre n'aura
            plus de numéros de page ; le texte n'est pas modifié).

Usage :
  python3 epub_pages.py livre.epub -o livre-pages.epub
  python3 epub_pages.py livre.epub -o livre-sans-ancres.epub --purge
"""

import argparse
import collections
import os
import re
import shutil
import sys
import tempfile
import zipfile
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epub_structure import (anchors_to_pagelist, decode_text, dedupe_ids, fix_broken_links,  # noqa: E402
                            fix_nav_targets,
                            get_attr, renumber_play_order, reorder_adjacent_anchors, resolve)

EMPTY_ANCHOR = r"""<a\s+id\s*=\s*["']({id})["']\s*(?:/>|>\s*</a>)"""


# --------------------------------------------------------------------------
# Report des ancres de page depuis une autre version du livre
# --------------------------------------------------------------------------

PAGE_ANCHOR = re.compile(r"""\sid\s*=\s*["']((?:GBS\.(?!.*\.w\.)[^"']+)|page-\d+)["']""")
TOKEN = re.compile(r"<[^>]*>|[^<]+", re.S)


def source_stream(path):
    """Mots (squelettes) et ancres de page d'un EPUB, dans l'ordre de lecture ; numéros
    imprimés de sa page-map s'il en a une."""
    import html as _html
    from epub_reference import skel, WORD
    words, anchors, labels = [], [], {}
    with zipfile.ZipFile(path) as z:
        container = z.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(z.read(opf_path))[0]
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if get_attr(m.group(0), "href"):
                items[get_attr(m.group(0), "id")] = resolve(opf_path, get_attr(m.group(0), "href"))
        spine = [items[i] for i in re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf)
                 if i in items]
        pm = re.search(r"""page-map\s*=\s*["']([^"']+)""", opf)
        if pm and pm.group(1) in items:
            pmt = z.read(items[pm.group(1)]).decode("utf-8", "replace")
            for m in re.finditer(r"""<page\b[^>]*>""", pmt):
                name, href = get_attr(m.group(0), "name"), get_attr(m.group(0), "href") or ""
                if name and "#" in href:
                    labels.setdefault(href.split("#", 1)[1], name.strip())
        for p in spine:
            if p not in z.namelist():
                continue
            t = decode_text(z.read(p))[0]
            body = t[t.find("<body"):] if "<body" in t else t
            for tok in TOKEN.findall(body):
                if tok.startswith("<"):
                    m = PAGE_ANCHOR.search(tok)
                    if m:
                        anchors.append((len(words), m.group(1)))
                else:
                    for w in WORD.findall(_html.unescape(tok)):
                        words.append(skel(w))
    return words, anchors, labels


def report_anchors(source, zin, spine, texts, new_data, ncx_path, names):
    import xml.etree.ElementTree as ET
    from epub_longs import Doc, text_holders
    from epub_reference import skel, WORD
    src_words, src_anchors, labels = source_stream(source)
    print("Source : %d mots, %d ancres de page%s" % (len(src_words), len(src_anchors),
                                                    ", numéros imprimés de la page-map" if labels else ""))
    # texte cible : mots avec leur emplacement exact
    docs, slots = [], []
    for p in spine:
        try:
            d = Doc(p, *decode_text(zin.read(p)))
        except ET.ParseError:
            continue
        if d.body is None:
            continue
        docs.append(d)
        parents = {c: par for par in d.body.iter() for c in par}
        for holder, attr in text_holders(d.body):
            s = getattr(holder, attr) or ""
            for m in WORD.finditer(s):
                slots.append((d, holder, attr, m.start(), parents))
    tgt = []
    for d, holder, attr, start, _ in slots:
        s = getattr(holder, attr)
        tgt.append(skel(WORD.match(s, start).group(0)))
    present = {m.group(1) for t in texts.values() for m in PAGE_ANCHOR.finditer(t)}
    index = {}
    for n in (5, 4, 3):
        idx = collections.defaultdict(list)
        for i in range(len(tgt) - n + 1):
            idx[tuple(tgt[i:i + n])].append(i)
        index[n] = idx
    ratio = len(tgt) / max(1, len(src_words))
    placed, last, missed = [], 0, []
    for k, pid in src_anchors:
        if pid in present:
            continue
        expect = int(k * ratio)
        pos = None
        # contexte qui suit l'ancre, puis celui qui la précède ; en sautant au besoin un ou
        # deux mots (mot coupé en deux par le changement de page : « pre- | cautions »)
        tries = []
        for n in (5, 4, 3):
            for dd in (0, 1, 2):
                tries.append((tuple(src_words[k + dd:k + dd + n]), -dd, n))
                tries.append((tuple(src_words[max(0, k - n - dd):k - dd]), n, n))
        for key, shift, n in tries:
            if len(key) < n:
                continue
            cands = [c + shift for c in index[n].get(key, ()) if c + shift >= last]
            cands = [c for c in cands if abs(c - expect) < 4000]
            if cands:
                pos = min(cands, key=lambda c: abs(c - expect))
                break
        if pos is None or pos >= len(slots):
            missed.append(pid)
            continue
        placed.append((pos, pid))
        last = pos
    # insertion, de la fin vers le début (les emplacements précédents restent valables)
    groups = collections.OrderedDict()
    for pos, pid in placed:
        groups.setdefault(pos, []).append(pid)
    touched = set()
    for pos in sorted(groups, reverse=True):
        d, holder, attr, start, parents = slots[pos]
        s = getattr(holder, attr) or ""
        before, after = s[:start], s[start:]
        new = []
        for pid in groups[pos]:
            a = ET.Element("{http://www.w3.org/1999/xhtml}a")
            a.set("id", pid)
            new.append(a)
        new[-1].tail = after
        if attr == "text":
            holder.text = before or None
            for i, a in enumerate(new):
                holder.insert(i, a)
        else:
            holder.tail = before or None
            parent = parents[holder]
            at = list(parent).index(holder) + 1
            for i, a in enumerate(new):
                parent.insert(at + i, a)
        touched.add(d.path)
    for d in docs:
        if d.path in touched:
            raw = d.serialize()
            texts[d.path] = raw.decode(d.enc)
            new_data[d.path] = raw
    print("Ancres de page reportées : %d (déjà présentes : %d, introuvables : %d)"
          % (len(placed), len(present & {pid for _, pid in src_anchors}), len(missed)))
    if missed:
        print("   introuvables : " + ", ".join(missed[:20]) + (" …" if len(missed) > 20 else ""))
    if ncx_path and ncx_path in names:
        t, enc, bom = decode_text(zin.read(ncx_path))
        stats = collections.Counter()
        rebuilt = anchors_to_pagelist(t, ncx_path, spine, texts, stats, labels)
        if rebuilt is not None:
            rebuilt, _, _ = fix_nav_targets(rebuilt, ncx_path, texts)
            new_data[ncx_path] = bom + renumber_play_order(rebuilt, ncx_path, spine, texts).encode(enc)
            print("Liste des pages refaite : %d pages" % stats["liste des pages reconstruite"])


def main():
    ap = argparse.ArgumentParser(description="Liste des pages d'un EPUB : la rétablir ou purger ses ancres.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--from", dest="source", metavar="EPUB",
                    help="reporter les ancres de page d'une autre version du même livre (par exemple "
                         "l'EPUB de Google d'origine) : chaque ancre est replacée devant le même mot, "
                         "retrouvé malgré la modernisation ; puis la liste des pages est refaite")
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

        if opts.source:
            report_anchors(opts.source, zin, spine, texts, new_data, ncx_path, names)
        elif opts.purge:
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
            dups = links = 0
            for p in spine:
                fixed, n = dedupe_ids(reorder_adjacent_anchors(texts[p]))
                fixed, k = fix_broken_links(fixed, p, names)
                dups += n
                links += k
                if fixed != texts[p]:
                    texts[p] = fixed
                    new_data[p] = fixed.encode("utf-8")
            if dups:
                print("Id en double retirés (paragraphe coupé en deux dans Sigil) : %d" % dups)
            if links:
                print("Liens réparés (feuille de style, image déplacée ou fichier renommé) : %d" % links)
            if new_data:
                print("Fichiers retouchés (ordre des ancres, doublons) : %d" % len(new_data))
            t, enc, bom = decode_text(zin.read(ncx_path))
            stats = collections.Counter()
            if "<pageTarget" in t:
                # liste présente : on la garde (plusieurs pages blanches peuvent viser la même
                # ancre) et on n'en retire que les pages dont l'ancre a disparu
                rebuilt, dropped, repaired = fix_nav_targets(t, ncx_path, texts)
                stats["liste des pages reconstruite"] = len(re.findall(r"<pageTarget\b", rebuilt))
                if dropped:
                    print("Pages dont l'ancre a disparu, retirées de la liste : %d" % dropped)
            else:
                rebuilt = anchors_to_pagelist(t, ncx_path, spine, texts, stats)
                if rebuilt is None:
                    sys.exit("Aucune ancre de page (GBS.…, page-…) dans le texte.")
                rebuilt, _, repaired = fix_nav_targets(rebuilt, ncx_path, texts)
            if repaired:
                print("Entrées de la table dont l'ancre a disparu : %d (elles visent le début du fichier)" % repaired)
            rebuilt = renumber_play_order(rebuilt, ncx_path, spine, texts)
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
