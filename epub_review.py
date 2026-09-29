#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_review.py — Prépare la relecture dans Sigil d'un EPUB issu d'OCR.

Produit un RAPPORT HTML (à ouvrir à côté de Sigil) qui liste, fichier par
fichier, ce qui mérite un coup d'œil, avec pour chaque cas :
  * le nom du fichier tel que Sigil l'affiche et un extrait à rechercher ;
  * un lien vers la page scannée d'origine (Google Books : les ancres
    GBS.PA17… donnent directement la page ; modèle d'URL réglable) ;
Catégories : mots collés, mots coupés, casse mélangée, chiffres dans les
mots, lettres isolées, ponctuation collée, paragraphes très courts, coupures
de paragraphe douteuses, trous et doublons dans la numérotation des
chapitres, remplacements globaux possibles (ß, ſ, ligatures…).

Options :
  --mark FICHIER.epub   écrit une copie où chaque cas est entouré de
                        <span class="a-verifier" title="…"> (surligné en
                        jaune) : dans Sigil, rechercher  a-verifier  pour
                        passer d'un cas au suivant. Le texte n'est pas modifié.
  --unmark              retire tous les marqueurs (à faire avant publication) ;
                        avec -o pour écrire ailleurs, sinon en place.
  --dict-out FICHIER    liste des mots du livre (≥ 3 occurrences), un par ligne,
                        utilisable comme dictionnaire utilisateur de Sigil pour
                        que le correcteur ne souligne plus l'orthographe ancienne.

Usage :
  python3 epub_review.py livre.epub                       # → livre-relecture.html
  python3 epub_review.py livre.epub --mark livre-a-relire.epub
  python3 epub_review.py livre-a-relire.epub --unmark -o livre-final.epub
