#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_structure.py — Deuxième passe après epub_simplify.py : redonne une
structure de livre à un EPUB issu d'OCR, sans perdre de texte.

Par défaut (aucun caractère du texte n'est modifié) :
  * « CHAPITRE II », « Chap. XII. »… deviennent des <h2 id="chap-…"> ;
    « LIVRE SEPTIÈME »… des <h1> ; le paragraphe qui suit un titre de
    chapitre (le sommaire) reçoit la classe « sommaire » ;
  * les notes de bas de page (« 1. Saluer en ôtant le bonnet ») reçoivent
    la classe « note » ;
  * table des matières (toc.ncx, et nav si EPUB 3) reconstruite à partir des
    titres : « Chapitre II — Dissentiments entre le maréchal… » ;
  * page-map Adobe (non standard, refusée par epubcheck) convertie en
    <pageList> du toc.ncx : les numéros de page du livre papier restent ;
  * corrections de validité : <img> vers une image absente de l'EPUB
    supprimée, contenu « en vrac » dans <body> (img, texte) mis dans un bloc ;
  * feuille livre.css complétée (retrait de première ligne, sommaire, note).

Options qui recomposent le texte (vérifiées, et journalisées) :
  --merge-pages     recolle les paragraphes coupés par un changement de page
                    (« … ayant combattu Montgom » + « mery, il n'y… ») ; le
                    numéro de page (ancre de la page-map) est conservé à
                    l'endroit de la jonction ; manchettes, notes et images
                    intercalées sont reportées après le paragraphe ;
  --drop-furniture  supprime les restes de mise en page sans mots : folios
                    (« 16 », « 172 »), signatures (« IV-1 »), signes isolés
                    (« , », « + ») ; la liste de ce qui est retiré est affichée.

Vérification : le texte final doit contenir exactement les mêmes caractères
que l'original (espaces exclus), moins les tirets de césure recollés et les
éléments retirés par --drop-furniture ; sinon rien n'est écrit.

Usage :
  python3 epub_structure.py livre.epub -o livre-structure.epub --merge-pages --drop-furniture
  python3 epub_split_h1.py livre-structure.epub --tag h2      # un fichier par chapitre
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
EPUB_NS = "http://www.idpf.org/2007/ops"
for _p, _u in (("", XHTML_NS), ("svg", "http://www.w3.org/2000/svg"),
               ("xlink", "http://www.w3.org/1999/xlink"), ("epub", EPUB_NS),
               ("m", "http://www.w3.org/1998/Math/MathML")):
    ET.register_namespace(_p, _u)

BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "table",
         "blockquote", "pre", "hr", "address"}
HEAD_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
MEDIA = {"img", "svg", "image", "object", "video", "audio", "math", "iframe"}
LOWER = "a-zà-öø-ÿœæ"
ROMAN = r"[IVXLCDMivxl1]+(?:\s?[IVXLCDMivxl1]+)*"
ORDINAL = r"[A-Za-zÀ-ÿ]{4,14}"   # premier, second, tiers, quatriesme (et ses fautes d'OCR)

CHAPTER_RE = r"^(?:CHAPITRE|Chapitre|CHAP|Chap)\b\s*\.?\s*(?:" + ROMAN + \
    r"|" + ORDINAL + r"|[Ii]er|\d+)[\s.]*$"
BOOK_RE = (r"^(?:(?:LIVRE|Livre|PARTIE|Partie)\s+[\wÀ-ÿ]+\s*\.?"
           r"|(?:LE\s+|Le\s+)?(?:PREMIER|SECOND|TIERS|TROISI[EÈ]ME|QUATRI[EÈ]ME|CINQUI[EÈ]ME"
           r"|[Pp]remier|[Ss]econd|[Tt]iers|[Tt]roisi[eè]me|[Qq]uatri[eè]me|[Cc]inqui[eè]me)"
           r"\s+(?:LI[UV]RE|li[uv]re)\b[^.]{0,60})$")
TABLE_RE = r"^(?:TABLE|Table)(?:\s+(?:DES\s+MATI[ÈE]RES|des\s+mati[èe]res|ANALYTIQUE))?\s*\.?$"
NOTE_RE = re.compile(r"^\(?\d{1,3}[.)]\s+\S|^[*†‡]\s*\S")
FURNITURE_RE = re.compile(r"^(?:[^\w]|[\d_])*$|^[IVXLC]{1,5}[\s.\-]*\d{0,3}\s*[.,]?$")
TERMINAL = re.compile(r"[.!?:»)\]…]\s*$|\.\.\s*$")

CSS_MARK_BEGIN = "/* --- epub_structure.py --- */"
CSS_MARK_END = "/* --- fin epub_structure.py --- */"
CSS_ADDITIONS = CSS_MARK_BEGIN + """
p { text-indent: 1.2em; }
p.marge, p.note, p.centre, p.droite, p.sommaire, p.numero { text-indent: 0; }
.numero { text-align: center; font-variant: small-caps; margin: 0 0 1em 0; }
h1 { font-size: 1.6em; margin: 2em 0 1em 0; page-break-before: always; }
h2 { font-size: 1.3em; margin: 1.5em 0 0.5em 0; page-break-before: always; }
.sommaire { font-style: italic; font-size: 90%; margin: 0 2em 1.5em 2em; text-align: justify; }
.note { font-size: 80%; margin: 0.3em 0 0.3em 1em; }
""" + CSS_MARK_END + "\n"


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def X(tag):
    return "{%s}%s" % (XHTML_NS, tag)


def resolve(base, href):
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(href)))


