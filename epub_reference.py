#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_reference.py — Compare un EPUB issu d'OCR à une autre édition du même texte
(PDF ou texte brut) et corrige l'EPUB d'après elle, catégorie par catégorie.

Alignement : chaque paragraphe de l'EPUB est retrouvé dans la référence grâce à
des suites de quatre mots ramenés à un « squelette » insensible aux graphies
(accents, s long lu f, y/i, oi/ai, consonnes doubles, -ez/-es), puis comparé mot
à mot. Les notes et appels de note de la référence (police plus petite) et ses
repères de pagination « [I, 111] » sont écartés.

Catégories d'écarts (seules celles demandées par --apply sont appliquées) :
  ocr          lettre(s) mal lue(s) : « vlande » → « viande », « II » → « Il »,
               « Roy al » → « royal », et le s long ambigu « font » → « sont » ;
  esperluette  « & » → « et » ;
  apostrophes  « qu'il » → « qu’il » ;
  casse        « Roi » → « roi » ;
  graphie      accents et graphies modernisés (« par tout » → « partout ») : choix
               de l'éditeur de la référence ;
  variante     autre mot correct (« leurs » / « leur », « fonds » / « fond ») : la
               référence suit peut-être une autre édition ou corrige le texte ;
  ponctuation  virgule, point-virgule ou deux-points absents de l'EPUB entre deux mots
               identiques des deux côtés (« de Poithou d'Angou » → « de Poithou, d'Angou »).
               À réserver à une référence de la MÊME édition (autre numérisation : Google
               Livres, Internet Archive) : l'OCR perd souvent ces petits signes. Seuls des
               signes sont ajoutés, jamais retirés ni remplacés.
La référence peut être un PDF, un texte brut ou un EPUB (autre numérisation).
Les mots en plus ou en moins (omissions, « sic ») ne sont jamais appliqués :
ils sont listés dans le rapport.

Droits : une édition moderne (texte établi, modernisé, annoté) est une œuvre
protégée même si le texte d'origine est libre. S'en servir pour corriger les
erreurs d'OCR (catégorie « ocr ») revient à vérifier une lecture ; reprendre ses
choix de modernisation et de ponctuation reproduit son travail d'éditeur :
demandez l'accord de l'éditeur avant de diffuser un tel résultat.

Usage :
  python3 epub_reference.py livre.epub "Chardin voyages.pdf" --from-page 118 \\
      -o livre-corrige.epub --report ecarts.html
  python3 epub_reference.py livre.epub ref.pdf --from-page 118 --apply ocr,esperluette -o …
"""

import argparse
import collections
import difflib
import html
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from epub_longs import (Doc, EPUB2, decode_text, fix_doctype, get_attr, load_wordlist,  # noqa: E402
                        resolve, text_holders)

CATS = collections.OrderedDict([
    ("ocr", "Erreurs d'OCR (lettres mal lues, mots coupés ou collés, s long)"),
    ("esperluette", "« & » → « et »"),
    ("apostrophes", "Apostrophes typographiques"),
    ("casse", "Majuscules / minuscules"),
    ("graphie", "Graphie et accents de la référence"),
    ("variante", "Variantes de texte entre les éditions (autre mot, accord…)"),
    ("ponctuation", "Ponctuation absente de l'EPUB (, ; :)"),
    ("absent", "Mots absents de l'EPUB (jamais appliqué)"),
    ("enplus", "Mots en plus dans l'EPUB (jamais appliqué)"),
])
WORD = re.compile(r"&|[^\W\d_]+(?:['’][^\W\d_]+)*", re.U)
S_LONG_AMBIGUOUS = set("font fait fais faits forte fortes fort foi fi fur fuite fuites fuis fuit ferment "
                       "fervent fol fols fous fous feroit feroient fera feront fable fables".split())


def skel(w):
    if w == "&":
        return "et"
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    w = re.sub(r"[^a-zœæſ]", "", w).replace("œ", "oe").replace("æ", "ae").replace("ſ", "s")
    w = w.replace("f", "s").replace("y", "i").replace("oi", "ai")
    w = re.sub(r"(.)\1", r"\1", w)
    return re.sub(r"ez$", "es", w)


# --------------------------------------------------------------------------
# Texte de référence
# --------------------------------------------------------------------------

def epub_text(path):
    """Texte d'un EPUB, paragraphe par paragraphe, dans l'ordre du spine."""
    z = zipfile.ZipFile(path)
    container = z.read("META-INF/container.xml").decode("utf-8", "replace")
    opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)["']""", container).group(1)
    opf = decode_text(z.read(opf_path))[0]
    items = {}
    for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
        if get_attr(m.group(0), "href"):
            items[get_attr(m.group(0), "id")] = resolve(opf_path, get_attr(m.group(0), "href"))
    out = []
    for i in re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)["']""", opf):
        if i not in items or items[i] not in z.namelist():
            continue
        t = decode_text(z.read(items[i]))[0]
        t = re.sub(r"(?is)<(head|style|script)\b.*?</\1>", " ", t)
        t = re.sub(r"(?i)</(p|div|h\d|li|td|tr)>|<br\s*/?>", "\n", t)
        out.append(html.unescape(re.sub(r"<[^>]+>", "", t)))
    return "\n".join(out)