"""

import argparse
import collections
import datetime
import html
import html.entities
import os
import posixpath
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote

XHTML_NS = "http://www.w3.org/1999/xhtml"
for _p, _u in (("", XHTML_NS), ("svg", "http://www.w3.org/2000/svg"),
               ("xlink", "http://www.w3.org/1999/xlink"), ("epub", "http://www.idpf.org/2007/ops"),
               ("m", "http://www.w3.org/1998/Math/MathML")):
    ET.register_namespace(_p, _u)

TEXT_BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "div"}
MARK_CLASS = "a-verifier"
CSS_BEGIN = "/* --- epub_review.py (marqueurs de relecture) --- */"
CSS_END = "/* --- fin epub_review.py --- */"
CSS_RULES = CSS_BEGIN + """
.a-verifier { background: #ffe58a; }
p.a-verifier, h1.a-verifier, h2.a-verifier { background: none; outline: 2px dashed #c99a06; }
""" + CSS_END + "\n"

LETTERS = "A-Za-zÀ-ÖØ-öø-ÿŒœÆæß"
WORD_RE = re.compile(r"[%s]+" % LETTERS)
ALLOWED_SINGLE = set("aàyoôAÀYOÔ&")
CHAPTER_RE = re.compile(r"^(?:[^a-zà-ÿ]{0,30}?\s)?(?:CHA)?(?:CHAPITRE|Chapitre|CHAP|Chap)\b\s*\.?\s*(.+?)[\s.]*$")
ORDINALS = [("premi", 1), ("secon", 2), ("deux", 2), ("tier", 3), ("trois", 3), ("quatr", 4),
            ("cinq", 5), ("sixi", 6), ("sept", 7), ("huit", 8), ("neuf", 9), ("dixi", 10)]
GLOBAL_FIXES = [
    ("ß", "ss", "« ß » : s long + s mal lu (außi → aussi)"),
    ("ſ", "s", "s long"),
    ("ﬁ", "fi", "ligature fi"), ("ﬂ", "fl", "ligature fl"), ("ﬀ", "ff", "ligature ff"),
    ("ﬃ", "ffi", "ligature ffi"), ("ﬅ", "st", "ligature st"),
    ("|", "", "barre verticale (souvent un I ou un l mal lu)"),
    ("¬", "", "trait de césure OCR"),
]
# Découpages qui ne révèlent pas un mot collé mais une dérivation normale
SUFFIXES = {"aient", "ait", "ais", "ant", "ants", "ante", "antes", "ment", "ments", "ent", "rent",
            "ront", "ra", "rai", "ras", "rez", "ons", "ions", "iez", "ez", "er", "es", "ées", "ée",
            "able", "ables", "ance", "ances", "eur", "eurs", "euse", "euses", "ure", "ures", "ion",
            "ions", "ité", "ités", "isme", "iste", "ise", "ises", "age", "ages", "ette", "ettes"}
PREFIXES = {"entre", "contre", "quatre", "sur", "sous", "tres", "très", "mal", "bien", "non",
            "re", "dé", "pré", "anti", "demi"}
CATEGORIES = collections.OrderedDict([
    ("chapitres", "Numérotation des chapitres"),
    ("slong", "S long lu « f » ? (mot laissé tel quel)"),
    ("oi", "Imparfait en « oi » ? (mot laissé tel quel)"),
    ("ocr", "Mots peu sûrs pour l'OCR"),
    ("notes", "Notes sans appel dans le texte"),
    ("cesures", "Mots coupés par un trait d'union"),
    ("colles", "Mots collés ?"),
    ("coupes", "Mots coupés ?"),
    ("casse", "Casse mélangée dans un mot"),
    ("chiffres", "Chiffres dans un mot"),
    ("isolees", "Lettres isolées"),
    ("ponctuation", "Ponctuation collée ou mal placée"),
    ("lettrines", "Lettrine perdue ?"),
    ("courts", "Paragraphes très courts"),
    ("coupures", "Paragraphe qui semble coupé"),
])
HELP = {
    "oi": "Forme en « oi » laissée telle quelle par la modernisation (nom propre, nationalité, forme "
          "inconnue : « François », « Anglois », « appelloit »). Décidez ici, ou une fois pour toutes "
          "dans l'onglet « oi → ai » de Prescel.",
    "lettrines": "Le paragraphe commence par un mot incomplet : la grande lettre du début (lettrine) "
                 "n'a pas été lue par l'OCR (« Ous avons » pour « NOus avons »). La lettre proposée "
                 "est celle qui donne un mot fréquent du livre ; vérifiez sur la page scannée.",
    "cesures": "Trait d'union suivi d'une espace au milieu d'une phrase : reste d'une coupure de fin "
               "de ligne de l'imprimé (« estran- ges »). Recollez le mot ; la correction proposée est "
               "suivie de « ? » quand ce mot n'existe pas ailleurs dans le livre.",
    "notes": "Note de bas de page dont l'appel n'a pas été retrouvé (chiffre perdu ou mal lu par "
             "l'OCR). Retrouvez le mot sur la page scannée et ajoutez l'appel en exposant : "
             "<sup><a href=\"#note-N\" id=\"appel-N\">1</a></sup>, et id=\"note-N\" sur la note.",
    "ocr": "Mots dont l'OCR lui-même doutait (confiance faible), déjà surlignés à l'import du PDF. "
           "Comparez avec la page scannée.",
    "slong": "Mot qui existe sous les deux formes (« font »/« sont », « fait »/« sait ») : la "
             "correction automatique l'a laissé tel quel. Comparez avec la page scannée ; pour trancher "
             "une fois pour toutes, cochez-le dans la liste du s long et relancez.",
    "chapitres": "Numéros manquants, répétés ou illisibles. Un titre manquant est souvent sur une page "
                 "que l'OCR a traitée comme image : ajoutez-le en <h2> dans Sigil puis relancez "
                 "epub_structure.py pour régénérer la table.",
    "colles": "Mot absent du reste du livre mais qui se coupe en deux mots fréquents "
              "(« notableschoses »). Ajoutez l'espace manquante.",
    "coupes": "Deux morceaux qui forment un mot fréquent du livre (« a vec »). Supprimez l'espace.",
    "casse": "Majuscule au milieu d'un mot (« AVtres », « DaEtylus ») : lettre souvent mal reconnue.",
    "chiffres": "Un chiffre dans un mot est presque toujours une lettre mal lue (1 → l ou I, 0 → o).",
    "isolees": "Lettre seule qui n'est pas un mot (« e », « t ») : reste de lettrine, de manchette "
               "ou de tache.",
    "ponctuation": "Signe collé au mot suivant (« fins.Chapitre ») ou espace avant une virgule "
                   "ou un point.",
    "courts": "Paragraphe de quelques caractères qui n'est ni un titre ni une manchette : "
              "fragment à rattacher ou à supprimer.",
    "coupures": "Le paragraphe ne se termine pas par une ponctuation et le suivant commence par "
                "une majuscule : coupure de page non recollée, ou titre à baliser.",
}


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def X(tag):
    return "{%s}%s" % (XHTML_NS, tag)


def resolve(base, href):
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(href)))


def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8", data[:3]
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    enc = m.group(1).decode("ascii") if m else "utf-8"
    return data.decode(enc), enc, b""


def get_attr(tag, name):
    m = re.search(r"""\s%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % re.escape(name), tag, re.I)
    return None if not m else (m.group(1) if m.group(1) is not None else m.group(2))


def replace_named_entities(text):
    def rep(m):
        if m.group(1) in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        cp = html.entities.name2codepoint.get(m.group(1))
        return "&#%d;" % cp if cp else m.group(0)
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", rep, text)


def text_of(el):
    return " ".join("".join(el.itertext()).split())


def classes(el):
    return set((el.get("class") or "").split())


def compact(s):
    return "".join((s or "").split())


EPUB2 = [True]      # mis à jour d'après la version du paquet (OPF)
XHTML11 = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
           '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">')


def fix_doctype(prefix):
    """EPUB 2 : epubcheck exige le DOCTYPE XHTML 1.1 (Google met du XHTML 1.0 Strict)."""
    if EPUB2[0] and re.search(r"<!DOCTYPE[^>]*XHTML 1\.0", prefix):
        return re.sub(r"<!DOCTYPE[^>]*>", lambda m: XHTML11, prefix, count=1)
    return prefix



class Doc:
    def __init__(self, path, text, enc, bom):
        self.path, self.enc, self.bom = path, enc, bom
        m = re.search(r"<(?:[\w-]+:)?html\b", text)
        self.prefix = text[:m.start()] if m else '<?xml version="1.0" encoding="utf-8"?>\n'
        self.root = ET.fromstring(replace_named_entities(text).encode("utf-8"))
        self.body = self.root.find(X("body"))

    def serialize(self):
        out = ET.tostring(self.root, encoding="unicode")
        return self.bom + (fix_doctype(self.prefix).rstrip() + "\n" + out + "\n").encode(
            self.enc, "xmlcharrefreplace")