def rel_href(frm, to):
    return quote(posixpath.relpath(to, posixpath.dirname(frm) or "."), safe="/")


def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8", data[:3]
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    enc = m.group(1).decode("ascii") if m else "utf-8"
    return data.decode(enc), enc, b""


def get_attr(tag, name):
    m = re.search(r"""\s%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % re.escape(name), tag, re.I)
    return None if not m else (m.group(1) if m.group(1) is not None else m.group(2))


def text_of(el):
    return " ".join("".join(el.itertext()).split())


def compact(s):
    return "".join((s or "").split())


def replace_named_entities(text):
    def rep(m):
        if m.group(1) in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        cp = html.entities.name2codepoint.get(m.group(1))
        return "&#%d;" % cp if cp else m.group(0)
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", rep, text)


def add_text_before(parent, index, text):
    if not text:
        return
    if index == 0:
        parent.text = (parent.text or "") + text
    else:
        prev = parent[index - 1]
        prev.tail = (prev.tail or "") + text


def remove_keep_tail(parent, child):
    i = list(parent).index(child)
    tail = child.tail
    parent.remove(child)
    add_text_before(parent, i, tail)


def is_bare_anchor(el):
    return (lname(el) == "a" and el.get("id") and not el.get("href")
            and len(el) == 0 and not (el.text or "").strip())


def anchor(id_):
    a = ET.Element(X("a"))
    a.set("id", id_)
    return a


def classes(el):
    return set((el.get("class") or "").split())


def is_normal_p(el):
    return lname(el) == "p" and not (classes(el) & {"marge", "note", "centre", "droite",
                                                     "sommaire", "image"})


def get_end(el):
    """(get, set) du dernier nœud texte d'un élément."""
    if len(el):
        last = el[-1]
        return (lambda: last.tail or "", lambda v: setattr(last, "tail", v))
    return (lambda: el.text or "", lambda v: setattr(el, "text", v))


def append_content(dst, src, joiner_text):
    """Ajoute le contenu de src (texte + enfants) à la fin de dst."""
    get, put = get_end(dst)
    put(joiner_text(get()))
    get, put = get_end(dst)
    put(get() + (src.text or ""))
    for ch in list(src):
        src.remove(ch)
        dst.append(ch)


def give_id_to_next_block(parent, index, id_):
    """Rattache une ancre au bloc textuel suivant (ou précédent)."""
    kids = list(parent)
    for el in kids[index:]:
        if lname(el) in ("p",) or lname(el) in HEAD_TAGS:
            if not el.get("id"):
                el.set("id", id_)
            else:
                a = anchor(id_)
                a.tail, el.text = el.text, None
                el.insert(0, a)
            return True
    for el in reversed(kids[:index]):
        if lname(el) in ("p",) or lname(el) in HEAD_TAGS:
            el.append(anchor(id_))
            return True
    return False


# --------------------------------------------------------------------------
# Traitement d'un document
# --------------------------------------------------------------------------

class Doc:
    def __init__(self, path, text, enc, bom):
        self.path, self.enc, self.bom = path, enc, bom
        m = re.search(r"<(?:[\w-]+:)?html\b", text)
        self.prefix = text[:m.start()] if m else '<?xml version="1.0" encoding="utf-8"?>\n'
        self.root = ET.fromstring(replace_named_entities(text).encode("utf-8"))
        self.head = self.root.find(X("head"))
        self.body = self.root.find(X("body"))

    def serialize(self):
        out = ET.tostring(self.root, encoding="unicode")
        return self.bom + (self.prefix.rstrip() + "\n" + out + "\n").encode(self.enc, "xmlcharrefreplace")


class Structurer:
    def __init__(self, opts, vocab, names, stats, log):
        self.opts, self.vocab, self.names = opts, vocab, names
        self.st, self.log = stats, log
        self.chapter_re = re.compile(opts.chapter_regex)
        self.book_re = re.compile(opts.book_regex)
        self.table_re = re.compile(opts.table_regex)
        self.in_table = False
        self.removed = collections.Counter()
        self.hyphens = 0
        self.heading_seq = 0
        self.used_ids = set()

    # -- validité ----------------------------------------------------------
    def fix_missing_images(self, doc):
        for parent in list(doc.body.iter()):
            for img in [c for c in parent if lname(c) == "img"]:
                src = img.get("src")
                if src and not src.startswith(("http:", "https:", "data:")) \
                        and resolve(doc.path, src) not in self.names:
                    remove_keep_tail(parent, img)
                    self.st["images absentes retirées"] += 1
                    self.log.append("  %s : <img> vers %s (fichier absent) retirée"
                                    % (doc.path, src))
        # div devenues vides
        for parent in list(doc.body.iter()):
            for d in [c for c in parent if lname(c) == "div"]:
                if not text_of(d) and not any(lname(x) in MEDIA for x in d.iter()):
                    ids = [x.get("id") for x in d.iter() if x.get("id")]
                    i = list(parent).index(d)
                    remove_keep_tail(parent, d)
                    for k, id_ in enumerate(ids):
                        parent.insert(i + k, anchor(id_))

    def unwrap_wrappers(self, doc):
        """Une <div> qui enveloppe tout le texte (souvent une balise fermée trop
        tard après une retouche) empêche de voir les paragraphes : on la retire."""
        body = doc.body
        for d in [c for c in body if lname(c) == "div"]:
            blocks = [c for c in d if lname(c) in BLOCK]
            if len(blocks) >= 10 and not d.get("id"):
                i = list(body).index(d)
                kids, text, tail = list(d), d.text, d.tail
                body.remove(d)
                add_text_before(body, i, text)
                for k, kid in enumerate(kids):
                    body.insert(i + k, kid)
                if kids:
                    kids[-1].tail = (kids[-1].tail or "") + (tail or "")
                self.st["div englobantes retirées"] += 1
                self.log.append("  %s : <div%s> englobant %d blocs retirée"
                                % (doc.path, ' class="%s"' % d.get("class") if d.get("class") else "",
                                   len(blocks)))

    def wrap_loose(self, doc):
        body = doc.body
        if (body.text or "").strip():
            p = ET.Element(X("p"))
            p.text, body.text = body.text.strip(), "\n"
            body.insert(0, p)
            self.st["contenu en vrac encadré"] += 1
        i = 0
        while i < len(body):
            ch = body[i]
            n = lname(ch)
            if n in BLOCK:
                if (ch.tail or "").strip():
                    p = ET.Element(X("p"))
                    p.text, ch.tail = ch.tail.strip(), "\n"
                    body.insert(i + 1, p)
                    self.st["contenu en vrac encadré"] += 1
                i += 1
                continue
            if is_bare_anchor(ch) and not (ch.tail or "").strip():
                id_ = ch.get("id")
                body.remove(ch)
                if not give_id_to_next_block(body, i, id_):
                    d = ET.Element(X("div"))
                    d.append(anchor(id_))
                    body.insert(i, d)
                    i += 1
                continue
            wrapper = ET.Element(X("div"))
            if any(lname(x) in MEDIA for x in ch.iter()):
                wrapper.set("class", "image")
            body.remove(ch)
            wrapper.append(ch)
            wrapper.tail = "\n"
            body.insert(i, wrapper)
            self.st["contenu en vrac encadré"] += 1
            i += 1

    # -- titres, sommaires, notes -----------------------------------------
    def mark_structure(self, doc):
        for el in doc.body:
            if el.get("class") == "sommaire":
                del el.attrib["class"]
        kids = list(doc.body)
        for idx, el in enumerate(kids):
            if lname(el) not in ("p",) and lname(el) not in HEAD_TAGS:
                continue
            if "numero" in classes(el):
                continue          # numéro déjà rattaché à son titre (relance)
            t = text_of(el)
            level = None
            if self.table_re.match(t) and not self.in_table:
                level, self.in_table = "h2", True
            elif self.in_table:
                pass  # table des matières imprimée : pas de titres ici
            elif self.book_re.match(t) and not (classes(el) & {"marge", "note"}):
                level = "h1"
            elif self.chapter_re.match(t):
                level = "h2"
            if level == "h2" and self.opts.title_before and not self.table_re.match(t):
                title = self.title_before(kids, idx)
                if title is not None:
                    # le titre devient le h2, la ligne « Chap. XX. » un simple numéro
                    el.tag = X("p")
                    el.set("class", "numero")
                    title.tag = X("h2")
                    if "class" in title.attrib:
                        del title.attrib["class"]
                    if not title.get("id"):
                        title.set("id", self.new_id())
                    self.st["titres h2 (titre avant le numéro)"] += 1
                    continue
            if level:
                if lname(el) != level:
                    el.tag = X(level)
                    if "class" in el.attrib:
                        del el.attrib["class"]
                    self.st["titres " + level] += 1
                if not el.get("id"):
                    el.set("id", self.new_id())
                if level == "h2" and not self.table_re.match(t):
                    for nxt in kids[idx + 1:idx + 4]:
                        if is_normal_p(nxt) and len(text_of(nxt)) < self.opts.summary_max and \
                                (" - " in text_of(nxt) or len(text_of(nxt)) <= 160) and \
                                re.match(r"[A-ZÀ-Þ]", text_of(nxt)) and \
                                text_of(nxt).rstrip().endswith(".") and len(text_of(nxt)) >= 15:
                            nxt.set("class", "sommaire")
                            self.st["sommaires"] += 1
                            break
                        if lname(nxt) not in ("div",) and not self.is_furniture(nxt):
                            break
            elif "marge" in classes(el) and NOTE_RE.match(t):
                el.set("class", "note")
                self.st["notes"] += 1

    def new_id(self):
        while True:
            self.heading_seq += 1
            cand = "titre-%d" % self.heading_seq
            if cand not in self.used_ids:
                self.used_ids.add(cand)
                return cand

    def title_before(self, kids, idx):
        """Paragraphe en capitales juste avant « Chapitre N » (ex. Belon)."""
        for prv in reversed(kids[:idx]):
            if lname(prv) == "div" or is_bare_anchor(prv) or self.is_furniture(prv) or \
                    "marge" in classes(prv) or "note" in classes(prv):
                continue
            if not is_normal_p(prv) and "centre" not in classes(prv):
                return None
            t = text_of(prv)
            letters = [c for c in t if c.isalpha()][:12]
            if 8 <= len(t) <= 300 and len(letters) >= 6 and \
                    sum(c.isupper() for c in letters) / len(letters) >= 0.8:
                return prv
            return None
        return None

    # -- restes de mise en page -------------------------------------------
    def is_furniture(self, el):
        if lname(el) != "p":
            return False
        t = text_of(el)
        if not t:
            return False
        if len(t) <= 8 and FURNITURE_RE.match(t):
            return True
        return self.is_running_head(t)

    def is_running_head(self, t):
        """Titre courant : « MONTLUC REMPLACÉ EN GUYENNE 171 »."""
        if len(t) > 70 or not re.search(r"^\d{1,4}\b|\b\d{1,4}$", t):
            return False
        if self.chapter_re.match(t) or self.book_re.match(t):
            return False
        letters = [c for c in t if c.isalpha()]
        return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.8

    def drop_furniture(self, doc):
        body = doc.body
        i = 0
        while i < len(body):
            el = body[i]
            if self.is_furniture(el) and not any(lname(x) in MEDIA for x in el.iter()):
                ids = [x.get("id") for x in el.iter() if x.get("id")]
                self.removed[text_of(el)] += 1
                for c in text_of(el):
                    if not c.isspace():
                        self.removed_chars[c] += 1
                remove_keep_tail(body, el)
                for id_ in ids:
                    give_id_to_next_block(body, i, id_)
                self.st["restes de mise en page"] += 1
                continue
            i += 1

    # -- paragraphes coupés par les pages ---------------------------------
    def joiner(self, left, right):
        """Retourne (texte de gauche modifié, texte de droite modifié)."""
        lw = re.search(r"([\w'’-]+)\s*$", left)
        rw = re.match(r"\s*([\w'’-]+)", right)
        lword = lw.group(1) if lw else ""
        rword = rw.group(1) if rw else ""
        if left.rstrip().endswith("-") and lword.strip("-") and rword:
            base = lword.rstrip("-")
            hyph = (base + "-" + rword).lower()
            glued = (base + rword).lower()
            if self.vocab.get(hyph, 0) > self.vocab.get(glued, 0):
                return left.rstrip(), right.lstrip(), "trait conservé"
            self.hyphens += 1
            return left.rstrip()[:-1], right.lstrip(), "césure"
        lword = re.sub(r"^\w+['’]", "", lword)   # « d'en|tre » → « en|tre »
        if lword and rword and lword[-1:].isalpha() and rword[:1].isalpha():
            v = self.vocab.get
            glued = (lword + rword).lower()
            hyph = (lword + "-" + rword).lower()
            l_rare, r_rare = v(lword.lower(), 0) <= 1, v(rword.lower(), 0) <= 1
            # Mot composé connu du livre : « Peut|être » → « Peut-être »
            if v(hyph, 0) >= 1 and v(hyph, 0) >= v(glued, 0):
                self.hyphens -= 1          # un tiret est ajouté
                return left.rstrip() + "-", right.lstrip(), "trait ajouté"
            # Mot connu dont un des morceaux n'existe pas seul : « de|meurer »
            if v(glued, 0) >= 1 and (l_rare or r_rare):
                return left.rstrip(), right.lstrip(), "mot recollé"
            # Mot plus fréquent que ses morceaux : « Mon|sieur »
            if v(glued, 0) >= 2 and v(glued, 0) >= min(v(lword.lower(), 0), v(rword.lower(), 0)):
                return left.rstrip(), right.lstrip(), "mot recollé"
            # Deux morceaux inconnus : « sui|vissions »
            if l_rare and r_rare and len(lword) > 1 and len(rword) > 1:
                return left.rstrip(), right.lstrip(), "mot recollé"
        return left.rstrip() + " ", right.lstrip(), "espace"

    def merge_pages(self, doc):
        body = doc.body
        i = 0
        while i < len(body):
            p = body[i]
            if not is_normal_p(p) or self.is_furniture(p):
                i += 1
                continue
            t = text_of(p)
            if not t or (TERMINAL.search(t) and not t.endswith("-")):
                i += 1
                continue
            # cherche la suite en sautant manchettes, notes, images, folios
            j, between = i + 1, []
            q = None
            while j < len(body) and j - i <= 10:
                el = body[j]
                n = lname(el)
                if is_normal_p(el) and text_of(el) and not self.is_furniture(el):
                    q = el
                    break
                if n == "div" or (n == "p" and (classes(el) & {"marge", "note"} or
                                                self.is_furniture(el) or not text_of(el))) \
                        or is_bare_anchor(el):
                    between.append(el)
                    j += 1
                    continue
                break
            if q is None:
                i += 1
                continue
            qt = text_of(q)
            if not (re.match(r"[%s]" % LOWER, qt) or t.endswith("-")):
                i += 1
                continue
            # jonction
            left_get, left_put = get_end(p)
            # premier texte de q (après une éventuelle ancre de page)
            holder, attr = q, "text"
            if not (q.text or "").strip():
                for ch in q:
                    if not is_bare_anchor(ch):
                        break
                    holder, attr = ch, "tail"
                    if (ch.tail or "").strip():
                        break
            new_left, new_right, kind = self.joiner(left_get(), getattr(holder, attr) or "")
            left_put(new_left)
            setattr(holder, attr, new_right)
            ids = [q.get("id")] if q.get("id") else []
            ids += [x.get("id") for x in between if is_bare_anchor(x)]
            for id_ in ids:
                p.append(anchor(id_))
            append_content(p, q, lambda s: s)
            body.remove(q)
            for x in between:
                if is_bare_anchor(x):
                    body.remove(x)
            # les éléments intercalés restent après le paragraphe fusionné
            self.st["paragraphes recollés"] += 1
            self.st["  dont " + kind] += 1
            if self.opts.verbose:
                self.log.append("  %s : …%s|%s…  (%s)" % (doc.path, t[-25:], qt[:25], kind))
            # on retente avec le même paragraphe (fragment suivant éventuel)

    # -- pipeline -----------------------------------------------------------
    def run(self, doc):
        self.removed_chars = collections.Counter()
        before = compact("".join(doc.body.itertext()))
        self.hyphens = 0
        self.fix_missing_images(doc)
        self.unwrap_wrappers(doc)
        self.wrap_loose(doc)
        if self.opts.drop_furniture:
            self.drop_furniture(doc)
        self.mark_structure(doc)
        if self.opts.merge_pages:
            self.merge_pages(doc)
        after = compact("".join(doc.body.itertext()))
        expected = collections.Counter(before) - self.removed_chars
        expected["-"] -= self.hyphens
        expected = +expected
        if expected != collections.Counter(after):
            diff = (expected - collections.Counter(after)) + (collections.Counter(after) - expected)
            raise RuntimeError("Texte modifié dans %s (écart : %s)" % (doc.path, dict(diff)))
        layout(doc.body)


def layout(body):
    kids = list(body)
    if not kids or (body.text or "").strip() or any((k.tail or "").strip() for k in kids):
        return
    body.text = "\n  "
    for k in kids:
        k.tail = "\n  "
    kids[-1].tail = "\n"


# --------------------------------------------------------------------------
# Table des matières
# --------------------------------------------------------------------------

def clean_number(label):
    """« Chapitre. X V. » → « Chapitre XV » ; « Chap.v11 » → « Chap. VII »."""
    m = re.match(r"^(CHAPITRE|Chapitre|CHAP|Chap)\s*\.?\s*(.*?)[\s.]*$", label)
    if not m:
        return label
    word, num = m.group(1), m.group(2)
    compact_num = num.replace(" ", "")
    if re.fullmatch(r"[IVXLCDMivxl1]+", compact_num):
        num = compact_num.upper().replace("1", "I")
    word = {"CHAPITRE": "Chapitre", "CHAP": "Chap."}.get(word, "Chap." if word == "Chap" else word)
    return "%s %s" % (word, num)


def toc_entries(docs_in_order, chapter_re, book_re, table_re, used_ids=frozenset()):
    """Titres retenus : h1 (tous), h2 de chapitre. Niveau 1 = livre/partie."""
    entries, seq = [], 0
    for doc in docs_in_order:
        kids = list(doc.body)
        for idx, el in enumerate(kids):
            n = lname(el)
            label = text_of(el)
            numbered = any("numero" in classes(x) for x in kids[idx + 1:idx + 2])
            if not label or n not in ("h1", "h2") or \
                    (n == "h2" and not (chapter_re.match(label) or table_re.match(label) or numbered)):
                continue
            if not el.get("id"):
                seq += 1
                while "toc-%d" % seq in used_ids:
                    seq += 1
                el.set("id", "toc-%d" % seq)
            label = clean_number(label)
            label = re.sub(r"^(CHAPITRE|LIVRE|PARTIE)\b", lambda m: m.group(1).capitalize(), label)
            if label.isupper():
                label = label.capitalize()          # « TABLE » → « Table »
            for nxt in kids[idx + 1:idx + 4]:
                if "numero" in classes(nxt):
                    words = [w.lower() if w.isupper() and len(w) > 1 else w for w in label.split()]
                    label = " ".join(words)
                    label = clean_number(text_of(nxt)) + " — " + label[:1].upper() + label[1:]
                    if len(label) > 110:
                        label = label[:110].rsplit(" ", 1)[0] + "…"
                    break
                if "sommaire" in classes(nxt):
                    s = text_of(nxt)
                    s = re.split(r"\s+-\s+|\.\s", s, maxsplit=1)[0].rstrip(".")
                    if len(s) > 80:
                        s = s[:80].rsplit(" ", 1)[0] + "…"
                    label += " — " + s
                    break
            entries.append((1 if (n == "h1" and book_re.match(text_of(el))) else 2,
                            label, doc.path, el.get("id")))
    return entries


def build_ncx(ncx_text, ncx_path, entries, first_point):
    has_h1 = any(lv == 1 for lv, _, _, _ in entries)
    points, order = [], [0]

    def point(label, src, children, ind):
        order[0] += 1
        pid = "nav-%d" % order[0]
        s = ('%s<navPoint id="%s" playOrder="%d">\n%s  <navLabel><text>%s</text></navLabel>\n'
             '%s  <content src="%s"/>\n' % (ind, pid, order[0], ind, html.escape(label, quote=False),
                                           ind, html.escape(src)))
        s += "".join(children)
        return s + "%s</navPoint>\n" % ind

    out = []
    if first_point:
        label, src = first_point
        out.append(point(label, src, [], "    "))
    i = 0
    while i < len(entries):
        lv, label, path, id_ = entries[i]
        src = rel_href(ncx_path, path) + "#" + id_
        if has_h1 and lv == 1:
            order_before = order[0]
            # enfants : entrées de niveau 2 jusqu'au prochain niveau 1
            j, kids_raw = i + 1, []
            while j < len(entries) and entries[j][0] == 2:
                kids_raw.append(entries[j])
                j += 1
            order[0] += 1
            me = order[0]
            kids = []
            for _, kl, kp, kid in kids_raw:
                kids.append(point(kl, rel_href(ncx_path, kp) + "#" + kid, [], "      "))
            out.append('    <navPoint id="nav-%d" playOrder="%d">\n      <navLabel><text>%s</text></navLabel>\n'
                       '      <content src="%s"/>\n%s    </navPoint>\n'
                       % (me, me, html.escape(label, quote=False), html.escape(src), "".join(kids)))
            i = j
        else:
            out.append(point(label, src, [], "    "))
            i += 1
    depth = 2 if has_h1 else 1
    new = re.sub(r"(<navMap\b[^>]*>).*?(</navMap>)",
                 lambda m: m.group(1) + "\n" + "".join(out) + "  " + m.group(2), ncx_text, flags=re.S)
    new = re.sub(r"""(<meta\s+name=["']dtb:depth["']\s+content=["'])\d+""",
                 lambda m: m.group(1) + str(depth), new)
    return new


def build_nav(doc, entries):
    """Remplace la liste de <nav epub:type="toc"> (EPUB 3)."""
    for nav in doc.body.iter(X("nav")):
        if nav.get("{%s}type" % EPUB_NS) != "toc":
            continue
        for ol in [c for c in nav if lname(c) == "ol"]:
            nav.remove(ol)
        ol = ET.SubElement(nav, X("ol"))
        cur_sub = None
        for lv, label, path, id_ in entries:
            li = ET.Element(X("li"))
            a = ET.SubElement(li, X("a"))
            a.set("href", rel_href(doc.path, path) + "#" + id_)
            a.text = label
            if lv == 2 and cur_sub is not None:
                cur_sub.append(li)
            else:
                ol.append(li)
                cur_sub = None
                if lv == 1:
                    cur_sub = ET.SubElement(li, X("ol"))
        for li in ol.iter(X("li")):
            for sub in [c for c in li if lname(c) == "ol" and len(c) == 0]:
                li.remove(sub)
        return True
    return False


# --------------------------------------------------------------------------
# page-map Adobe → <pageList> du toc.ncx (EPUB 2 standard)
# --------------------------------------------------------------------------

ROMAN_PAGE = re.compile(r"^[ivxlcdm]+$", re.I)


def doc_order_key(spine, texts):
    """Clé d'ordre de lecture d'une cible fichier#id."""
    cache = {}

    def key(path, frag):
        idx = spine.index(path) if path in spine else len(spine)
        if not frag:
            return (idx, -1)
        if path not in cache:
            cache[path] = {m.group(1): m.start() for m in
                           re.finditer(r"""\sid\s*=\s*["']([^"']+)["']""", texts.get(path, ""))}
        return (idx, cache[path].get(frag, -1))
    return key


def page_map_to_ncx(ncx_text, ncx_path, pm_text, pm_path, spine, texts, stats, log):
    ids = {p: set(re.findall(r"""\sid\s*=\s*["']([^"']+)["']""", t)) for p, t in texts.items()}
    pages, last_good = [], {}
    for m in re.finditer(r"<(?:[\w-]+:)?page\b[^>]*>", pm_text):
        name, href = get_attr(m.group(0), "name"), get_attr(m.group(0), "href")
        if name is None or not href:
            continue
        path, _, frag = href.partition("#")
        target = resolve(pm_path, path)
        if frag and frag not in ids.get(target, ()):
            # ancre disparue (page blanche supprimée…) : page précédente du même fichier
            frag = last_good.get(target, "")
            stats["pages sans ancre (rattachées)"] += 1
        if frag:
            last_good[target] = frag
        pages.append((name.strip(), target, frag))
    if not pages:
        return None

    out = ['  <pageList>\n    <navLabel><text>Pages</text></navLabel>\n']
    max_num = 0
    for n, (name, target, frag) in enumerate(pages, 1):
        if name.isdigit():
            ptype, value = "normal", ' value="%d"' % int(name)
            max_num = max(max_num, int(name))
        elif ROMAN_PAGE.match(name):
            ptype, value = "front", ""
        else:
            ptype, value = "special", ""
        src = rel_href(ncx_path, target) + ("#" + frag if frag else "")
        out.append('    <pageTarget id="page-%d" type="%s"%s playOrder="0">'
                   '<navLabel><text>%s</text></navLabel><content src="%s"/></pageTarget>\n'
                   % (n, ptype, value, html.escape(name, quote=False), html.escape(src)))
    out.append("  </pageList>\n")
    ncx_text = re.sub(r"\s*<pageList\b.*?</pageList>", "", ncx_text, flags=re.S)
    ncx_text = re.sub(r"(</navMap>\s*\n?)", lambda m: m.group(1) + "".join(out), ncx_text, count=1)
    for meta, val in (("dtb:totalPageCount", len(pages)), ("dtb:maxPageNumber", max_num)):
        ncx_text = re.sub(r"""(<meta\s+name=["']%s["']\s+content=["'])[^"']*""" % meta,
                          lambda m: m.group(1) + str(val), ncx_text)
    stats["pages converties en pageList"] = len(pages)
    return ncx_text


def renumber_play_order(ncx_text, ncx_path, spine, texts):
    """playOrder = ordre de lecture ; même cible → même numéro, sans trou."""
    key = doc_order_key(spine, texts)
    pat = re.compile(r"""<(navPoint|pageTarget)\b[^>]*>.*?<content\s+src=["']([^"']+)["']""", re.S)
    found = []
    for m in pat.finditer(ncx_text):
        path, _, frag = m.group(2).partition("#")
        found.append(key(resolve(ncx_path, path), unquote(frag)))
    rank = {k: i + 1 for i, k in enumerate(sorted(set(found)))}
    it = iter(found)

    def repl(m):
        k = next(it)
        tag = re.sub(r"""playOrder\s*=\s*["'][^"']*["']""", 'playOrder="%d"' % rank[k], m.group(0), count=1)
        return tag
    return pat.sub(repl, ncx_text)


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Structure un EPUB issu d'OCR (titres, sommaires, notes, TdM).")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--merge-pages", action="store_true",
                    help="recoller les paragraphes coupés par un changement de page")
    ap.add_argument("--drop-furniture", action="store_true",
                    help="supprimer folios, signatures et signes isolés")
    ap.add_argument("--chapter-regex", default=CHAPTER_RE,
                    help="expression des titres de chapitre (→ h2)")
    ap.add_argument("--book-regex", default=BOOK_RE,
                    help="expression des titres de livre/partie (→ h1)")
    ap.add_argument("--title-before", action="store_true",
                    help="le titre en capitales qui PRÉCÈDE « Chapitre N » devient le h2 "
                         "(éditions anciennes comme Belon)")
    ap.add_argument("--summary-max", type=int, default=350,
                    help="longueur maximale d'un sommaire de chapitre (0 = pas de sommaire)")
    ap.add_argument("--table-regex", default=TABLE_RE,
                    help="titre de la table imprimée (→ h2 ; plus aucun titre détecté après)")
    ap.add_argument("--keep-page-map", action="store_true",
                    help="garder la page-map Adobe (sinon convertie en <pageList> du toc.ncx, "
                         "format standard : plus d'erreur epubcheck)")
    ap.add_argument("--no-toc", action="store_true", help="ne pas reconstruire la table des matières")
    ap.add_argument("--css-path", default="Styles/livre.css", help="feuille à compléter (relative à l'OPF)")
    ap.add_argument("--verbose", action="store_true", help="détailler chaque jonction")
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    opts = ap.parse_args()

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(i.filename for i in infos)
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf_text, opf_enc, opf_bom = decode_text(zin.read(opf_path))
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf_text):
            href = get_attr(m.group(0), "href")
            if href:
                items[get_attr(m.group(0), "id")] = (resolve(opf_path, href),
                                                     (get_attr(m.group(0), "media-type") or "").lower(),
                                                     get_attr(m.group(0), "properties") or "")
        spine = [items[i][0] for i in re.findall(
            r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf_text) if i in items]
        nav_path = next((p for p, mt, pr in items.values() if "nav" in pr.split()), None)
        ncx_path = next((p for p, mt, _ in items.values() if mt == "application/x-dtbncx+xml"), None)

        docs = []
        for p in spine:
            if p == nav_path or not p in names:
                continue
            t, enc, bom = decode_text(zin.read(p))
            try:
                d = Doc(p, t, enc, bom)
            except ET.ParseError as e:
                print("Avertissement : %s ignoré (%s)" % (p, e), file=sys.stderr)
                continue
            if d.body is not None:
                docs.append(d)

        # Vocabulaire du livre (pour décider « Montgom|mery » → « Montgommery »)
        vocab = collections.Counter()
        for d in docs:
            for w in re.findall(r"[\w'’-]+", "".join(d.body.itertext())):
                vocab[w.lower()] += 1
                for part in re.split(r"['’]", w):
                    if part and part != w:
                        vocab[part.lower()] += 1

        stats, log = collections.Counter(), []
        s = Structurer(opts, vocab, names, stats, log)
        for d in docs:
            s.used_ids.update(x.get("id") for x in d.root.iter() if x.get("id"))
        removed_all = collections.Counter()
        for d in docs:
            try:
                s.run(d)
            except RuntimeError as e:
                sys.exit("ARRÊT, rien n'a été écrit.\n%s" % e)
            removed_all.update(s.removed)
            s.removed = collections.Counter()

        # Table des matières (avant sérialisation : des id peuvent être ajoutés)
        entries = toc_entries(docs, s.chapter_re, s.book_re, s.table_re, s.used_ids)
        new_data = {d.path: d.serialize() for d in docs}
        if entries and not opts.no_toc:
            if ncx_path and ncx_path in names:
                ncx_text, enc, bom = decode_text(zin.read(ncx_path))
                first = None
                m = re.search(r"<navPoint\b.*?<text>(.*?)</text>.*?<content\s+src=[\"']([^\"']+)",
                              ncx_text, re.S)
                if m:
                    first_file = resolve(ncx_path, m.group(2).split("#")[0])
                    head_doc = next(d for d in docs if d.path == entries[0][2])
                    head_is_first = list(head_doc.body)[:1] and \
                        list(head_doc.body)[0].get("id") == entries[0][3]
                    if first_file != entries[0][2] or not head_is_first:
                        first = (html.unescape(m.group(1)), m.group(2))
                new_data[ncx_path] = bom + build_ncx(ncx_text, ncx_path, entries, first).encode(enc)
                stats["entrées de table des matières"] = len(entries)
            if nav_path and nav_path in names:
                t, enc, bom = decode_text(zin.read(nav_path))
                nd = Doc(nav_path, t, enc, bom)
                if build_nav(nd, entries):
                    new_data[nav_path] = nd.serialize()

        # page-map Adobe → pageList
        drop_files = set()
        pm_attr = re.search(r"""(<(?:[\w-]+:)?spine\b[^>]*?)\s+page-map\s*=\s*["']([^"']+)["']""", opf_text)
        if pm_attr and not opts.keep_page_map and ncx_path and ncx_path in names \
                and pm_attr.group(2) in items:
            pm_path = items[pm_attr.group(2)][0]
            texts = {}
            for p in spine:
                if p in new_data:
                    texts[p] = new_data[p].decode("utf-8", "replace")
                elif p in names:
                    texts[p] = zin.read(p).decode("utf-8", "replace")
            ncx_bytes = new_data.get(ncx_path) or zin.read(ncx_path)
            ncx_text, enc, bom = decode_text(ncx_bytes)
            pm_text = zin.read(pm_path).decode("utf-8", "replace") if pm_path in names else ""
            conv = page_map_to_ncx(ncx_text, ncx_path, pm_text, pm_path, spine, texts, stats, log)
            if conv is not None:
                conv = renumber_play_order(conv, ncx_path, spine, texts)
                new_data[ncx_path] = bom + conv.encode(enc)
                opf_new = opf_text.replace(pm_attr.group(0), pm_attr.group(1), 1)
                item_tag = re.search(r"""[ \t]*<(?:[\w-]+:)?item\b[^>]*\sid\s*=\s*["']%s["'][^>]*>[ \t]*\r?\n?"""
                                     % re.escape(pm_attr.group(2)), opf_new)
                if item_tag:
                    opf_new = opf_new.replace(item_tag.group(0), "", 1)
                new_data[opf_path] = opf_bom + opf_new.encode(opf_enc)
                drop_files.add(pm_path)
        elif ncx_path in new_data:
            # TdM reconstruite : playOrder cohérents avec d'éventuelles pages
            texts = {p: (new_data[p] if p in new_data else zin.read(p)).decode("utf-8", "replace")
                     for p in spine if p in names}
            t, enc, bom = decode_text(new_data[ncx_path])
            new_data[ncx_path] = bom + renumber_play_order(t, ncx_path, spine, texts).encode(enc)

        # CSS
        css_path = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), opts.css_path))
        if css_path in names:
            css = zin.read(css_path).decode("utf-8")
            css = re.sub(re.escape(CSS_MARK_BEGIN) + r".*?" + re.escape(CSS_MARK_END) + r"\n?", "",
                         css, flags=re.S)
            new_data[css_path] = (css.rstrip() + "\n\n" + CSS_ADDITIONS).encode("utf-8")
        else:
            print("Remarque : %s absente (lancer d'abord epub_simplify.py) ; styles non ajoutés." % css_path)

        # Rapport
        for k, v in sorted(stats.items(), key=lambda kv: (kv[0].startswith("  "), kv[0])):
            print("  %-32s %6d" % (k, v))
        if removed_all:
            print("Restes de mise en page retirés :")
            print("   " + ", ".join("« %s »×%d" % (k, v) if v > 1 else "« %s »" % k
                                    for k, v in removed_all.most_common()))
        if log:
            print("\n".join(log))
        print("Texte vérifié : mêmes caractères qu'avant (espaces exclus%s%s)."
              % (", césures recollées exclues" if opts.merge_pages else "",
                 ", restes de mise en page retirés exclus" if opts.drop_furniture else ""))
        if opts.dry_run:
            print("(--dry-run : rien n'a été écrit)")
            return

        out_path = opts.output or src
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w") as zout:
                for info in sorted(infos, key=lambda i: i.filename != "mimetype"):
                    if info.filename in drop_files:
                        continue
                    data = new_data.get(info.filename)
                    if data is None:
                        data = zin.read(info)
                    if info.filename == "mimetype":
                        info.compress_type = zipfile.ZIP_STORED
                    zout.writestr(info, data, compress_type=info.compress_type)
        except BaseException:
            os.unlink(tmp)
            raise

    if not opts.output and opts.backup:
        shutil.copy2(src, src + ".bak")
    shutil.copymode(src, tmp)
    os.replace(tmp, out_path)
    print("EPUB écrit : %s" % out_path)


if __name__ == "__main__":
    main()