def reference_text(path, from_page, to_page):
    if path.lower().endswith(".pdf"):
        try:
            import pymupdf
        except ImportError:
            try:
                import fitz as pymupdf
            except ImportError:
                sys.exit("Lire un PDF demande PyMuPDF : pip install pymupdf")
        d = pymupdf.open(path)
        a, b = max(0, from_page - 1), min(d.page_count, to_page or d.page_count)
        sizes = collections.Counter()
        for i in range(a, min(b, a + 40)):
            for blk in d[i].get_text("dict")["blocks"]:
                for ln in blk.get("lines", []):
                    for sp in ln["spans"]:
                        sizes[round(sp["size"], 1)] += len(sp["text"])
        body = sizes.most_common(1)[0][0] if sizes else 12
        parts = []
        for i in range(a, b):
            for blk in d[i].get_text("dict")["blocks"]:
                for ln in blk.get("lines", []):
                    for sp in ln["spans"]:
                        if sp["size"] >= 0.92 * body:      # notes et appels de note écartés
                            parts.append(sp["text"])
                    parts.append("\n")
        text = "".join(parts)
        # un trait d'union en fin de ligne est un vrai trait (« c'est-à-|dire », « au-|delà ») :
        # les PDF composés par traitement de texte ne coupent pas les mots
        text = re.sub(r"-\n", "-", text)
    elif path.lower().endswith(".epub"):
        text = epub_text(path)
        text = re.sub(r"<<+\s?|&lt;&lt;", "« ", text)          # guillemets lus « << » par l'OCR
        text = re.sub(r"\s?>>+|&gt;&gt;", " »", text)
        text = re.sub(r"(?<=[^\W\d_])-\n\s*(?=[^\W\d_A-ZÀ-Ý])", "", text)  # césures
        text = re.sub(r"(?<=[^\W\d_])-\n\s*(?=[A-ZÀ-Ý])", "-", text)   # « Saint-|Jaques »
    else:
        text = open(path, encoding="utf-8", errors="replace").read()
    return re.sub(r"\[(?:[IVXLC]+,\s*)?\d+\]", " ", text)   # repères de pagination


def reference_words(path, from_page, to_page):
    """Mots de la référence, et ce qui sépare chaque mot du suivant (ponctuation)."""
    text = reference_text(path, from_page, to_page)
    ms = list(WORD.finditer(text))
    words = [m.group(0) for m in ms]
    gaps = [text[m.end():n.start()] for m, n in zip(ms, ms[1:])] + [""]
    return words, gaps


PUNCT_GAP = re.compile(r"^\s*([«»]?)\s*([,;:])?\s*([«»]?)\s*$")


