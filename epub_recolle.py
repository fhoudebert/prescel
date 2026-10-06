#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_recolle.py — Recolle les mots que l'OCR a coupés d'une espace (« mar eschal »,
« con nestable », « Fran çois », « cheval lier »), et sépare les mots que l'OCR a collés
(« chambredu », « royaumedeFrance »).

Le livre lui-même sert de dictionnaire : deux morceaux séparés par une espace sont recollés
quand le mot entier se trouve ailleurs dans le livre (au moins deux fois, et pas moins souvent
que la suite des deux morceaux) et qu'un des morceaux n'apparaît jamais seul dans le livre
(« ment », « nestable », « çois »). Deux vrais mots côte à côte ne sont jamais recollés : « je
n'en vis », « de rue en rue », « de mander », « si tost », « pour tant » restent tels quels.
Sans le mot dans le livre, la liste de mots français sert de repli quand aucun des deux
morceaux n'est un mot. Seule une espace disparaît : les lettres ne changent pas.

Mots collés : un mot qui n'apparaît qu'une fois et n'est pas un mot de la langue est séparé
quand une seule découpe donne des mots courants du livre (au moins 5 fois chacun) dont la suite,
séparée, se trouve au moins deux fois ailleurs. Seule une espace s'ajoute.

La liste de ce qui est recollé (et de ce qui ne l'est pas, faute de certitude) est écrite
en TSV : une ligne « non » dans la colonne « recoller » empêche ce recollage à la relance,
une ligne « oui » l'impose.

Usage :
  python3 epub_recolle.py livre.epub -o livre-recolle.epub --tsv livre-recolle.tsv
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
from epub_longs import (Doc, EPUB2, decode_text, fix_doctype, get_attr, load_wordlist,  # noqa: E402
                        resolve, text_holders)

WORD = re.compile(r"[^\W\d_]+")
# terminaisons qu'une espace sépare souvent de leur mot (« autre ment », « parle ment ») et qui
# ne sont presque jamais des mots à elles seules dans ces textes
OPENERS = {"si", "et", "au", "aux", "en", "le", "la", "les", "de", "du", "des", "que", "quant", "or",
           "puis", "ce", "il", "ils", "on", "car", "mais", "à", "a", "ne", "se", "sur", "par", "pour"}
SUFFIXES = {"ment", "mens", "ments", "ent", "ient", "oient", "rent", "oit", "tion", "tions",
            "ance", "ances", "ité", "eur", "eurs", "ture", "tures"}
# deux morceaux séparés par une seule espace, sans apostrophe ni trait d'union autour
PAIR = re.compile(r"(?<![\w-])([^\W\d_]+)[ \u00a0](?=([^\W\d_]+)(?![\w'’-]))")


def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def read_tsv(path):
    forced = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or line.startswith("recoller\t") or not line.strip():
                    continue
                c = line.rstrip("\n").split("\t")
                if len(c) >= 3:
                    v = c[0].strip().lower()
                    if v in ("oui", "non"):          # « auto-oui » / « auto-non » : décision du script
                        forced[(c[1], c[2])] = v == "oui"
    return forced


def main():
    ap = argparse.ArgumentParser(description="Recoller les mots coupés par une espace.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--tsv", help="liste des recollages (écrite ; vos « oui »/« non » sont repris)")
    ap.add_argument("--wordlist", default="auto",
                    help="liste de mots (fichier, ou « auto » : liste française libre) ; « » pour s'en passer")
    ap.add_argument("--sans-decollage", action="store_true",
                    help="ne pas séparer les mots collés (« chambredu » → « chambre du »)")
    ap.add_argument("--dry-run", action="store_true", help="ne rien écrire, seulement la liste")
    opts = ap.parse_args()

    src = opts.epub
    forced = read_tsv(opts.tsv)
    wordlist = load_wordlist(opts.wordlist) if opts.wordlist else None
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

        holders = [(d, h, a) for d in docs for h, a in text_holders(d.body)]
        words, pairs = collections.Counter(), collections.Counter()
        lower_first = collections.Counter()      # mots écrits au moins une fois sans majuscule
        triples = collections.Counter()
        for d, h, a in holders:
            s = getattr(h, a) or ""
            ws = WORD.findall(s)
            words.update(w.lower() for w in ws)
            lower_first.update(w.lower() for w in ws if w[:1].islower())
            pairs.update((m.group(1).lower(), m.group(2).lower()) for m in PAIR.finditer(s))
            lw = [w.lower() for w in ws]
            triples.update(zip(lw, lw[1:], lw[2:]))
        if wordlist is not None:
            wordlist = {w.lower() for w in wordlist}

        decided = {}

        # occurrences « libres » de chaque morceau : hors des suites qui forment un mot du livre
        free = collections.Counter(words)
        for (x, y), n in pairs.items():
            if words[x + y] >= 2:
                free[x] -= n
                free[y] -= n

        def decide(a, b):
            key = (a.lower(), b.lower())
            if key in decided:
                return decided[key]
            whole = (a + b).lower()
            n_whole, n_pair = words[whole], pairs[key]
            unknown = lambda w: free[w] < 2          # jamais seul ailleurs dans le livre
            why = ""
            if (a, b) in forced or key in forced:
                ok, why = forced.get((a, b), forced.get(key)), "imposé par la liste"
            elif b[:1].isupper() and not a.isupper():
                ok, why = False, "second morceau en majuscule"
            elif a[:1].islower() and n_whole and not lower_first[whole]:
                ok, why = False, "le mot entier est un nom propre (« %s »)" % whole.capitalize()
            elif key[1] in SUFFIXES and key[0] not in SUFFIXES and n_whole >= 5 and n_whole >= 5 * n_pair:
                ok, why = True, "terminaison détachée, « %s » ailleurs dans le livre (%d fois)" % (whole, n_whole)
            elif not (unknown(key[0]) or unknown(key[1])):
                ok, why = False, "deux mots du livre (« %s » %d fois, « %s » %d fois)" % (
                    key[0], free[key[0]], key[1], free[key[1]])
            elif n_whole >= 2 and n_pair <= n_whole:
                ok, why = True, "« %s » ailleurs dans le livre (%d fois)" % (whole, n_whole)
            elif wordlist and whole in wordlist and unknown(key[0]) and unknown(key[1]):
                ok, why = True, "mot de la langue, aucun morceau n'est un mot"
            elif n_whole < 2:
                ok, why = False, "mot entier trop rare (%d)" % n_whole
            else:
                ok, why = False, "suite des deux morceaux plus fréquente (%d contre %d)" % (n_pair, n_whole)
            decided[key] = (ok, n_whole, n_pair, why)
            return decided[key]

        joined, refused, changed = collections.Counter(), collections.Counter(), set()
        for d, h, a in holders:
            s = getattr(h, a) or ""
            if not s.strip():
                continue

            def rep(m):
                x, y = m.group(1), m.group(2)
                if words[(x + y).lower()] == 0 and not (wordlist and (x + y).lower() in wordlist):
                    return m.group(0)
                ok, *_ = decide(x, y)
                if ok:
                    joined[(x, y)] += 1
                    return x                     # l'espace disparaît ; y suit déjà
                refused[(x, y)] += 1
                return m.group(0)
            # les paires se recouvrent (« chevaucha tant pas ») : le second mot n'est pas consommé
            new = PAIR.sub(rep, s)
            if new != s:
                setattr(h, a, new)
                changed.add(d.path)

        # mots collés : « chambredu » → « chambre du », « royaumedeFrance » → « royaume de France ».
        # Le mot collé n'apparaît qu'une fois et n'est pas un mot de la langue ; chaque morceau est
        # un mot courant du livre et la suite séparée se trouve au moins deux fois ailleurs ; une
        # seule découpe possible.
        split_done = collections.Counter()

        def splits(w):
            lw, out = w.lower(), []
            n = len(w)
            for i in range(2, n - 1):
                a_, b_ = lw[:i], lw[i:]
                if words[a_] >= 5 and words[b_] >= 5 and pairs[(a_, b_)] >= 2:
                    out.append((w[:i], w[i:]))
            if not out:
                for i in range(2, n - 3):
                    for j in range(i + 2, n - 1):
                        a_, b_, c_ = lw[:i], lw[i:j], lw[j:]
                        if words[a_] >= 5 and words[b_] >= 5 and words[c_] >= 5 and triples[(a_, b_, c_)] >= 2:
                            out.append((w[:i], w[i:j], w[j:]))
            return out

        def unglue(m):
            w = m.group(0)
            lw = w.lower()
            if len(w) < 5 or w.isupper() or words[lw] > 1 or (wordlist and lw in wordlist):
                return w
            key = ("|", lw)
            if key in forced and not forced[key]:
                return w
            cand = splits(w)
            if len(cand) != 1:
                return w
            parts = cand[0]
            # mot à majuscule : nom propre (« Pasque ») sauf s'il commence par un petit mot de
            # début de phrase (« Siprindrent », « Auroi », « Etsi »)
            if w[:1].isupper() and parts[0].lower() not in OPENERS:
                return w
            # forme ancienne d'un mot de la langue : « passans » (passants), « faisans »
            if wordlist and re.search(r"[ae]ns$", lw) and (lw[:-1] + "ts") in wordlist:
                return w
            if any(p_[:1].isupper() for p_ in parts[1:]) and not all(
                    p_[:1].isupper() or p_.islower() for p_ in parts):
                return w
            split_done[(w, " ".join(parts))] += 1
            return " ".join(parts)

        if not opts.sans_decollage:
            for d, h, a in holders:
                s_ = getattr(h, a) or ""
                new = WORD.sub(unglue, s_)
                if new != s_:
                    setattr(h, a, new)
                    changed.add(d.path)

        total = sum(joined.values())
        print("Mots recollés : %d (%d formes)" % (total, len(joined)))
        for (x, y), n in joined.most_common(40):
            print("  %-28s → %s%s" % ("%s %s" % (x, y), x + y, "  ×%d" % n if n > 1 else ""))
        if len(joined) > 40:
            print("  … (liste complète dans le TSV)")
        if not opts.sans_decollage:
            print("Mots collés séparés : %d (%d formes)" % (sum(split_done.values()), len(split_done)))
            for (w, sp), n in split_done.most_common(40):
                print("  %-28s → %s" % (w, sp))
        if opts.tsv:
            with open(opts.tsv, "w", encoding="utf-8") as f:
                f.write("# Recollages proposés (auto-oui) ou écartés (auto-non). Remplacez par « oui » ou « non »\n"
                        "# pour imposer votre choix à la relance.\n")
                f.write("recoller\tmorceau 1\tmorceau 2\tmot entier\tfois\tmot entier ailleurs\tsuite ailleurs\tmotif\n")
                for (x, y), n in sorted(joined.items(), key=lambda kv: (-kv[1], kv[0])):
                    ok, nw, np_, why = decide(x, y)
                    f.write("%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s\n" % ("oui" if why == "imposé par la liste" else "auto-oui", x, y, x + y, n, nw, np_, why))
                for (w, sp), n in sorted(split_done.items()):
                    f.write("auto-oui\t|\t%s\t%s\t%d\t\t\tmot collé séparé (« non » pour le garder collé)\n"
                            % (w.lower(), sp, n))
                for (x, y), n in sorted(refused.items(), key=lambda kv: (-kv[1], kv[0])):
                    ok, nw, np_, why = decide(x, y)
                    if nw >= 2:                   # seuls les cas où le mot entier existe vraiment
                        f.write("%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s\n" % ("non" if why == "imposé par la liste" else "auto-non", x, y, x + y, n, nw, np_, why))
            print("Liste : %s" % opts.tsv)
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