def page_of(pid):
    """Page scannée désignée par une ancre : GBS.PA17 (Google), page-12 (pdf_to_epub)."""
    if not pid:
        return None
    if pid.startswith("GBS."):
        return pid[4:]
    m = re.match(r"page-(\w+)$", pid)
    return m.group(1) if m else None


def roman_to_int(s):
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    s = s.upper()
    if not s or any(c not in vals for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = vals[c]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total if total > 0 else None


ORD_UNITS = [("premi", 1), ("second", 2), ("tier", 3), ("onz", 11), ("douz", 12), ("treiz", 13),
             ("quatorz", 14), ("quinz", 15), ("seiz", 16), ("dix", 10), ("vingt", 20), ("trent", 30),
             ("quarant", 40), ("cinquant", 50), ("soixant", 60), ("cent", 100), ("un", 1), ("deux", 2),
             ("trois", 3), ("quatr", 4), ("cinq", 5), ("six", 6), ("sept", 7), ("huit", 8), ("neu", 9)]


def french_ordinal(raw):
    """« vingt-quatrie me » → 24, « onziesme » → 11, « trentieme » → 30 (0 si illisible)."""
    t = raw.lower().translate(str.maketrans("αβεζηικμνορτυχéèêàâęė", "abezhikmnoptyxeeeaaee"))
    t = re.sub(r"[^a-z\- ]", "", t).replace(" ", "")
    t = re.sub(r"-(?=[a-z]{1,2}$)", "", t)          # « dix-huitiem-e »
    total = 0
    for part in re.split(r"-|\bet\b", t):
        part = re.sub(r"(?:iesme|ieme|ime|me)$", "", part)
        if not part:
            continue
        for pref, val in ORD_UNITS:
            if part.startswith(pref):
                total = total * val if val == 100 and total else total + val
                break
        else:
            return 0
    return total


def chapter_number(label):
    m = CHAPTER_RE.match(label)
    if not m:
        return None, None
    raw = m.group(1).strip()
    comp = raw.replace(" ", "").replace("1", "I").replace("l", "I")
    n = roman_to_int(comp)
    if n is None and raw.isdigit():
        n = int(raw)
    if n is None:
        n = french_ordinal(raw) or None
    return n, raw


# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------

class Reviewer:
    def __init__(self, vocab, scan_template, wordlist=None, min_glued=11, longs=None, oi=None):
        self.vocab = vocab
        self.longs = longs or {}
        self.oi = oi or {}
        self.wordlist = wordlist
        self.min_glued = min_glued
        self.scan_template = scan_template
        self.items = collections.defaultdict(list)
        self.global_counts = collections.Counter()

    def scan_url(self, page):
        if not self.scan_template or not page:
            return None
        return self.scan_template.replace("{page}", quote(page))

    # -- recherche dans une chaîne ------------------------------------------
    def suspects_in(self, s):
        """Liste de (début, fin, catégorie, détail) dans une chaîne."""
        out = []
        v = self.vocab
        words = [(m.start(), m.end(), m.group(0)) for m in WORD_RE.finditer(s)]
        for i, (a, b, w) in enumerate(words):
            lw = w.lower()
            if lw in self.longs:
                out.append((a, b, "slong", "→ %s ?" % self.longs[lw]))
                continue
            if lw in self.oi:
                out.append((a, b, "oi", "→ %s ?" % self.oi[lw]))
                continue
            elided = b < len(s) and s[b] in "'’"
            # « a-t-il », « va-t-on » : seul le t euphonique, entre deux traits d'union, est admis.
            # Toute autre lettre collée à un trait reste signalée : c'est souvent un reste de
            # coupure de fin de ligne (« e- stant »).
            hyphenated = w in "tT" and a > 0 and s[a - 1] in "-‑" and b < len(s) and s[b] in "-‑"
            # casse mélangée : « AVtres », « DaEtylus » (sauf mots tout en capitales)
            if len(w) > 2 and not w.isupper() and not re.fullmatch(r"[ivxlcIVXLC]+", w) and \
                    re.search(r"[a-zà-ÿ][A-ZÀ-Þ]|^[A-ZÀ-Þ]{2,}[a-zà-ÿ]", w):
                out.append((a, b, "casse", w))
                continue
            # lettre isolée (les chiffres romains en minuscules sont admis)
            if len(w) == 1 and w not in ALLOWED_SINGLE and not elided and not hyphenated \
                    and not w.isupper() \
                    and w not in "ivxlc":
                out.append((a, b, "isolees", w))
                continue
            # mot collé
            # (seulement les mots longs : l'orthographe ancienne produit beaucoup de
            #  mots uniques légitimes, « portraicts », « vertueux »…)
            if len(w) >= self.min_glued and v.get(lw, 0) <= 1 and \
                    (self.wordlist is None or lw not in self.wordlist):
                best = None
                for k in range(3, len(lw) - 2):
                    l, r = lw[:k], lw[k:]
                    fl, fr = v.get(l, 0), v.get(r, 0)
                    if self.wordlist is not None:
                        ok = l in self.wordlist and r in self.wordlist
                    else:
                        ok = fl >= 5 and fr >= 5
                    if ok and (r in SUFFIXES or l in PREFIXES):
                        ok = False
                    if ok:
                        score = min(fl, fr)
                        if best is None or score > best[0]:
                            best = (score, w[:k] + " " + w[k:])
                if best:
                    out.append((a, b, "colles", "→ " + best[1]))
                    continue
            # mot coupé : « a vec »
            if i + 1 < len(words):
                a2, b2, w2 = words[i + 1]
                if s[b:a2] == " ":
                    glued = (w + w2).lower()
                    if v.get(glued, 0) >= 2 and (v.get(lw, 0) <= 1 or v.get(w2.lower(), 0) <= 1):
                        out.append((a, b2, "coupes", "→ " + w + w2))
        # coupure de fin de ligne restée dans le texte : « estran- ges », « e- stant »
        for m in re.finditer(r"([%s]+)[-‑¬]\s+([a-zà-öø-ÿœæſ]+)" % LETTERS, s):
            glued = (m.group(1) + m.group(2)).lower()
            detail = "→ " + m.group(1) + m.group(2) + ("" if self.vocab.get(glued, 0) else " ?")
            out.append((m.start(), m.end(), "cesures", detail))
        # chiffres dans un mot : « x1111 », « c0mme » (pas « 1er », « 2e »)
        for m in re.finditer(r"\b(?=\w*[%s])(?=\w*\d)\w+\b" % LETTERS, s):
            tok = m.group(0)
            if not re.fullmatch(r"\d+(?:er|re|e|ème|eme|es|o|°)", tok, re.I):
                out.append((m.start(), m.end(), "chiffres", tok))
        # phrase collée à la suivante : « fins.Chapitre » (pas « Chap.xv », « M.de »)
        for m in re.finditer(r"([%s]{2,})([.!?])([A-ZÀ-Þ][a-zà-ÿ]+)" % LETTERS, s):
            if m.group(1).lower() in ("chap", "fueil", "fueill", "cap", "liu") or len(m.group(1)) < 3:
                continue
            out.append((m.start(), m.end(), "ponctuation", m.group(0)))
        # virgules et deux-points collés : trop nombreux dans les imprimés anciens,
        # comptés pour un remplacement global plutôt que listés un par un
        self.global_counts["__comma"] += len(re.findall(r"[%s][,;:][%s]" % (LETTERS, LETTERS), s))
        for m in re.finditer(r"[%s] [,.](?!\.)" % LETTERS, s):
            out.append((m.start(), m.end(), "ponctuation", m.group(0)))
        # retirer les chevauchements (on garde le premier)
        out.sort(key=lambda x: (x[0], x[2] != "cesures", -x[1]))   # la coupure l'emporte
        cleaned, last_end = [], -1
        for it in out:
            if it[0] >= last_end:
                cleaned.append(it)
                last_end = it[1]
        return cleaned

    def lost_lettrine(self, text):
        """Paragraphe dont la lettrine a disparu à l'OCR : « Ous avons » (nous), « E vent »
        (le), « N vient » (on). Renvoie (longueur du premier mot, suggestion) ou None."""
        m = re.match(r"([%s]+)" % LETTERS, text)
        if not m:
            return None
        w = m.group(1)
        lw = w.lower()
        if len(w) > 1 and (self.vocab.get(lw, 0) > 1 or not w[:1].isupper()):
            return None
        if len(w) == 1 and w in "AÀYOÔ":
            return None
        best = []
        for L in "abcdefghijlmnopqrstuvy":
            n = self.vocab.get(L + lw, 0)
            if n >= 5:
                best.append((n, (L + lw).upper() if w.isupper() else L.upper() + lw))
        if not best:
            return None
        best.sort(reverse=True)
        sugg = " ou ".join(x[1] for x in best[:3])
        return len(w), "→ " + sugg + (" ?" if len(best) > 1 else "")

    def add(self, cat, doc, page, context, start, end, detail):
        lo = max(0, start - 45)
        hi = min(len(context), end + 45)
        self.items[cat].append({
            "file": posixpath.basename(doc.path), "path": doc.path, "page": page,
            "before": ("…" if lo > 0 else "") + context[lo:start],
            "hit": context[start:end],
            "after": context[end:hi] + ("…" if hi < len(context) else ""),
            "detail": detail, "url": self.scan_url(page),
        })

    # -- parcours d'un document ---------------------------------------------
    def review(self, doc, page_state, mark):
        blocks = [el for el in doc.body.iter() if lname(el) in TEXT_BLOCKS
                  and not any(lname(c) in TEXT_BLOCKS for c in el)]
        page = page_state[0]
        prev_block = None
        for el in blocks:
            # pages : ancres GBS.* dans et avant le bloc
            first_page = page
            if page_of(el.get("id")):
                first_page = page_of(el.get("id"))
            full = " ".join("".join(el.itertext()).split())
            if "note" in classes(el) and not any(lname(x) == "a" and x.get("href") for x in el.iter()):
                self.add("notes", doc, first_page, full, 0, min(len(full), 60), "note non reliée")
            # mots signalés par l'OCR à l'import (pdf_to_epub.py)
            for sp in el.iter():
                if lname(sp) == "span" and MARK_CLASS in classes(sp) and \
                        (sp.get("title") or "").startswith("OCR") and sp.text:
                    k = full.find(sp.text)
                    self.add("ocr", doc, first_page, full, max(0, k), max(0, k) + len(sp.text),
                             sp.get("title"))
            # suspects mot à mot, sur chaque nœud de texte
            for holder, attr, node_page in self.text_nodes(el, page):
                s = getattr(holder, attr) or ""
                if not s.strip():
                    continue
                hits = self.suspects_in(s)
                for (a, b, cat, detail) in hits:
                    self.add(cat, doc, node_page, s, a, b, detail)
                if hits and mark:
                    self.wrap(holder, attr, hits)
            for d in el.iter():
                pid = d.get("id") or ""
                if page_of(pid):
                    page = page_of(pid)
            # paragraphes courts / coupures douteuses
            n = lname(el)
            cls = classes(el)
            normal = n == "p" and not (cls & {"marge", "note", "centre", "droite", "sommaire",
                                              "numero", "image"})
            if normal and full and len(full) >= 25:
                lost = self.lost_lettrine(full)
                if lost:
                    self.add("lettrines", doc, first_page, full, 0, lost[0], lost[1])
                    if mark:
                        el.set("class", " ".join(sorted(cls | {MARK_CLASS})))
            if normal and full and len(full) < 25 and not re.search(r"[.!?:»)]$", full):
                self.add("courts", doc, first_page, full, 0, len(full), "%d caractères" % len(full))
                if mark:
                    el.set("class", " ".join(sorted(cls | {MARK_CLASS})))
            if normal and prev_block is not None:
                pt = text_of(prev_block)
                if len(pt) > 40 and not re.search(r"[.!?:;»)\]…,-]\s*$", pt) and \
                        re.match(r"[A-ZÀ-Þ][a-zà-ÿ]", full or ""):
                    self.add("coupures", doc, first_page, pt[-60:] + " ¶ " + full[:60],
                             len(pt[-60:]), len(pt[-60:]) + 3, "fin sans ponctuation")
            prev_block = el if normal else (prev_block if n == "div" or "marge" in cls
                                            or "note" in cls else None)
            # remplacements globaux
            for ch, _, _ in GLOBAL_FIXES:
                if ch in full:
                    self.global_counts[ch] += full.count(ch)
        page_state[0] = page

    def text_nodes(self, el, page):
        """(porteur, attribut, page) pour chaque nœud de texte du bloc."""
        out = [(el, "text", page)]
        cur = page

        def walk(node):
            nonlocal cur
            for ch in node:
                pid = ch.get("id") or ""
                if page_of(pid):
                    cur = page_of(pid)
                if lname(ch) != "span" or MARK_CLASS not in classes(ch):
                    out.append((ch, "text", cur))
                    walk(ch)
                out.append((ch, "tail", cur))
        pid = el.get("id") or ""
        if page_of(pid):
            cur = page_of(pid)
            out[0] = (el, "text", cur)
        walk(el)
        return out

    def wrap(self, holder, attr, hits):
        s = getattr(holder, attr) or ""
        pieces, pos = [], 0
        spans = []
        for a, b, cat, detail in hits:
            sp = ET.Element(X("span"))
            sp.set("class", MARK_CLASS)
            sp.set("title", "%s %s" % (CATEGORIES[cat], detail))
            sp.text = s[a:b]
            if spans:
                spans[-1].tail = s[pos:a]
            else:
                first = s[pos:a]
            spans.append(sp)
            pos = b
        spans[-1].tail = s[pos:]
        if attr == "text":
            holder.text = first
            for k, sp in enumerate(spans):
                holder.insert(k, sp)
        else:
            parent = self.parent_of[holder]
            holder.tail = first
            idx = list(parent).index(holder)
            for k, sp in enumerate(spans):
                parent.insert(idx + 1 + k, sp)

    # -- numérotation des chapitres -----------------------------------------
    def check_chapters(self, docs):
        prev, prev_label = None, None
        book = 0
        for doc in docs:
            kids = list(doc.body)
            for idx, el in enumerate(kids):
                n = lname(el)
                if n == "h1":
                    book += 1
                    prev = None
                    continue
                if n != "h2":
                    continue
                label = text_of(el)
                num_label = label
                if not CHAPTER_RE.match(label):
                    nxt = kids[idx + 1] if idx + 1 < len(kids) else None
                    if nxt is not None and "numero" in classes(nxt):
                        num_label = text_of(nxt)
                    else:
                        continue
                num, raw = chapter_number(num_label)
                page = None
                for d in el.iter():
                    if page_of(d.get("id")):
                        page = page_of(d.get("id"))
                if page is None:
                    page = self.last_page_before(doc, el)
                ctx = num_label if num_label == label else "%s — %s" % (num_label, label[:60])
                if num is None:
                    self.add("chapitres", doc, page, ctx, 0, len(num_label), "numéro illisible")
                    continue
                if prev is not None:
                    if num == 1 and prev > 1:
                        pass  # nouveau livre sans titre h1
                    elif num == prev:
                        self.add("chapitres", doc, page, ctx, 0, len(num_label),
                                 "même numéro que le précédent (%s)" % prev_label)
                    elif num < prev:
                        self.add("chapitres", doc, page, ctx, 0, len(num_label),
                                 "numéro inférieur au précédent (%s) : faute d'OCR ?" % prev_label)
                    elif num > prev + 1:
                        missing = list(range(prev + 1, num))
                        txt = ", ".join(str(x) for x in missing[:8]) + ("…" if len(missing) > 8 else "")
                        self.add("chapitres", doc, page, ctx, 0, len(num_label),
                                 "chapitre(s) %s absent(s) avant celui-ci" % txt)
                prev, prev_label = num, num_label

    def last_page_before(self, doc, target):
        page = None
        for d in doc.body.iter():
            if d is target:
                break
            if page_of(d.get("id")):
                page = page_of(d.get("id"))
        return page


# --------------------------------------------------------------------------
# Rapport HTML
# --------------------------------------------------------------------------

REPORT_CSS = """
:root { --encre:#1f2a44; --papier:#f3f5f2; --vert:#2f7a6b; --or:#c99a06; --gris:#5d6673; --trait:#d5dbd6; }
* { box-sizing: border-box; }
body { margin:0; background:var(--papier); color:var(--encre);
       font: 16px/1.55 "Iowan Old Style","Palatino Linotype","Book Antiqua",Palatino,Georgia,serif; }
header { padding:2rem 1.5rem 1rem; max-width:62rem; margin:auto; }
h1 { font-size:2rem; margin:0 0 .3rem; font-weight:600; }
.sous { color:var(--gris); margin:0; }
main { max-width:62rem; margin:auto; padding:0 1.5rem 3rem; }
table.resume { border-collapse:collapse; width:100%; margin:1rem 0 2rem; }
table.resume td { padding:.35rem .5rem; border-bottom:1px solid var(--trait); }
table.resume td.n { text-align:right; font-variant-numeric:tabular-nums; width:5rem; }
details { border-top:2px solid var(--encre); margin:1.5rem 0; padding-top:.4rem; }
summary { cursor:pointer; font-size:1.25rem; font-weight:600; list-style:none; }
summary::before { content:"▸ "; color:var(--vert); }
details[open] summary::before { content:"▾ "; }
.aide { color:var(--gris); margin:.4rem 0 1rem; max-width:48rem; }
ol.cas { padding-left:0; list-style:none; margin:0; }
ol.cas li { display:grid; grid-template-columns: 9.5rem 1fr 5.5rem; gap:.8rem; padding:.45rem 0;
            border-bottom:1px solid var(--trait); align-items:baseline; }
.fic { font-family: ui-monospace, "DejaVu Sans Mono", monospace; font-size:.8rem; color:var(--gris);
       overflow-wrap:anywhere; }
.ctx mark { background:#ffe58a; padding:0 .1em; }
.det { display:block; font-size:.85rem; color:var(--vert); }
a { color:var(--vert); }
.scan { font-size:.85rem; text-align:right; }
code { background:#e4e9e5; padding:.05em .3em; border-radius:3px; }
button.copie { font: .75rem system-ui, sans-serif; margin-left:.5rem; padding:.05rem .45rem; cursor:pointer;
  border:1px solid var(--trait); border-radius:3px; background:#fff; color:var(--vert); }
button.copie:hover { border-color: var(--vert); }
.glob td { padding:.3rem .6rem; border-bottom:1px solid var(--trait); }
@media (max-width:40rem) { ol.cas li { grid-template-columns:1fr; gap:.1rem; } .scan { text-align:left; } }
"""


def build_report(title, rv, docs_count, marked_path, scan_template, max_items):
    e = html.escape
    total = sum(len(v) for v in rv.items.values())
    out = ['<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Relecture — %s</title><style>%s</style></head><body>' % (e(title), REPORT_CSS),
           '<header><h1>Relecture : %s</h1>' % e(title),
           '<p class="sous">%d cas à examiner dans %d fichiers — rapport du %s</p></header><main>'
           % (total, docs_count, datetime.date.today().strftime("%d/%m/%Y"))]
    out.append("<h2>Comment s'en servir</h2><p>Dans Sigil, ouvrez le fichier indiqué dans la "
               "colonne de gauche, puis cherchez l'extrait surligné (Édition › Rechercher, mode "
               "« Normal », étendue « Tous les fichiers HTML »).")
    if scan_template:
        out.append(" Le lien « page » ouvre la page scannée correspondante pour comparer avec "
                   "l'original.")
    if marked_path:
        out.append(" L'EPUB <code>%s</code> contient des marqueurs : recherchez "
                   "<code>a-verifier</code> dans Sigil pour aller de cas en cas, puis retirez-les "
                   "tous avec <code>epub_review.py --unmark</code> avant publication."
                   % e(os.path.basename(marked_path)))
    out.append("</p>")
    out.append('<table class="resume">')
    for cat, label in CATEGORIES.items():
        n = len(rv.items.get(cat, []))
        if n:
            out.append('<tr><td><a href="#%s">%s</a></td><td class="n">%d</td></tr>' % (cat, e(label), n))
    out.append("</table>")

    if any(v for k, v in rv.global_counts.items()):
        out.append("<h2>Remplacements globaux possibles</h2><p class='aide'>À faire en une fois dans "
                   "Sigil (Rechercher/Remplacer, tous les fichiers HTML), après vérification sur "
                   "quelques cas.</p><table class='glob'>")
        for ch, rep, why in GLOBAL_FIXES:
            if rv.global_counts.get(ch):
                out.append("<tr><td><code>%s</code> → <code>%s</code></td><td>%s</td><td>%d fois</td></tr>"
                           % (e(ch), e(rep) or "(rien)", e(why), rv.global_counts[ch]))
        if rv.global_counts.get("__comma"):
            out.append("<tr><td><code>([a-z]),([a-z])</code> → <code>\\1, \\2</code></td><td>virgule, "
                       "point-virgule ou deux-points collés au mot suivant (mode Regex ; même chose "
                       "pour <code>;</code> et <code>:</code>)</td><td>%d fois</td></tr>"
                       % rv.global_counts["__comma"])
        out.append("</table>")

    for cat, label in CATEGORIES.items():
        lst = rv.items.get(cat, [])
        if not lst:
            continue
        out.append('<details id="%s"%s><summary>%s (%d)</summary><p class="aide">%s</p><ol class="cas">'
                   % (cat, " open" if cat == "chapitres" else "", e(label), len(lst), e(HELP[cat])))
        for it in lst[:max_items]:
            scan = ('<a href="%s" target="_blank" rel="noopener">page %s</a>' % (e(it["url"]), e(it["page"]))
                    if it["url"] else (e(it["page"]) if it["page"] else ""))
            out.append('<li><span class="fic">%s</span><span class="ctx">%s<mark>%s</mark>%s'
                       '<span class="det">%s <button class="copie" type="button" data-t="%s" '
                       'title="Copier l\'extrait pour la recherche de Sigil">copier</button></span></span>'
                       '<span class="scan">%s</span></li>'
                       % (e(it["file"]), e(it["before"]), e(it["hit"]), e(it["after"]),
                          e(it["detail"]), html.escape(it["hit"].strip(), quote=True), scan))
        if len(lst) > max_items:
            out.append("<li><span></span><span class='aide'>… et %d autres (voir --max-items)</span>"
                       "<span></span></li>" % (len(lst) - max_items))
        out.append("</ol></details>")
    out.append("""</main><script>
document.addEventListener("click", function (ev) {
  var b = ev.target.closest("button.copie"); if (!b) return;
  var t = b.getAttribute("data-t");
  function done() { var o = b.textContent; b.textContent = "copié"; setTimeout(function () { b.textContent = o; }, 1200); }
  if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(t).then(done); return; }
  var ta = document.createElement("textarea"); ta.value = t; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch (e) {} ta.remove();
});
</script></body></html>""")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Marqueurs : pose et retrait
# --------------------------------------------------------------------------

def unmark_doc(doc):
    n = 0
    for parent in list(doc.body.iter()):
        for ch in list(parent):
            if lname(ch) == "span" and MARK_CLASS in classes(ch) and len(ch) == 0:
                i = list(parent).index(ch)
                txt = (ch.text or "") + (ch.tail or "")
                parent.remove(ch)
                if i == 0:
                    parent.text = (parent.text or "") + txt
                else:
                    parent[i - 1].tail = (parent[i - 1].tail or "") + txt
                n += 1
        if MARK_CLASS in classes(parent):
            rest = classes(parent) - {MARK_CLASS}
            if rest:
                parent.set("class", " ".join(sorted(rest)))
            else:
                del parent.attrib["class"]
            n += 1
    return n


def update_css(css_text, add):
    css_text = re.sub(re.escape(CSS_BEGIN) + r".*?" + re.escape(CSS_END) + r"\n?", "", css_text, flags=re.S)
    return css_text.rstrip() + "\n\n" + CSS_RULES if add else css_text.rstrip() + "\n"


def write_epub(src, out_path, new_data):
    fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
    os.close(fd)
    try:
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w") as zout:
            for info in sorted(zin.infolist(), key=lambda i: i.filename != "mimetype"):
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


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Prépare la relecture d'un EPUB issu d'OCR.")
    ap.add_argument("epub")
    ap.add_argument("--report", help="rapport HTML (défaut : <livre>-relecture.html)")
    ap.add_argument("--mark", metavar="EPUB", help="écrire une copie marquée pour Sigil")
    ap.add_argument("--unmark", action="store_true", help="retirer tous les marqueurs")
    ap.add_argument("--fix-doctype", action="store_true",
                    help="seulement mettre les DOCTYPE en XHTML 1.1 (EPUB 2), marqueurs conservés")
    ap.add_argument("-o", "--output", help="avec --unmark : EPUB de sortie (défaut : en place)")
    ap.add_argument("--dict-out", metavar="FICHIER", help="liste des mots du livre pour Sigil")
    ap.add_argument("--scan-url", help="modèle d'URL des pages scannées, avec {page} "
                    "(défaut : Google Books si l'identifiant s'y prête)")
    ap.add_argument("--wordlist", metavar="FICHIER",
                    help="liste de mots de référence (un par ligne, ex. /usr/share/dict/french ou "
                         "un .dic Hunspell) : détection des mots collés plus fine")
    ap.add_argument("--min-glued", type=int, default=11,
                    help="longueur minimale d'un mot pour le soupçonner d'être collé (défaut 11)")
    ap.add_argument("--longs-tsv", metavar="FICHIER",
                    help="liste d'epub_longs.py : les formes laissées telles quelles (appliquer=0) "
                         "sont signalées une par une")
    ap.add_argument("--oi-tsv", metavar="FICHIER",
                    help="liste d'epub_modernise.py --mode oi : formes laissées au choix signalées")
    ap.add_argument("--max-items", type=int, default=400, help="cas affichés par catégorie")
    ap.add_argument("--css-path", default="Styles/livre.css")
    opts = ap.parse_args()

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        names = set(zin.namelist())
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf, _, _ = decode_text(zin.read(opf_path))
        _ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf)
        EPUB2[0] = not (_ver and _ver.group(1).startswith("3"))
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if get_attr(m.group(0), "href"):
                items[get_attr(m.group(0), "id")] = (resolve(opf_path, get_attr(m.group(0), "href")),
                                                     get_attr(m.group(0), "properties") or "")
        spine = [items[i][0] for i in re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf)
                 if i in items and "nav" not in items[i][1].split()]
        title_m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.S)
        title = html.unescape(title_m.group(1).strip()) if title_m else os.path.basename(src)
        ident = re.findall(r"<dc:identifier[^>]*>\s*([^<\s]+)\s*<", opf)
        docs = []
        for p in spine:
            if p in names:
                try:
                    d = Doc(p, *decode_text(zin.read(p)))
                except ET.ParseError as err:
                    print("Avertissement : %s ignoré (%s)" % (p, err), file=sys.stderr)
                    continue
                if d.body is not None:
                    docs.append(d)
        css_path = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), opts.css_path))
        css_text = zin.read(css_path).decode("utf-8") if css_path in names else None

    # --- DOCTYPE seuls ---
    if opts.fix_doctype:
        new_data = {d.path: d.serialize() for d in docs if fix_doctype(d.prefix) != d.prefix}
        out = opts.output or src
        if new_data:
            write_epub(src, out, new_data)
        print("DOCTYPE mis en XHTML 1.1 : %d fichiers" % len(new_data))
        if new_data:
            print("EPUB écrit : %s" % out)
        return

    # --- retrait des marqueurs ---
    if opts.unmark:
        new_data, n = {}, 0
        for d in docs:
            before = compact("".join(d.body.itertext()))
            k = unmark_doc(d)
            if k or fix_doctype(d.prefix) != d.prefix:
                assert compact("".join(d.body.itertext())) == before
                new_data[d.path] = d.serialize()
                n += k
        if css_text is not None and CSS_BEGIN in css_text:
            new_data[css_path] = update_css(css_text, False).encode("utf-8")
        out = opts.output or src
        write_epub(src, out, new_data)
        print("Marqueurs retirés : %d" % n)
        print("EPUB écrit : %s" % out)
        return

    # --- vocabulaire ---
    vocab = collections.Counter()
    for d in docs:
        for w in WORD_RE.findall("".join(d.body.itertext())):
            vocab[w.lower()] += 1

    scan = opts.scan_url
    m = re.search(r"""<meta\s+name=["']prescel:scan-url["']\s+content=["']([^"']+)["']""", opf)
    if scan is None and m:
        scan = html.unescape(m.group(1))       # posé par pdf_to_epub.py (Gallica…)
    if scan is None:
        google = next((i for i in ident if re.fullmatch(r"[A-Za-z0-9_-]{12}", i)), None)
        has_gbs = any((e.get("id") or "").startswith("GBS.") for d in docs for e in d.body.iter())
        if google and has_gbs:
            scan = "https://books.google.com/books?id=%s&pg={page}" % google

    wordlist = None
    if opts.wordlist:
        with open(opts.wordlist, encoding="utf-8", errors="replace") as f:
            wordlist = {line.split("/")[0].strip().lower() for line in f if line.strip()}
    longs = {}
    if opts.longs_tsv and os.path.exists(opts.longs_tsv):
        import csv
        with open(opts.longs_tsv, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("forme_lue") and (r.get("appliquer") or "0").strip() != "1":
                    longs[r["forme_lue"].lower()] = r.get("correction", "")
    oi = {}
    if opts.oi_tsv and os.path.exists(opts.oi_tsv):
        import csv
        with open(opts.oi_tsv, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("forme_lue") and (r.get("appliquer") or "0").strip() != "1":
                    oi[r["forme_lue"].lower()] = r.get("correction", "")
    rv = Reviewer(vocab, scan, wordlist, opts.min_glued, longs, oi)
    page_state = [None]
    mark = bool(opts.mark)
    before = {}
    for d in docs:
        before[d.path] = compact("".join(d.body.itertext()))
        rv.parent_of = {c: p for p in d.body.iter() for c in p}
        rv.review(d, page_state, mark)
    rv.check_chapters(docs)

    report = opts.report or re.sub(r"\.epub$", "", src, flags=re.I) + "-relecture.html"
    with open(report, "w", encoding="utf-8") as f:
        f.write(build_report(title, rv, len(docs), opts.mark, scan, opts.max_items))

    total = 0
    for cat, label in CATEGORIES.items():
        n = len(rv.items.get(cat, []))
        total += n
        if n:
            print("  %-36s %5d" % (label, n))
    for ch, rep, why in GLOBAL_FIXES:
        if rv.global_counts.get(ch):
            print("  remplacement global « %s » → « %s » : %d fois" % (ch, rep, rv.global_counts[ch]))
    if rv.global_counts.get("__comma"):
        print("  ponctuation collée (, ; :) : %d fois — remplacement global proposé"
              % rv.global_counts["__comma"])
    print("Cas à examiner : %d" % total)
    print("Rapport : %s" % report)
    if scan:
        print("Liens vers les pages scannées : %s" % scan.replace("{page}", "…"))

    if opts.dict_out:
        words = sorted(w for w, c in vocab.items() if c >= 3 and len(w) > 1)
        with open(opts.dict_out, "w", encoding="utf-8") as f:
            f.write("\n".join(words) + "\n")
        print("Dictionnaire : %s (%d mots)" % (opts.dict_out, len(words)))

    if mark:
        new_data = {}
        for d in docs:
            if compact("".join(d.body.itertext())) != before[d.path]:
                sys.exit("ARRÊT : le marquage a modifié le texte de %s" % d.path)
            new_data[d.path] = d.serialize()
        if css_text is not None:
            new_data[css_path] = update_css(css_text, True).encode("utf-8")
        write_epub(src, opts.mark, new_data)
        print("EPUB marqué : %s (rechercher « a-verifier » dans Sigil)" % opts.mark)


if __name__ == "__main__":
    main()