def punct_to_add(egap, rgap):
    """Signe à ajouter dans l'écart EPUB egap d'après l'écart de la référence rgap, ou None.
    Les appels de note de la référence (chiffres, astérisques) sont ignorés."""
    rgap = re.sub(r"[\d*•'`°]+", " ", rgap)
    if "\n" in egap or re.search(r"[^\s«»]", egap):
        return None                         # l'EPUB a déjà un signe (ou du texte) à cet endroit
    me, mr = PUNCT_GAP.match(egap), PUNCT_GAP.match(rgap)
    if not mr or not mr.group(2) or not me:
        return None
    # mêmes guillemets des deux côtés, à la même place
    if (me.group(1) or me.group(3)) != (mr.group(1) or mr.group(3)):
        return None
    sign = mr.group(2)
    q = me.group(1) or me.group(3)
    if not q:
        return sign + " "
    if mr.group(1):                          # « » , » : le signe suit le guillemet fermant
        return " %s%s " % (q, sign)
    return "%s %s " % (sign, q)              # « , « » : le signe précède le guillemet ouvrant


# --------------------------------------------------------------------------
# Alignement d'un paragraphe
# --------------------------------------------------------------------------

class Aligner:
    def __init__(self, ref):
        self.R = ref
        self.SR = [skel(w) for w in ref]
        self.index = collections.defaultdict(list)
        for i in range(len(self.SR) - 3):
            self.index[tuple(self.SR[i:i + 4])].append(i)

    def locate(self, se):
        votes = collections.Counter()
        for i in range(len(se) - 3):
            pos = self.index.get(tuple(se[i:i + 4]), ())
            if 0 < len(pos) <= 3:
                for p in pos:
                    votes[p - i] += 1
        if not votes:
            return None
        off, v = votes.most_common(1)[0]
        return off if v >= 2 or len(se) < 12 else off


def plain(w):
    w = unicodedata.normalize("NFD", w.lower().replace("’", "'"))
    return "".join(c for c in w if unicodedata.category(c) != "Mn")


def s_long_swap(e, r):
    """Seule différence : des « f » à la place de « s » (ou l'inverse) — s long mal lu."""
    e, r = plain(e), plain(r)
    return len(e) == len(r) and e != r and all(x == y or {x, y} == {"f", "s"} for x, y in zip(e, r))


def is_word(w, wordlist, vocab):
    """Mot du français (liste de mots) ; sans liste, mot fréquent du livre. Une erreur d'OCR
    répétée (« vlande » ×24) ne devient pas un mot pour autant."""
    lw = w.lower().replace("’", "'")
    if wordlist is not None:
        return lw in wordlist or lw.split("'")[-1] in wordlist
    return vocab.get(lw, 0) > 3


def letter_confusion(e, r):
    """Différences limitées aux confusions classiques de l'OCR : l / i / 1 / I."""
    e, r = plain(e), plain(r)
    return len(e) == len(r) and e != r and all(x == y or {x, y} <= set("il1|") for x, y in zip(e, r))


