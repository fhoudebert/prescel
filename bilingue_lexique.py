#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bilingue_lexique.py — Tire d'une édition bilingue (texte ancien en regard d'une traduction en français
moderne) de quoi enrichir et contrôler la modernisation de Prescel (epub_modernise.py).

Le texte ancien passe par la chaîne de modernisation de l'époque choisie, puis la traduction en regard
sert de juge :
  1. résidus : formes restées anciennes (absentes de la liste de mots française), par fréquence ;
  2. candidats : pour chaque résidu, les formes modernes que donnent les règles de graphie
     (dictionnaires/graphie_*.py), retenues seulement si la traduction de la même double page les
     emploie (« validé ») ; et les mots de la traduction les plus liés au résidu (association sur les
     doubles pages × ressemblance des graphies), à examiner : utile pour les mots pleins (« eve » → eau,
     « chief » → tête), sans valeur pour les mots-outils ;
  3. recoupement : chaque remplacement que fait déjà la chaîne (« pucele » → pucelle) est cherché dans la
     traduction en regard ; un taux très bas signale un faux ami probable, avec le mot que le
     traducteur emploie le plus souvent à la place.

Aucun passage n'est écrit : les sorties ne contiennent que des mots isolés et des nombres (une
traduction moderne est une œuvre protégée ; elle sert ici de témoin, pas de source à reproduire).

Entrée : un PDF à couche texte où le texte ancien et sa traduction sont sur deux pages qui se suivent
(édition « bilingue » : GF-Flammarion, Lettres gothiques, Champion Classiques…).

Usage :
  python3 bilingue_lexique.py lancelot.pdf --pages 54-439 --ancien pair --epoque ancien -o lancelot
  # → lancelot-residus.tsv, lancelot-candidats.tsv, lancelot-recoupement.tsv et un bilan
  python3 bilingue_lexique.py livre.pdf --pages 20-301 --ancien impair --epoque moyen -o livre --min 3
