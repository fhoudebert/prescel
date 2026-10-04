#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_guillemets.py — Rétablit les guillemets que l'OCR a lus comme des lettres isolées.

Dans les éditions du XIXe siècle (Kervyn de Lettenhove…), l'OCR de Gallica lit souvent
« comme « u » et » comme « n ». Ces lettres isolées ne sont presque jamais des mots :

  « présent le roy de France? n Il respondi »   → « … France ? » Il respondi »
  « que nous le tendrons en prison … belle. n »  → « … belle. » »
  « et nous adont voulen-|u tiers entendrons »  → « voulentiers entendrons »
                                                   (guillemet répété en début de ligne)

Chaque « u » ou « n » isolé (variantes comprises ; ni « n. s. », ni lettre collée à un
signe) est décidé d'après la lettre et l'équilibre des guillemets du paragraphe :
  - suivi d'un « : c'est le fermant de la réplique précédente → « » » ;
  - « n » : fermant → « » », sauf au milieu d'une phrase citée (minuscules de part et d'autre),
    où c'est le guillemet répété en tête de ligne → supprimé ;
  - « u » dans une citation ouverte : suivi d'une minuscule, guillemet répété → supprimé ;
    sinon fermant → « » » ;
  - « u » hors citation, suivi d'un mot : ouvrant → « « ».
Le reste (« u » hors citation, rien après) est laissé tel quel et listé.

Seuls les guillemets changent ; tout est listé. La typographie (espaces insécables) est
ensuite l'affaire d'epub_typo.py.

Usage : python3 epub_guillemets.py livre.epub -o livre-guillemets.epub
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
from epub_longs import (Doc, EPUB2, decode_text, fix_doctype, get_attr, resolve,  # noqa: E402
                        text_holders)

LETTER = re.compile(r"(?<![\w'’-])([un])(?![\w'’-])")


def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def main():
    ap = argparse.ArgumentParser(description="Guillemets lus « u » / « n » par l'OCR.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--dry-run", action="store_true", help="ne rien écrire, seulement la liste")
    opts = ap.parse_args()

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos, names = zin.infolist(), zin.namelist()
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(zin.read(opf_path))[0]
        ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf)
        EPUB2[0] = not (ver and ver.group(1).startswith("3"))
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if get_attr(m.group(0), "href"):
                items[get_attr(m.group(0), "id")] = resolve(opf_path, get_attr(m.group(0), "href"))
        spine = [items[i] for i in re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf)
                 if i in items and items[i] in names]
        docs = []
        for p in spine:
            try:
                d = Doc(p, *decode_text(zin.read(p)))
            except ET.ParseError:
                continue
            if d.body is not None:
                docs.append(d)

        stats, examples, kept, changed = collections.Counter(), collections.defaultdict(list), [], set()
        for d in docs:
            for p in d.body.iter():
                if lname(p) not in ("p", "li", "blockquote"):
                    continue
                if any(lname(c) in ("p", "li") for c in p):
                    continue
                holders = [(h, a) for h, a in text_holders(p)
                           if not (a == "text" and lname(h) == "sup")]   # appels de variante / de note
                depth = 0
                for h, a in holders:
                    s = getattr(h, a) or ""
                    out, pos = [], 0
                    for m in re.finditer(r"[«»]|(?<![\w'’-])[un](?![\w'’-])", s):
                        tok = m.group(0)
                        if tok == "«":
                            depth += 1
                            continue
                        if tok == "»":
                            depth = max(0, depth - 1)
                            continue
                        before, after = s[:m.start()], s[m.end():]
                        prev_word = re.search(r"([^\s«»]+)\s*$", before)
                        next_word = re.search(r"^\s*([^\s]+)", after)
                        pw = prev_word.group(1) if prev_word else ""
                        nw = next_word.group(1) if next_word else ""
                        if after.startswith(".") or (before and not re.search(r"[\s«».,;:!?]$", before)):
                            continue                     # « (n. s.) », « Bi°n » : pas un guillemet
                        lower_next = bool(re.match(r"[a-zà-ÿ]", nw))
                        mid = bool(pw and lower_next and re.search(r"[a-zà-ÿ]$", pw))
                        if nw.startswith("«"):
                            new, why = "»", "guillemet fermant"      # « … Lancastre. u « Je vous »
                            depth = max(0, depth - 1)
                        elif tok == "n":
                            # « n » est presque toujours un fermant ; au milieu d'une phrase citée,
                            # c'est le guillemet répété en tête de ligne
                            if depth > 0 and mid:
                                new, why = "", "guillemet répété en tête de ligne"
                            else:
                                new, why = "»", "guillemet fermant"
                                depth = max(0, depth - 1)
                        elif depth > 0 and lower_next:
                            new, why = "", "guillemet répété en tête de ligne"
                        elif depth > 0:
                            new, why = "»", "guillemet fermant"
                            depth -= 1
                        elif nw and not re.match(r"[«».,;:!?)]", nw):
                            new, why = "«", "guillemet ouvrant"
                            depth += 1
                        else:
                            kept.append("%s : …%s[%s]%s…" % (d.path.split("/")[-1], before[-40:], tok, after[:30]))
                            continue
                        stats[why] += 1
                        if len(examples[why]) < 6:
                            examples[why].append("…%s[%s→%s]%s…" % (before[-35:], tok, new or "∅", after[:25]))
                        out.append(s[pos:m.start()])
                        if new == "":
                            # pas de double espace là où le guillemet disparaît
                            out[-1] = out[-1].rstrip(" ") + (" " if not after.startswith(" ") else "")
                            pos = m.end() + (1 if after.startswith(" ") and out[-1].endswith(" ") else 0)
                        else:
                            out.append(new)
                            pos = m.end()
                    if out:
                        out.append(s[pos:])
                        new_s = "".join(out)
                        if new_s != s:
                            setattr(h, a, new_s)
                            changed.add(d.path)

        print("Guillemets rétablis : %d" % sum(stats.values()))
        for why, n in stats.most_common():
            print("  %-36s %4d" % (why, n))
            for e in examples[why][:4]:
                print("      " + e.replace("\n", " "))
        if kept:
            print("Laissés tels quels (aucune citation ouverte, rien après) : %d" % len(kept))
            for k in kept[:10]:
                print("  " + k.replace("\n", " "))
        if opts.dry_run:
            return

        out_path = opts.output or src
        new_data = {d.path: d.serialize() for d in docs if d.path in changed or fix_doctype(d.prefix) != d.prefix}
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
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
            os.replace(tmp, out_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    print("EPUB écrit : %s" % out_path)


if __name__ == "__main__":
    main()