def classify(e_words, r_words, wordlist, vocab):
    """Catégorie d'un écart (mots de l'EPUB → mots de la référence). « ocr » est réservé aux
    vraies erreurs de lecture : s long, forme qui n'est pas un mot, mot coupé en morceaux qui
    n'en sont pas ; un autre mot correct (« leurs » / « leur ») est une variante d'édition."""
    if not e_words:
        return "absent"
    if not r_words:
        return "enplus"
    e, r = " ".join(e_words), " ".join(r_words)
    if e == "&" and r.lower() == "et":
        return "esperluette"
    if e.replace("'", "’") == r.replace("'", "’") and e != r:
        return "apostrophes"
    if e.lower() == r.lower():
        return "casse"
    if len(e_words) == len(r_words) == 1:
        if s_long_swap(e, r):
            # « font » → « sont » : f lu pour un s long. Dans l'autre sens (« Jessé » → « Jeffe »),
            # la référence peut elle-même garder une graphie ancienne : il faut un vrai mot.
            back = any(x == "s" and y == "f" for x, y in zip(plain(e), plain(r)))
            if not back or wordlist is None or is_word(r, wordlist, vocab):
                return "ocr"                     # « font » → « sont », « sois » → « fois »
            return "variante"
        if plain(e) == plain(r):
            return "casse" if e.lower() == r.lower() else "graphie"
        if letter_confusion(e, r):
            return "ocr"                         # « Dadlan » → « Dadian », « II » → « Il »
        if skel(e) == skel(r):
            if wordlist is not None and is_word(e, wordlist, vocab) and is_word(r, wordlist, vocab):
                return "variante"                # deux vrais mots : « nez » / « nés », « fond » / « fonds »
            return "graphie"                     # « Tiflis » / « Tifflis », « pié » / « pied »
        if e[:1].isupper() or len(e) <= 3:
            # nom propre (« Ptolémée » / « Ptolomée ») ou abréviation (« Ste ») : la graphie
            # de l'EPUB peut être la plus moderne ; seules les confusions ci-dessus sont sûres
            return "variante"
        if not is_word(e, wordlist, vocab) and \
                difflib.SequenceMatcher(None, plain(e), plain(r)).ratio() >= 0.6:
            return "ocr"                         # « vlande » → « viande », « crlant » → « criant »
        return "variante"
    # mots coupés ou collés
    if len(e_words) == 1 and skel(e) == skel("".join(r_words)):
        return "graphie"                         # « dequoi » / « de quoi », « Garderobe »
    if skel("".join(e_words)) == skel("".join(r_words)):
        pieces_ok = all(is_word(w, wordlist, vocab) for w in e_words)
        return "graphie" if pieces_ok else "ocr"   # « par tout » / « Roy al »
    return "variante"


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Corriger un EPUB d'après une autre édition du texte.")
    ap.add_argument("epub")
    ap.add_argument("reference", help="PDF ou fichier texte de l'édition de référence")
    ap.add_argument("-o", "--output", help="EPUB corrigé (défaut : en place)")
    ap.add_argument("--from-page", type=int, default=1, help="première page utile du PDF")
    ap.add_argument("--to-page", type=int, default=0, help="dernière page utile du PDF")
    ap.add_argument("--apply", default="ocr",
                    help="catégories à appliquer, séparées par des virgules "
                         "(ocr, esperluette, apostrophes, casse, graphie ; « aucune » pour le rapport seul)")
    ap.add_argument("--keep", default="",
                    help="mots de l'EPUB à ne jamais remplacer, séparés par des virgules "
                         "(ex. « Ptolémée, Européens, l'économie ») ; casse, accents et apostrophes ignorés")
    ap.add_argument("--max-variant-words", type=int, default=3,
                    help="une variante n'est appliquée que si elle remplace au plus ce nombre de mots, "
                         "et par au plus ce nombre de mots (défaut 3)")
    ap.add_argument("--min-ratio", type=float, default=0.8,
                    help="ressemblance minimale d'un paragraphe avec la référence (défaut 0,8)")
    ap.add_argument("--report", help="rapport HTML des écarts (défaut : <sortie>-ecarts.html)")
    ap.add_argument("--wordlist", default="auto", help="liste de mots français (fichier ou « auto »)")
    ap.add_argument("--dry-run", action="store_true", help="rapport seulement, aucun EPUB écrit")
    opts = ap.parse_args()

    apply = set() if opts.apply in ("aucune", "none", "") else set(x.strip() for x in opts.apply.split(","))
    bad = apply - set(CATS)
    if bad:
        sys.exit("Catégorie inconnue : %s" % ", ".join(sorted(bad)))
    apply -= {"absent", "enplus"}

    keep = {plain(w.strip()) for w in opts.keep.split(",") if w.strip()}
    ref, ref_gaps = reference_words(opts.reference, opts.from_page, opts.to_page)
    if len(ref) < 50:
        sys.exit("Référence presque vide (%d mots) : vérifiez --from-page / le fichier." % len(ref))
    print("Référence : %d mots" % len(ref))
    al = Aligner(ref)
    wordlist = load_wordlist(opts.wordlist)

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(zin.namelist())
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

        vocab = collections.Counter(w.lower() for d in docs for w in WORD.findall("".join(d.body.itertext())))
        found = collections.Counter()           # (catégorie, epub, référence) -> occurrences
        examples = {}
        applied = collections.Counter()
        guarded, guarded_ex = collections.Counter(), {}
        stats = collections.Counter()
        changed_docs = set()

        for d in docs:
            blocks = [el for el in d.body.iter()
                      if el.tag.rsplit("}", 1)[-1] in ("p", "h1", "h2", "h3", "h4", "li", "td")]
            for el in blocks:
                # mots du bloc avec leur emplacement (nœud de texte, début, fin)
                slots = []
                for holder, attr in text_holders(el):
                    if holder is not el and holder.tag.rsplit("}", 1)[-1] in ("p", "h1", "h2", "h3", "h4", "li"):
                        continue
                    s = getattr(holder, attr) or ""
                    for m in WORD.finditer(s):
                        slots.append((holder, attr, m.start(), m.end(), m.group(0)))
                if len(slots) < 6:
                    stats["blocs trop courts"] += 1
                    continue
                E = [x[4] for x in slots]
                SE = [skel(w) for w in E]
                off = al.locate(SE)
                if off is None:
                    stats["blocs non retrouvés"] += 1
                    continue
                # fenêtre élargie : la référence peut intercaler des notes ou un apparat de
                # variantes au milieu du paragraphe (OCR de Google) ; la ressemblance se mesure
                # alors sur les mots de l'EPUB retrouvés, pas sur la longueur de la fenêtre
                a, b = max(0, off - 10), min(len(al.SR), off + int(len(SE) * 1.5) + 60)
                sm = difflib.SequenceMatcher(None, SE, al.SR[a:b], autojunk=False)
                covered = sum(m.size for m in sm.get_matching_blocks()) / max(1, len(SE))
                if covered < opts.min_ratio:
                    stats["blocs trop différents"] += 1
                    continue
                stats["blocs alignés"] += 1
                edits = []                       # (indices EPUB, texte de remplacement)
                punct_edits = []                 # (nœud, attribut, début, fin, nouvel écart)
                shifts, merged = [], set()       # décalages laissés par les corrections de mots
                codes = sm.get_opcodes()
                for k_op, (op, i1, i2, j1, j2) in enumerate(codes):
                    # la fenêtre de la référence déborde de 10 mots de chaque côté : ce qui
                    # dépasse au début ou à la fin du paragraphe n'est pas un mot absent
                    if op == "insert" and (k_op == 0 or k_op == len(codes) - 1):
                        continue
                    pairs = []
                    if op == "equal":
                        pairs = [([i], [a + j]) for i, j in zip(range(i1, i2), range(j1, j2)) if E[i] != al.R[a + j]]
                    elif op in ("replace", "delete", "insert"):
                        pairs = [(list(range(i1, i2)), list(range(a + j1, a + j2)))]
                    for ei, rj in pairs:
                        ew, rw = [E[i] for i in ei], [al.R[j] for j in rj]
                        cat = classify(ew, rw, wordlist, vocab)
                        key = (cat, " ".join(ew), " ".join(rw))
                        found[key] += 1
                        if key not in examples:
                            ctx_i = ei[0] if ei else min(i1, len(E) - 1)
                            examples[key] = (d.path, " ".join(E[max(0, ctx_i - 6):ctx_i + 7]))
                        blocked = any(plain(w) in keep for w in ew)
                        if cat in ("ocr", "graphie") and ei and len(ei) > 1:
                            # « Nostre-Dame » : un vrai trait d'union entre les mots de l'EPUB
                            h0, a0 = slots[ei[0]][0], slots[ei[0]][1]
                            if all(slots[k][0] is h0 and slots[k][1] == a0 for k in ei) and \
                                    "-" in (getattr(h0, a0) or "")[slots[ei[0]][3]:slots[ei[-1]][2]]:
                                blocked = True
                        if cat == "ocr" and ew and rw and not ocr_guard(ew, rw, wordlist, vocab):
                            blocked = True
                        if cat == "variante" and (len(ew) > opts.max_variant_words or
                                                  len(rw) > opts.max_variant_words):
                            blocked = True       # phrase entière remplacée : à voir à la main
                        if cat == "variante" and not blocked:
                            why = variant_guard(ew, rw, wordlist, vocab)
                            if why:
                                blocked = True
                                guarded[why] += 1
                                guarded_ex.setdefault(why, collections.Counter())[(" ".join(ew), " ".join(rw))] += 1
                        if blocked and cat in apply:
                            stats["écarts gardés (--keep, longueur)"] += 1
                        if cat in apply and ei and rw and not blocked:
                            # la majuscule de l'EPUB est gardée, sauf « casse » hors début de phrase :
                            # « … royaume. Ils » reste « Ils » même si la référence ponctue « ; ils »
                            new = " ".join(rw)
                            if ew[0][:1].isupper() and new[:1].islower():
                                h0, a0, st0 = slots[ei[0]][0], slots[ei[0]][1], slots[ei[0]][2]
                                before = (getattr(h0, a0) or "")[:st0]
                                sentence_start = (not before.strip() and h0 is el and a0 == "text") or \
                                    re.search(r"[.!?»:]\s*$", before)
                                if cat != "casse" or sentence_start:
                                    new = new[:1].upper() + new[1:]
                            edits.append((ei, new, cat))
                # application, de la fin vers le début ; plusieurs mots EPUB → le premier reçoit le
                # texte, les suivants sont vidés (s'ils sont dans le même nœud, l'espace entre eux part)
                # ponctuation : entre deux mots alignés tels quels des deux côtés
                for op, i1, i2, j1, j2 in codes:
                    if op != "equal":
                        continue
                    for i, j in zip(range(i1, i2 - 1), range(a + j1, a + j2 - 1)):
                        h0, a0, _s0, e0, w0 = slots[i]
                        h1, a1, s1, _e1, w1 = slots[i + 1]
                        if h0 is not h1 or a0 != a1:
                            continue                 # un appel de note ou une balise entre les deux
                        egap = (getattr(h0, a0) or "")[e0:s1]
                        new_gap = punct_to_add(egap, ref_gaps[j])
                        if new_gap is None:
                            continue
                        sign = new_gap.strip(" «»")
                        key = ("ponctuation", "%s %s" % (w0, w1), "%s%s %s" % (w0, sign, w1))
                        found[key] += 1
                        if key not in examples:
                            examples[key] = (d.path, " ".join(E[max(0, i - 6):i + 7]))
                        if "ponctuation" in apply:
                            punct_edits.append((h0, a0, e0, s1, new_gap))
                for ei, new, cat in sorted(edits, key=lambda x: -x[0][0]):
                    first = slots[ei[0]]
                    same_node = all(slots[i][0] is first[0] and slots[i][1] == first[1] for i in ei)
                    if not same_node:
                        # mot coupé par une balise d'italique : « <i>Nac</i>chivan », « <i>Mingre</i> <i>lie</i> »
                        merged.update((id(slots[ei[0]][0]), id(slots[ei[1]][0])))
                        if len(ei) == 2 and merge_across(el, slots[ei[0]], slots[ei[1]], new):
                            applied[cat] += 1
                            changed_docs.add(d.path)
                        continue
                    holder, attr = first[0], first[1]
                    s = getattr(holder, attr)
                    start, end = first[2], slots[ei[-1]][3]
                    setattr(holder, attr, s[:start] + new + s[end:])
                    shifts.append((id(holder), attr, start, len(new) - (end - start)))
                    applied[cat] += 1
                    changed_docs.add(d.path)
                # ponctuation en dernier, positions décalées par les corrections de mots
                for h0, a0, st, en, new_gap in sorted(punct_edits, key=lambda x: -x[2]):
                    if id(h0) in merged:
                        continue
                    delta = sum(dl for hid, at, pos, dl in shifts if hid == id(h0) and at == a0 and pos < st)
                    v = getattr(h0, a0)
                    st, en = st + delta, en + delta
                    if v[st:en].strip(" «»"):
                        continue
                    setattr(h0, a0, v[:st] + new_gap + v[en:])
                    applied["ponctuation"] += 1
                    changed_docs.add(d.path)

        # rapport
        report = opts.report or re.sub(r"\.epub$", "", opts.output or src) + "-ecarts.html"
        write_report(report, found, examples, applied, stats, apply, opts.reference)
        print("Blocs alignés : %d — non retrouvés : %d — trop différents : %d"
              % (stats["blocs alignés"], stats["blocs non retrouvés"], stats["blocs trop différents"]))
        for cat, label in CATS.items():
            n = sum(v for k, v in found.items() if k[0] == cat)
            if n:
                print("  %-58s %6d%s" % (label, n, ("  → %d appliqués" % applied[cat]) if cat in apply else ""))
        for why, n in guarded.items():
            ex = ", ".join("%s → %s" % kv for kv, _ in guarded_ex[why].most_common(6))
            print("  variantes gardées (%s) : %d — %s" % (why, n, ex))
        print("Rapport : %s" % report)
        if opts.dry_run or not applied:
            if not applied:
                print("Aucune correction appliquée.")
            return

        out_path = opts.output or src
        new_data = {d.path: d.serialize() for d in docs if d.path in changed_docs or fix_doctype(d.prefix) != d.prefix}
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