"""

import argparse
import collections
import difflib
import html
import json
import math
import os
import re
import runpy
import subprocess
import sys
import tempfile
import unicodedata
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORD = re.compile(r"[^\W\d_]+", re.U)


# --------------------------------------------------------------------------
# Lecture du PDF
# --------------------------------------------------------------------------

def clean_ancien(text):
    """Vers du texte ancien : sans numéros de vers ni de folio, sans titre courant."""
    out = []
    for line in text.split("\n"):
        line = re.sub(r"[\[{(]\s*\d+\s*[a-zA-Z]?\s*[\]})]", "", line)        # folio [27a], {27t]
        line = re.sub(r"^\s*\d+[a-z]?\s+", "", line)                         # numéro de vers en tête
        line = re.sub(r"\s+\d+\s*$", "", line).strip()                       # numéro de vers en fin
        if not line or re.fullmatch(r"[\d\s.]+", line):
            continue
        if re.fullmatch(r"[A-ZÀÂÉÈÊËÎÏÔÛÙÇŒ ,.'’!…-]{5,}", line):           # titre courant, intertitre
            continue
        out.append(line)
    return out


def clean_moderne(text):
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    lines = [l.strip() for l in text.split("\n")]
    lines = [l for l in lines if l and not re.fullmatch(r"[\d\s.]+", l)
             and not re.fullmatch(r"[A-ZÀÂÉÈÊËÎÏÔÛÙÇŒ ,.'’!…-]{5,}", l)]
    return " ".join(lines)


def read_spreads(pdf, first, last, ancien):
    try:
        import pymupdf
    except ImportError:
        sys.exit("PyMuPDF manque : pip install pymupdf")
    doc = pymupdf.open(pdf)
    parity = 0 if ancien == "pair" else 1
    spreads = []
    for p in range(first, last + 1):
        if p % 2 != parity or p >= doc.page_count:
            continue
        old = clean_ancien(doc[p - 1].get_text())
        new = clean_moderne(doc[p].get_text())
        if old and new:
            spreads.append({"page": p, "ancien": old, "moderne": new})
    return spreads


# --------------------------------------------------------------------------
# Chaîne de modernisation de Prescel
# --------------------------------------------------------------------------

CHAINES = {
    "ancien": [["--mode", "cas"], ["--mode", "vocab"], ["--mode", "graphie"]],
    "moyen": [["--mode", "vocab"], ["--mode", "vocab", "--dict", os.path.join(HERE, "dictionnaires", "noms_froissart.py")],
              ["--mode", "oi"], ["--mode", "graphie"], ["--mode", "erent"], ["--mode", "ants"], ["--mode", "vocab"]],
}


def write_epub(path, spreads):
    body = "".join('<p id="s%d">%s</p>\n' % (i, "<br/>".join(html.escape(l) for l in s["ancien"]))
                   for i, s in enumerate(spreads))
    xhtml = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
             'lang="fr" xml:lang="fr"><head><title>texte</title></head><body>\n%s</body></html>' % body)
    opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
           'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>texte</dc:title>'
           '<dc:language>fr</dc:language><dc:identifier id="id">bilingue</dc:identifier></metadata><manifest>'
           '<item id="t" href="t.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="t"/>'
           '</spine></package>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:'
                   'tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/c.opf" media-type='
                   '"application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/c.opf", opf)
        z.writestr("OEBPS/t.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)


def read_epub_spreads(path, n):
    t = zipfile.ZipFile(path).read("OEBPS/t.xhtml").decode("utf-8")
    out = [""] * n
    for m in re.finditer(r'<(?:\w+:)?p\b[^>]*\bid="s(\d+)"[^>]*>(.*?)</(?:\w+:)?p>', t, re.S):
        out[int(m.group(1))] = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
    return out


def moderniser(spreads, epoque, wordlist, workdir):
    src = os.path.join(workdir, "0.epub")
    write_epub(src, spreads)
    for k, args in enumerate(CHAINES[epoque], 1):
        dst = os.path.join(workdir, "%d.epub" % k)
        cmd = [sys.executable, os.path.join(HERE, "epub_modernise.py"), src, "-o", dst, "--epoque", epoque,
               "--tsv", os.path.join(workdir, "%d.tsv" % k), "--wordlist", wordlist] + args
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit("Échec de %s :\n%s" % (" ".join(args), r.stderr[-2000:]))
        src = dst
    return read_epub_spreads(src, len(spreads))


# --------------------------------------------------------------------------
# Mesures
# --------------------------------------------------------------------------

def load_words(wordlist):
    if wordlist == "auto":
        sys.path.insert(0, HERE)
        from epub_longs import load_wordlist          # télécharge et met en cache la liste
        return {w.lower() for w in load_wordlist("auto")}
    return {w.lower() for w in open(wordlist, encoding="utf-8").read().split()}


def tokens(text):
    return [w for w in WORD.findall(text)]


def lower_common(toks):
    """Mots en minuscules, sans les noms propres (majuscule hors début de vers : approximation)."""
    return [w.lower() for w in toks if not w[:1].isupper()]


def skel(w):
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return w.replace("an", "en").replace("z", "s").replace("y", "i")


def llr(a, b, c, d):
    def h(*k):
        t = sum(k)
        return sum(x * math.log(x / t) for x in k if x)
    return 2 * (h(a, b, c, d) - h(a + b, c + d) - h(a + c, b + d))


def associations(w, sw, mods, df, words, n, top=3):
    """Mots de la traduction liés à w (présents dans au moins la moitié des doubles pages de w)."""
    cand = collections.Counter(m for i in sw for m in mods[i] if m in words)
    out = []
    for m, a in cand.items():
        if a / len(sw) < 0.5 or df[m] > 0.8 * n:
            continue
        b, c = len(sw) - a, df[m] - a
        d = n - len(sw) - c
        assoc = llr(a, b, c, d) if a * n > len(sw) * df[m] else 0
        sim = difflib.SequenceMatcher(None, skel(w), skel(m)).ratio()
        out.append((assoc * (0.3 + sim), m))
    out.sort(reverse=True)
    return [m for _, m in out[:top]]


def plain(w):
    w = unicodedata.normalize("NFD", w.lower())
    return "".join(c for c in w if unicodedata.category(c) != "Mn")


def same_stem_used(y, sw, mods, seuil=0.25):
    """Le traducteur emploie-t-il un mot de même radical (« venait » / venir, venu ; « fût » / fut) ?
    Alors l'écart tient au temps ou à la tournure, pas au sens : ce n'est pas un faux ami."""
    k = 3 if len(y) < 5 else 4
    stem = plain(y)[:k]
    if not sw:
        return False
    hits = sum(any(plain(m).startswith(stem) for m in mods[i]) for i in sw)
    return hits / len(sw) >= seuil


def write_tsv(path, header, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Édition bilingue → résidus, candidats et contrôle de la modernisation.")
    ap.add_argument("pdf")
    ap.add_argument("--pages", required=True, help="pages du PDF (numérotation du fichier) : 54-439")
    ap.add_argument("--ancien", choices=["pair", "impair"], required=True,
                    help="pages du PDF qui portent le texte ancien (la traduction est sur la suivante)")
    ap.add_argument("--epoque", choices=["ancien", "moyen"], default="ancien")
    ap.add_argument("-o", "--output", required=True, help="préfixe des fichiers produits")
    ap.add_argument("--min", type=int, default=5, help="fréquence minimale d'un résidu examiné (défaut 5)")
    ap.add_argument("--wordlist", default="auto")
    ap.add_argument("--seuil", type=float, default=0.3,
                    help="part des doubles pages du résidu où la traduction doit employer le candidat (défaut 0,3)")
    opts = ap.parse_args()
    a, b = (int(x) for x in opts.pages.split("-"))

    spreads = read_spreads(opts.pdf, a, b, opts.ancien)
    if not spreads:
        sys.exit("Aucune double page lue : vérifier --pages et --ancien")
    words = load_words(opts.wordlist)
    with tempfile.TemporaryDirectory() as tmp:
        modern = moderniser(spreads, opts.epoque, opts.wordlist, tmp)

    olds = [" ".join(s["ancien"]) for s in spreads]
    mods = [set(w.lower() for w in tokens(s["moderne"])) for s in spreads]
    n = len(spreads)
    df = collections.Counter(w for m in mods for w in m)

    before = [w for t in olds for w in lower_common(tokens(t))]
    after = [w for t in modern for w in lower_common(tokens(t))]
    share = lambda ts: sum(w in words for w in ts) / max(1, len(ts))

    # 1. résidus
    residus = collections.Counter(w for w in after if w not in words)
    present = [set(w.lower() for w in tokens(t)) for t in modern]

    # 2. candidats
    g = runpy.run_path(os.path.join(HERE, "dictionnaires", "graphie_%s.py" % opts.epoque))
    sys.path.insert(0, HERE)
    import epub_modernise as em
    cand_rows, valid_occ = [], 0
    for w, cnt in residus.most_common():
        if cnt < opts.min or len(w) < 3:
            continue
        sw = [i for i in range(n) if w in present[i]]
        if not sw:
            continue
        variants = sorted({x for x in em.graphie_variants(w, g["RULES"]) if x in words and x != w})
        best, rate = "", 0.0
        for x in variants:
            if df[x] > 0.4 * n:                       # mot présent presque partout : ne prouve rien
                continue
            r = sum(x in mods[i] for i in sw) / len(sw)
            if r >= opts.seuil and r > rate:
                best, rate = x, r
        if best:
            valid_occ += cnt
        assoc = associations(w, sw, mods, df, words, n)
        cand_rows.append((w, cnt, len(sw), best, "%.2f" % rate if best else "",
                          ", ".join(x for x in variants if x != best), ", ".join(assoc)))

    # 3. recoupement des remplacements déjà faits
    ok, tot = collections.Counter(), collections.Counter()
    for old, new, mod in zip(olds, modern, mods):
        to, tn = tokens(old), tokens(new)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, to, tn, autojunk=False).get_opcodes():
            if tag != "replace" or i2 - i1 != j2 - j1:
                continue
            for x, y in zip(to[i1:i2], tn[j1:j2]):
                if x[:1].isupper():
                    continue
                k = (x.lower(), y.lower())
                tot[k] += 1
                ok[k] += y.lower() in mod
    rec_rows = []
    for (x, y), t in tot.most_common():
        rate = ok[(x, y)] / t
        sw = [i for i in range(n) if x in set(w.lower() for w in tokens(olds[i]))]
        flag, alt = "", ""
        if t >= 10 and rate < 0.25 and not same_stem_used(y, sw, mods):
            flag = "faux ami probable"
            alt = ", ".join(associations(x, sw, mods, df, words, n)) if sw else ""
        rec_rows.append((x, y, t, ok[(x, y)], "%.2f" % rate, flag, alt))

    write_tsv(opts.output + "-residus.tsv", ["forme", "occurrences"], residus.most_common())
    write_tsv(opts.output + "-candidats.tsv",
              ["forme", "occurrences", "doubles_pages", "validé_par_la_traduction", "taux",
               "autres_formes_des_règles", "mots_liés_dans_la_traduction"], cand_rows)
    write_tsv(opts.output + "-recoupement.tsv",
              ["ancien", "moderne", "remplacements", "retrouvés", "taux", "signal", "mots_du_traducteur"], rec_rows)

    t_ok, t_all = sum(ok.values()), sum(tot.values())
    print("Doubles pages lues : %d (%d vers ou lignes)" % (n, sum(len(s["ancien"]) for s in spreads)))
    print("Mots à forme moderne : %.1f %% → %.1f %% après la chaîne « %s »" % (100 * share(before), 100 * share(after), opts.epoque))
    print("Résidus : %d occurrences, %d formes ; examinés (≥ %d) : %d ; candidats validés par la traduction : %d formes, %d occurrences"
          % (sum(residus.values()), len(residus), opts.min, len(cand_rows), sum(1 for r in cand_rows if r[3]), valid_occ))
    print("Remplacements de la chaîne retrouvés dans la traduction : %d / %d (%.0f %%) ; faux amis probables : %d"
          % (t_ok, t_all, 100 * t_ok / max(1, t_all), sum(1 for r in rec_rows if r[5])))
    for r in [r for r in rec_rows if r[5]][:15]:
        print("  %-12s → %-12s %3s/%-4s  le traducteur : %s" % (r[0], r[1], r[3], r[2], r[6]))
    print("Fichiers : %s-residus.tsv, %s-candidats.tsv, %s-recoupement.tsv" % ((opts.output,) * 3))


if __name__ == "__main__":
    main()