def ocr_guard(ew, rw, wordlist, vocab):
    """Faux si la « correction d'OCR » est douteuse :
    - mot tronqué par la référence (« voulenu » → « voulen », « avenc » → « aven ») : la
      référence a coupé le mot en fin de ligne ;
    - mot éclaté en morceaux qui ne sont pas des mots (« dommaige » → « dom maige »)."""
    if len(ew) == len(rw) == 1:
        e, r = plain(ew[0]), plain(rw[0])
        if vocab.get(ew[0].lower(), 0) >= 3 and not s_long_swap(ew[0], rw[0]) and \
                not letter_confusion(ew[0], rw[0]) and vocab.get(rw[0].lower(), 0) < 3:
            return False                     # forme courante du livre (« tenoit », « voulsist »)
        if len(r) < len(e) and (e.startswith(r) or e.endswith(r)) and \
                not (wordlist is not None and is_word(rw[0], wordlist, vocab)):
            return False
    if len(ew) > len(rw):
        # mots recollés : « du roy » → « duroy », « tous esbahis » → « tousesbahis ». Si chaque
        # morceau est un mot connu (du livre ou de la langue), c'est la référence qui colle
        known = lambda w: is_word(w, wordlist, vocab) or vocab.get(w.lower(), 0) >= 2
        if all(known(w) for w in ew) and not all(known(w) for w in rw):
            return False
    if len(rw) > len(ew):
        if not all(is_word(w, wordlist, vocab) or vocab.get(w.lower(), 0) for w in rw):
            return False
    return True


def variant_guard(ew, rw, wordlist, vocab):
    """Raison de ne pas appliquer une variante, ou None.
    - archaïsme : l'EPUB a un mot moderne, la référence une graphie qui ne l'est pas
      (« enverrait » → « envoyerait », « Vizir » → « Visir », « Caravansérail » → « Caravanserai ») ;
    - abréviation : un mot entier remplacé par une abréviation (« Révérends Pères » → « RR PP ») ;
    - nom propre : deux noms propres différents et tous deux corrects (« Grèce » → « Grève »)."""
    if wordlist is None:
        return None
    e, r = " ".join(ew), " ".join(rw)
    if all(len(w) <= 2 for w in rw) and any(len(w) > 3 for w in ew):
        return "abréviation"
    if len(ew) == len(rw) == 1:
        if is_word(e, wordlist, vocab) and not is_word(r, wordlist, vocab) and \
                difflib.SequenceMatcher(None, plain(e), plain(r)).ratio() >= 0.7:
            return "archaïsme de la référence"
        if e[:1].isupper() and r[:1].isupper() and len(e) >= 5 and \
                is_word(e, wordlist, vocab) and is_word(r, wordlist, vocab):
            return "nom propre"
    return None


def merge_across(block, first, second, new):
    """Recolle un mot coupé entre deux nœuds de texte voisins d'un même élément en ligne
    (italique) : le mot entier passe dans le premier élément. Vrai si fait."""
    h1, a1, s1, e1 = first[0], first[1], first[2], first[3]
    h2, a2, s2, e2 = second[0], second[1], second[2], second[3]
    t1 = getattr(h1, a1) or ""
    if a1 != "text" or t1[e1:].strip():
        return False                              # le 1er morceau doit finir l'élément
    if h2 is h1 and a2 == "tail" and not (h1.tail or "")[:s2].strip():
        h1.text = t1[:s1] + new                   # <i>Nac</i>chivan → <i>Nacchivan</i>
        h1.tail = h1.tail[e2:]
        return True
    parent = next((p for p in block.iter() if h1 in list(p)), None)
    if parent is None or a2 != "text" or (getattr(h2, "text") or "")[:s2].strip():
        return False
    kids = list(parent)
    i = kids.index(h1)
    if i + 1 >= len(kids) or kids[i + 1] is not h2 or (h1.tail or "").strip() or h2.tag != h1.tag:
        return False
    # <i>Mingre</i> <i>lie</i> → <i>Mingrélie</i> (les deux éléments fusionnent)
    h1.text = t1[:s1] + new + (h2.text or "")[e2:]
    for ch in list(h2):
        h2.remove(ch)
        h1.append(ch)
    h1.tail = h2.tail
    parent.remove(h2)
    return True


def write_report(path, found, examples, applied, stats, apply, refname):
    e = html.escape
    out = ['<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Écarts avec la référence</title>',
           '<style>body{font:15px/1.5 Georgia,serif;max-width:64rem;margin:2rem auto;padding:0 1rem;color:#1f2a44;'
           'background:#f3f5f2}h1{font-size:1.6rem}details{border-top:2px solid #1f2a44;margin:1.2rem 0;'
           'padding-top:.3rem}summary{cursor:pointer;font-weight:600;font-size:1.1rem}table{border-collapse:'
           'collapse;width:100%;font-size:.9rem}td,th{border-bottom:1px solid #d3d9d4;padding:.25rem .5rem;'
           'text-align:left;vertical-align:top}td.n{text-align:right}del{color:#9b2c2c}ins{color:#2f7a6b;'
           'text-decoration:none;font-weight:600}.ctx{color:#5d6673;font-size:.85rem}</style></head><body>',
           '<h1>Écarts avec la référence</h1><p>%s — blocs alignés : %d, non retrouvés : %d, trop différents : %d.</p>'
           % (e(os.path.basename(refname)), stats["blocs alignés"], stats["blocs non retrouvés"],
              stats["blocs trop différents"])]
    for cat, label in CATS.items():
        rows = sorted(((k, v) for k, v in found.items() if k[0] == cat), key=lambda kv: -kv[1])
        if not rows:
            continue
        total = sum(v for _, v in rows)
        state = "appliqués" if cat in apply else "non appliqués"
        out.append('<details%s><summary>%s — %d (%s)</summary><table><tr><th>EPUB</th><th>Référence</th>'
                   '<th>Occ.</th><th>Exemple</th></tr>' % (" open" if cat == "ocr" else "", e(label), total, state))
        for (c, ew, rw), v in rows[:600]:
            f, ctx = examples.get((c, ew, rw), ("", ""))
            out.append('<tr><td><del>%s</del></td><td><ins>%s</ins></td><td class="n">%d</td>'
                       '<td class="ctx">%s<br>%s</td></tr>' % (e(ew), e(rw), v, e(os.path.basename(f)), e(ctx)))
        out.append("</table></details>")
    out.append("</body></html>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


if __name__ == "__main__":
    main()
