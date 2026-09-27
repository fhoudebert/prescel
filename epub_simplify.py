#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_simplify.py — Simplifie le balisage d'un EPUB issu d'OCR (Google Books,
ABBYY…) : on accepte de perdre la mise en forme, JAMAIS le texte.

Ce que fait le script sur chaque XHTML :
  * supprime les <a id="…"></a> vides, sauf ceux qui servent de cible à un
    lien (page-map, toc.ncx, nav, autres XHTML) : ceux-là sont conservés,
    en déplaçant de préférence l'id sur le paragraphe qui suit ;
  * supprime les id inutiles (block.…, para.…) ;
  * « déballe » les <div> qui ne contiennent que des blocs (flow, gtxt_body…)
    et supprime les <div>/<p> vides (y compris ceux qui ne contiennent que &#160;) ;
  * déballe les <span> sans rôle ; les spans en italique/gras deviennent <i>/<b> ;
  * remplace toutes les classes par un petit jeu lisible :
      marge (notes marginales), centre, droite, image, h1…h4 pour les titres Google ;
  * retire les <br/> en début/fin de paragraphe, normalise les espaces ;
  * vide les alt parasites du type « [ocr errors][merged small] » ;
  * retire les commentaires et les <style> embarqués, remplace les feuilles
    de style par une seule Styles/livre.css (déclarée au manifest) ;
  * VÉRIFIE, fichier par fichier, que le texte est identique avant/après
    (espaces exclus) ; en cas d'écart, rien n'est écrit.

Options qui touchent légèrement au texte (désactivées par défaut, vérifiées
aussi) :
  --join-hyphens  recolle les mots coupés en fin de ligne (« estran-<br/>ges »)
  --flatten-br    remplace les <br/> restants par une espace (texte continu)
  --lettrines     recolle les lettrines isolées (« M » + « E trouuant… »)
                  au début du paragraphe suivant ; chaque fusion est listée

Aucune dépendance externe (Python 3.8+).

Usage :
  python3 epub_simplify.py livre.epub -o livre-simple.epub
  python3 epub_simplify.py livre.epub -o livre-simple.epub --join-hyphens --flatten-br --lettrines
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
               ("xlink", "http://www.w3.org/1999/xlink"),
               ("epub", "http://www.idpf.org/2007/ops"),
               ("m", "http://www.w3.org/1998/Math/MathML")):
    ET.register_namespace(_p, _u)

BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "table",
         "blockquote", "pre", "hr", "address"}
TEXT_BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "dd", "td", "th"}
MEDIA = {"img", "svg", "image", "object", "video", "audio", "math", "iframe"}
HEADINGS = {"gtxt_heading": "h1", "gtxt_h1_heading": "h2",
            "gtxt_h2_heading": "h3", "gtxt_h3_heading": "h4"}
MARGIN_CLASSES = {"gtxt_footnote"}
JUNK_ALT = re.compile(r"^\s*(\[[^\]]*\]\s*)+$")
LETTRINE_RE = re.compile(r"^[A-ZÀ-ÖØ-Þ]$")

CSS_TEMPLATE = """/* Généré par epub_simplify.py */
body { margin: 0 1em; font-family: serif; }
p { margin: 0 0 0.6em 0; text-indent: 0; text-align: justify; }
h1, h2, h3, h4 { text-align: center; margin: 1em 0 0.6em 0; }
.marge { font-size: 85%; font-style: italic; margin: 0.2em 0 0.2em 2em; text-align: left; }
.centre { text-align: center; }
.droite { text-align: right; }
.image { text-align: center; margin: 1em 0; }
img { max-width: 100%; max-height: 100%; }
"""


# --------------------------------------------------------------------------
# Utilitaires généraux
# --------------------------------------------------------------------------

def lname(el):
    t = el.tag
    if not isinstance(t, str):
        return ""
    return t.rsplit("}", 1)[-1].lower()


def X(tag):
    return "{%s}%s" % (XHTML_NS, tag)


def resolve(base_file, href):
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_file), unquote(href)))


def rel_href(from_file, to_file):
    return quote(posixpath.relpath(to_file, posixpath.dirname(from_file) or "."), safe="/")


def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8", data[:3]
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    enc = m.group(1).decode("ascii") if m else "utf-8"
    return data.decode(enc), enc, b""


def get_attr(tag, name):
    m = re.search(r"""\s%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % re.escape(name), tag, re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def compact(s):
    """Texte sans aucun blanc : base de la vérification."""
    return "".join((s or "").split())


def body_text(el):
    return compact("".join(el.itertext()))


def has_content(el, keep_ids):
    """Vrai si l'élément porte du texte, un média ou une ancre utile."""
    if "".join(el.itertext()).strip():
        return True
    for d in el.iter():
        if lname(d) in MEDIA:
            return True
    return False


def referenced_ids_in(el, keep_ids):
    return [d.get("id") for d in el.iter() if d.get("id") in keep_ids]


# --------------------------------------------------------------------------
# CSS : classe -> déclarations
# --------------------------------------------------------------------------

def parse_css_classes(css, table):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        decls = {}
        for part in m.group(2).split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                decls[k.strip().lower()] = v.strip().lower()
        for sel in m.group(1).split(","):
            last = sel.strip().split()[-1] if sel.strip() else ""
            cm = re.fullmatch(r"[\w-]*\.([\w-]+)", last)
            if cm:
                table.setdefault(cm.group(1), {}).update(decls)


def element_decls(el, css_table):
    decls = {}
    for c in (el.get("class") or "").split():
        decls.update(css_table.get(c, {}))
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            decls[k.strip().lower()] = v.strip().lower()
    return decls


def font_size_ratio(v):
    if not v:
        return 1.0
    m = re.match(r"([\d.]+)\s*(%|em)?", v)
    if not m:
        return 1.0
    n = float(m.group(1))
    return n / 100 if m.group(2) == "%" else (n if m.group(2) == "em" else 1.0)


# --------------------------------------------------------------------------
# Manipulations d'arbre (en préservant texte et « tail »)
# --------------------------------------------------------------------------

def add_text_before(parent, index, text):
    """Rattache un texte à la position index du parent."""
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


def unwrap(parent, child):
    """Remplace child par son contenu (texte + enfants + tail)."""
    i = list(parent).index(child)
    kids = list(child)
    text, tail = child.text, child.tail
    parent.remove(child)
    add_text_before(parent, i, text)
    for k, kid in enumerate(kids):
        parent.insert(i + k, kid)
    if kids:
        kids[-1].tail = (kids[-1].tail or "") + (tail or "")
    else:
        add_text_before(parent, i, tail)


def is_block_only(div):
    if (div.text or "").strip():
        return False
    for ch in div:
        if lname(ch) not in BLOCK or (ch.tail or "").strip():
            return False
    return True


def make_anchor(el_id):
    a = ET.Element(X("a"))
    a.set("id", el_id)
    return a


# --------------------------------------------------------------------------
# Nettoyage d'un document
# --------------------------------------------------------------------------

class Cleaner:
    def __init__(self, keep_ids, css_table, opts, stats):
        self.keep_ids = keep_ids
        self.css = css_table
        self.opts = opts
        self.st = stats

    # -- étape 0 : attributs, classes, renommages --------------------------
    def fix_attributes(self, el):
        name = lname(el)
        classes = (el.get("class") or "").split()
        decls = element_decls(el, self.css)
        new_classes = []

        if name in ("p", "div"):
            for c in classes:
                if c in HEADINGS and name == "p":
                    el.tag = X(HEADINGS[c])
                    self.st["titres"] += 1
            if "gtxt_toc_entry" in classes:
                new_classes.append("tdm")          # ligne de la table des matières imprimée
            elif "gtxt_index_entry" in classes:
                new_classes.append("index")        # entrée d'index
            elif any(c in MARGIN_CLASSES for c in classes):
                new_classes.append("marge")
            else:
                align = decls.get("text-align", "")
                if align == "center":
                    new_classes.append("centre")
                elif align == "right":
                    # Mot isolé aligné à droite : presque toujours une manchette
                    short = len("".join(el.itertext()).strip()) < 40
                    new_classes.append("marge" if short and name == "p" else "droite")
            if name == "p" and self.opts.lettrines and \
                    LETTRINE_RE.match("".join(el.itertext()).strip()):
                # « 1 » : grande lettre (taille ≥ 150 %) ; « 2 » : lettre seule de
                # taille ordinaire, recollée seulement si le mot obtenu existe.
                big = font_size_ratio(decls.get("font-size")) >= 1.5
                el.set("data-lettrine", "1" if big else "2")
        elif name == "span":
            if "gstxt_sup" in classes or decls.get("vertical-align") == "super":
                el.tag = X("sup")
            elif "gstxt_sub" in classes or decls.get("vertical-align") == "sub":
                el.tag = X("sub")
            elif decls.get("font-style") == "italic":
                el.tag = X("i")
            elif decls.get("font-weight") in ("bold", "bolder", "700", "800", "900"):
                el.tag = X("b")
        elif name == "img":
            alt = el.get("alt")
            if alt is not None and JUNK_ALT.match(alt):
                el.set("alt", "")
                self.st["alt vidés"] += 1

        for attr in ("class", "style"):
            if attr in el.attrib:
                del el.attrib[attr]
        if new_classes:
            el.set("class", " ".join(new_classes))
        if "id" in el.attrib and el.get("id") not in self.keep_ids and not self.opts.keep_ids:
            del el.attrib["id"]
            self.st["id retirés"] += 1
        if lname(el) != name and name == "span":
            for a in list(el.attrib):
                if a != "id":
                    del el.attrib[a]

    # -- nettoyage récursif -------------------------------------------------
    def clean(self, el):
        self.fix_attributes(el)
        for ch in list(el):
            if isinstance(ch.tag, str):
                self.clean(ch)
            else:  # commentaire / PI résiduel
                remove_keep_tail(el, ch)

        # 1. éléments parasites
        for ch in list(el):
            n = lname(ch)
            if n == "a" and not ch.get("href") and len(ch) == 0 and not (ch.text or "").strip():
                if ch.get("id") not in self.keep_ids:
                    remove_keep_tail(el, ch)
                    self.st["ancres vides"] += 1
            elif n == "a" and not ch.get("href") and not ch.get("id"):
                unwrap(el, ch)
                self.st["spans/ancres déballés"] += 1
            elif n == "span" and not ch.get("id"):
                unwrap(el, ch)
                self.st["spans/ancres déballés"] += 1
            elif n in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6") and \
                    not has_content(ch, self.keep_ids):
                ids = referenced_ids_in(ch, self.keep_ids)
                i = list(el).index(ch)
                tail = ch.tail
                el.remove(ch)
                for k, id_ in enumerate(ids):
                    a = make_anchor(id_)
                    el.insert(i + k, a)
                if ids:
                    el[i + len(ids) - 1].tail = tail
                else:
                    add_text_before(el, i, tail)
                self.st["blocs vides"] += 1

        # 2. déballage des div qui ne contiennent que des blocs
        for ch in list(el):
            if lname(ch) == "div" and not ch.get("id") and is_block_only(ch):
                unwrap(el, ch)
                self.st["div déballées"] += 1

        # 3. ancres utiles : déplacées dans le bloc voisin
        if lname(el) in ("body", "div", "blockquote", "li", "td"):
            self.relocate_anchors(el)

        # 4. div restantes : classe « image » si elles portent une image
        for ch in el:
            if lname(ch) == "div" and not ch.get("class"):
                if any(lname(d) in MEDIA for d in ch.iter()) and not "".join(ch.itertext()).strip():
                    ch.set("class", "image")

    def relocate_anchors(self, parent):
        kids = list(parent)
        for idx, ch in enumerate(kids):
            if not (lname(ch) == "a" and ch.get("id") and not ch.get("href")
                    and len(ch) == 0 and not (ch.text or "").strip()):
                continue
            if (ch.tail or "").strip():
                continue  # du texte suit : l'ancre est déjà bien placée
            target = None
            for nxt in kids[idx + 1:]:
                if lname(nxt) in BLOCK:
                    target = nxt
                    break
                if lname(nxt) != "a":
                    break
            where = "start"
            if target is None:
                for prv in reversed(kids[:idx]):
                    if lname(prv) in BLOCK:
                        target, where = prv, "end"
                        break
            if target is None or lname(target) in ("ul", "ol", "dl", "table", "hr"):
                if target is not None and not target.get("id"):
                    target.set("id", ch.get("id"))
                    remove_keep_tail(parent, ch)
                continue
            if not target.get("id") and where == "start":
                target.set("id", ch.get("id"))
                remove_keep_tail(parent, ch)
            else:
                remove_keep_tail(parent, ch)
                ch.tail = None
                if where == "start":
                    ch.tail = target.text
                    target.text = None
                    target.insert(0, ch)
                else:
                    target.append(ch)
            self.st["ancres déplacées"] += 1


# --------------------------------------------------------------------------
# Passes de texte : espaces, <br/>, césures, lettrines
# --------------------------------------------------------------------------

WS = re.compile(r"[ \t\r\n]+")


def normalize_ws(block):
    block.text = WS.sub(" ", block.text) if block.text else block.text
    for d in block.iter():
        if d is not block:
            if d.text:
                d.text = WS.sub(" ", d.text)
            if d.tail:
                d.tail = WS.sub(" ", d.tail)


def strip_edges(block):
    # début
    if block.text:
        block.text = block.text.lstrip(" ") or None
    # fin (dernier nœud texte, en descendant)
    node = block
    while True:
        if len(node):
            last = node[-1]
            if last.tail and last.tail.strip(" "):
                last.tail = last.tail.rstrip(" ")
                break
            last.tail = None
            if lname(last) in ("br", "img", "a") and not (last.text or ""):
                break
            node = last
        else:
            if node.text:
                node.text = node.text.rstrip(" ") or None
            break


def text_before(parent, child):
    """(getter, setter) du texte qui précède child dans parent."""
    kids = list(parent)
    i = kids.index(child)
    if i == 0:
        return (lambda: parent.text or "", lambda v: setattr(parent, "text", v or None))
    prev = kids[i - 1]
    return (lambda: prev.tail or "", lambda v: setattr(prev, "tail", v or None))


def fix_breaks(block, opts, st):
    # <br/> en tête / en queue
    changed = True
    while changed:
        changed = False
        if len(block) and lname(block[0]) == "br" and not (block.text or "").strip():
            remove_keep_tail(block, block[0])
            block.text = (block.text or "").lstrip() or None
            st["br superflus"] += 1
            changed = True
        if len(block) and lname(block[-1]) == "br" and not (block[-1].tail or "").strip():
            block.remove(block[-1])
            st["br superflus"] += 1
            changed = True
    for br in [d for d in block.iter() if lname(d) == "br"]:
        parent = next(p for p in block.iter() if br in list(p))
        get, put = text_before(parent, br)
        before, after = get(), br.tail or ""
        if opts.join_hyphens:
            mb = re.search(r"(\w)-\s*$", before)
            ma = re.match(r"\s*([a-zà-öø-ÿœæ])", after)
            if mb and ma:
                put(before[:mb.start() + 1] + after.lstrip())
                parent.remove(br)
                st["césures recollées"] += 1
                continue
        if opts.flatten_br:
            put(before.rstrip() + " " + after.lstrip())
            parent.remove(br)
            st["br remplacés"] += 1
        else:
            put(before.rstrip(" "))
            br.tail = after.lstrip(" ") or None


VOCAB = collections.Counter()      # mots du livre (minuscules), rempli par main()
FIRST_WORD = re.compile(r"\s*([A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]+)")


def lettrine_word_ok(letter, text):
    """La lettre + le premier mot du paragraphe forment-ils un mot du livre ?"""
    m = FIRST_WORD.match(text)
    if not m:
        return False
    glued = VOCAB.get((letter + m.group(1)).lower(), 0)
    alone = VOCAB.get(m.group(1).lower(), 0)
    # « Le Grand Vizir » : « le » est un mot très courant à lui seul, « ble » non
    return glued >= 2 and glued * 20 >= alone


def merge_inline_lettrines(body, st, log, doc):
    """« C OMME les Colchéens » → « COMME les Colchéens » (lettrine séparée par une espace)."""
    pat = re.compile(r"^(\s*)([A-ZÀ-Þ])\s+([A-ZÀ-Þ][A-ZÀ-Þa-zà-ÿ]*)(?=[\s,.;:!?'’]|$)")
    for p in body.iter():
        if lname(p) not in TEXT_BLOCKS or not p.text:
            continue
        m = pat.match(p.text)
        if not m:
            continue
        letter, rest = m.group(2), m.group(3)
        glued, alone = (letter + rest).lower(), rest.lower()
        if VOCAB.get(glued, 0) >= 2 and VOCAB.get(alone, 0) <= 1 and \
                not (letter in "AÀOY" and VOCAB.get(alone, 0) > 0):
            p.text = m.group(1) + letter + rest + p.text[m.end():]
            st["lettrines recollées"] += 1
            log.append("  %s : « %s %s » → %s%s" % (doc, letter, rest, letter, rest))


def merge_lettrines(body, st, log, doc):
    merge_inline_lettrines(body, st, log, doc)
    paras = [p for p in body.iter() if lname(p) in TEXT_BLOCKS]
    for i, p in enumerate(paras):
        kind = p.get("data-lettrine")
        if kind not in ("1", "2"):
            continue
        letter = "".join(p.itertext()).strip()
        target = None
        for q in paras[i + 1:i + 8]:
            t = "".join(q.itertext()).strip()
            if q.get("data-lettrine") or q.get("class") == "marge" or len(t) < 40:
                continue
            if t[:1].isalpha():
                target = q
            break
        del p.attrib["data-lettrine"]
        if target is not None:
            ttext = "".join(target.itertext()).lstrip()
            # La suite d'une lettrine est composée en capitales (« E partis », « OMME ») :
            # la lettre + le premier mot doivent donner un mot connu du livre.
            if not ttext[:1].isupper() or not lettrine_word_ok(letter, ttext):
                if kind == "1":
                    log.append("  %s : lettrine « %s » laissée seule (« %s%s… » inconnu)"
                               % (doc, letter, letter, ttext[:12]))
                continue
        if target is None:
            log.append("  %s : lettrine « %s » laissée seule (cible introuvable)" % (doc, letter))
            continue
        first = (target.text or "")
        target.text = letter + first.lstrip(" ")
        parent = next(x for x in body.iter() if p in list(x))
        ids = [p.get("id")] if p.get("id") else []
        idx = list(parent).index(p)
        tail = p.tail
        parent.remove(p)
        for k, id_ in enumerate(ids):
            parent.insert(idx + k, make_anchor(id_))
        add_text_before(parent, idx + len(ids), tail)
        st["lettrines recollées"] += 1
        preview = "".join(target.itertext()).strip()[:50]
        log.append("  %s : « %s » → %s…" % (doc, letter, preview))
    for p in body.iter():
        if "data-lettrine" in p.attrib:
            del p.attrib["data-lettrine"]


def layout(el, depth=0):
    """Retours à la ligne entre blocs (sans toucher au contenu des paragraphes)."""
    if lname(el) in TEXT_BLOCKS:
        return
    kids = list(el)
    if not kids:
        return
    if (el.text or "").strip() or any((k.tail or "").strip() for k in kids):
        return
    if not all(lname(k) in BLOCK or lname(k) in ("li", "a") for k in kids):
        return
    ind = "  " * (depth + 1)
    el.text = "\n" + ind
    for k in kids:
        k.tail = "\n" + ind
        layout(k, depth + 1)
    kids[-1].tail = "\n" + "  " * depth


# --------------------------------------------------------------------------
# Traitement d'un fichier XHTML
# --------------------------------------------------------------------------

def replace_named_entities(text):
    def rep(m):
        name = m.group(1)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        cp = html.entities.name2codepoint.get(name)
        return "&#%d;" % cp if cp else m.group(0)
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", rep, text)


def process_doc(path, text, keep_ids, css_table, css_path, old_css, opts, st, log):
    m = re.search(r"<(?:[\w-]+:)?html\b", text)
    prefix = text[:m.start()] if m else '<?xml version="1.0" encoding="utf-8"?>\n'
    prefix = re.sub(r"<!--.*?-->", "", prefix, flags=re.S)
    if opts.epub2 and re.search(r"<!DOCTYPE[^>]*XHTML 1\.0", prefix):
        # epubcheck exige le DOCTYPE XHTML 1.1 dans un EPUB 2 (Google met du 1.0 Strict)
        prefix = re.sub(r"<!DOCTYPE[^>]*>", '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
                        '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">', prefix, count=1)
        st["DOCTYPE mis en XHTML 1.1"] += 1
    root = ET.fromstring(replace_named_entities(text).encode("utf-8"))
    head = root.find(X("head"))
    body = root.find(X("body"))
    if body is None or not any(lname(e) == "p" for e in body.iter()):
        # rien à nettoyer (page d'image seule) ; on corrige quand même le DOCTYPE
        if opts.epub2 and re.search(r"<!DOCTYPE[^>]*XHTML 1\.0", text[:m.start() if m else 0]):
            st["DOCTYPE mis en XHTML 1.1"] += 1
            return re.sub(r"<!DOCTYPE[^>]*>", '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
                          '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">', text, count=1)
        return None

    # Classes définies dans les <style> embarqués (sélecteurs simples)
    table = dict(css_table)
    if head is not None:
        for s in head.findall(X("style")):
            parse_css_classes(s.text or "", table)

    before = body_text(body)
    Cleaner(keep_ids, table, opts, st).clean(body)
    if opts.lettrines:
        merge_lettrines(body, st, log, path)
    for b in [e for e in body.iter() if lname(e) in TEXT_BLOCKS | {"div"}]:
        normalize_ws(b)
        fix_breaks(b, opts, st)
        strip_edges(b)
    layout(body, 0)
    after = body_text(body)

    # Vérification du texte
    if opts.join_hyphens:
        before_cmp, after_cmp = before.replace("-", ""), after.replace("-", "")
    else:
        before_cmp, after_cmp = before, after
    ok = (collections.Counter(before_cmp) == collections.Counter(after_cmp)) if opts.lettrines \
        else before_cmp == after_cmp
    if not ok:
        i = next((k for k, (a, b) in enumerate(zip(before_cmp, after_cmp)) if a != b),
                 min(len(before_cmp), len(after_cmp)))
        raise RuntimeError("Texte modifié dans %s près de :\n  avant : …%s…\n  après : …%s…"
                           % (path, before_cmp[max(0, i - 40):i + 40],
                              after_cmp[max(0, i - 40):i + 40]))

    # <head> : on retire les <style> et l'ancienne feuille, on lie livre.css
    if head is not None:
        for s in head.findall(X("style")):
            remove_keep_tail(head, s)
        for ln in head.findall(X("link")):
            href = ln.get("href")
            if href and (resolve(path, href) in old_css or resolve(path, href) == css_path):
                remove_keep_tail(head, ln)
        link = ET.SubElement(head, X("link"))
        link.set("href", rel_href(path, css_path))
        link.set("rel", "stylesheet")
        link.set("type", "text/css")
        link.tail = "\n"
        if len(head) > 1 and not (head[-2].tail or "").strip():
            head[-2].tail = "\n  "

    out = ET.tostring(root, encoding="unicode")
    return prefix.rstrip() + "\n" + out + "\n"


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Simplifie le balisage d'un EPUB sans perdre de texte.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--css-path", default="Styles/livre.css",
                    help="feuille générée, relative à l'OPF (défaut : Styles/livre.css)")
    ap.add_argument("--join-hyphens", action="store_true",
                    help="recoller les mots coupés en fin de ligne (« estran-<br/>ges »)")
    ap.add_argument("--flatten-br", action="store_true",
                    help="remplacer les <br/> restants par une espace")
    ap.add_argument("--lettrines", action="store_true",
                    help="recoller les lettrines isolées au paragraphe suivant")
    ap.add_argument("--keep-ids", action="store_true", help="conserver tous les id")
    ap.add_argument("--keep-old-css", action="store_true",
                    help="ne pas retirer les anciennes feuilles CSS de l'EPUB")
    ap.add_argument("--backup", action="store_true", help="copie .bak en mode en place")
    ap.add_argument("--dry-run", action="store_true", help="tout vérifier sans écrire")
    opts = ap.parse_args()

    src = opts.epub
    if not zipfile.is_zipfile(src):
        sys.exit("Erreur : %s n'est pas une archive EPUB" % src)

    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = [i.filename for i in infos]
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf_text, opf_enc, opf_bom = decode_text(zin.read(opf_path))
        css_path = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), opts.css_path))

        items = []
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf_text):
            href = get_attr(m.group(0), "href")
            if href:
                items.append((resolve(opf_path, href), (get_attr(m.group(0), "media-type") or "").lower(),
                              get_attr(m.group(0), "id"), m.group(0)))
        docs = [p for p, mt, _, _ in items if mt == "application/xhtml+xml" and p in names]
        old_css = {p for p, mt, _, _ in items if mt == "text/css" and p != css_path}

        # Toutes les cibles de liens de l'EPUB : fichier -> {id}
        keep = collections.defaultdict(set)
        for n in names:
            if not n.lower().endswith((".xhtml", ".html", ".htm", ".xml", ".ncx", ".opf")):
                continue
            try:
                t = zin.read(n).decode("utf-8", "replace")
            except KeyError:
                continue
            for m in re.finditer(r"""(?:href|src)\s*=\s*["']([^"']*#[^"']+)["']""", t):
                path, frag = m.group(1).split("#", 1)
                target = resolve(n, path) if path else n
                keep[target].add(unquote(frag))

        css_table = {}
        for p in old_css:
            if p in names:
                parse_css_classes(zin.read(p).decode("utf-8", "replace"), css_table)

        stats = collections.Counter()
        ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf_text)
        opts.epub2 = not (ver and ver.group(1).startswith("3"))
        # Vocabulaire du livre, pour décider des lettrines de taille ordinaire
        for d in docs:
            try:
                raw = decode_text(zin.read(d))[0]
            except (UnicodeDecodeError, LookupError):
                continue
            plain = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]+", plain):
                VOCAB[w.lower()] += 1
        log, new_data = [], {}
        size_before = size_after = 0
        for d in docs:
            raw = zin.read(d)
            text, enc, bom = decode_text(raw)
            try:
                result = process_doc(d, text, keep[d], css_table, css_path, old_css, opts, stats, log)
            except ET.ParseError as e:
                print("Avertissement : %s ignoré (XML invalide : %s)" % (d, e), file=sys.stderr)
                continue
            except RuntimeError as e:
                sys.exit("ARRÊT, rien n'a été écrit.\n%s" % e)
            if result is None:
                continue
            new_data[d] = bom + result.encode(enc, "xmlcharrefreplace")
            size_before += len(raw)
            size_after += len(new_data[d])
            stats["fichiers"] += 1

        if not new_data:
            print("Aucun document à simplifier.")
            return

        # Anciennes feuilles encore utilisées par un document non traité ?
        still_used = set()
        for d in docs:
            if d in new_data:
                continue
            t = zin.read(d).decode("utf-8", "replace")
            for m in re.finditer(r"""href\s*=\s*["']([^"']+\.css)["']""", t):
                still_used.add(resolve(d, m.group(1)))
        drop_css = set() if opts.keep_old_css else (old_css - still_used)

        # OPF : ajout de livre.css, retrait des feuilles abandonnées
        new_opf = opf_text
        for p, mt, iid, tag in items:
            if p in drop_css:
                new_opf = re.sub(r"[ \t]*" + re.escape(tag) + r"[ \t]*\r?\n?", "", new_opf, count=1)
        if not any(p == css_path for p, _, _, _ in items):
            ids = set(re.findall(r"""\sid\s*=\s*["']([^"']+)""", new_opf))
            iid, n = "livre-css", 1
            while iid in ids:
                n += 1
                iid = "livre-css-%d" % n
            item = '<item id="%s" href="%s" media-type="text/css"/>' % (iid, rel_href(opf_path, css_path))
            end = re.search(r"\n([ \t]*)</(?:[\w-]+:)?manifest\s*>", new_opf)
            ind = (end.group(1) + "  ") if end else "  "
            pos = end.start() if end else new_opf.index("</manifest")
            new_opf = new_opf[:pos] + "\n" + ind + item + new_opf[pos:]
        new_data[opf_path] = opf_bom + new_opf.encode(opf_enc)

        # toc.ncx : dtb:uid doit reprendre l'identifiant unique de l'OPF (EPUB 2)
        uid_ref = re.search(r"""<(?:[\w-]+:)?package\b[^>]*unique-identifier\s*=\s*["']([^"']+)""", opf_text)
        uid_m = uid_ref and re.search(
            r"""<dc:identifier\b[^>]*\sid\s*=\s*["']%s["'][^>]*>\s*([^<]*?)\s*<""" % re.escape(uid_ref.group(1)),
            opf_text)
        for p, mt, _, _ in items:
            if uid_m and mt == "application/x-dtbncx+xml" and p in names:
                t, enc, bom = decode_text(zin.read(p))
                nt = re.sub(r"""(<meta\s+name\s*=\s*["']dtb:uid["']\s+content\s*=\s*["'])[^"']*(["'])""",
                            lambda m: m.group(1) + html.escape(uid_m.group(1)) + m.group(2), t, count=1)
                if nt != t:
                    new_data[p] = bom + nt.encode(enc)
                    stats["ncx uid corrigé"] += 1
        new_data[css_path] = CSS_TEMPLATE.encode("utf-8")

        print("Fichiers simplifiés : %d  (%d Ko → %d Ko)"
              % (stats.pop("fichiers"), size_before // 1024, size_after // 1024))
        for k, v in sorted(stats.items()):
            print("  %-24s %6d" % (k, v))
        if drop_css:
            print("  feuilles retirées       : %s" % ", ".join(sorted(drop_css)))
        print("Texte vérifié : identique dans tous les fichiers (espaces exclus%s)."
              % (", tirets de césure exclus" if opts.join_hyphens else ""))
        if log:
            print("Lettrines :")
            print("\n".join(log))
        if opts.dry_run:
            print("(--dry-run : rien n'a été écrit)")
            return

        out_path = opts.output or src
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
        os.close(fd)
        try:
            now = datetime.datetime.now().timetuple()[:6]
            with zipfile.ZipFile(tmp, "w") as zout:
                for info in sorted(infos, key=lambda i: i.filename != "mimetype"):
                    if info.filename in drop_css:
                        continue
                    data = new_data.pop(info.filename, None)
                    if data is None:
                        data = zin.read(info)
                    if info.filename == "mimetype":
                        info.compress_type = zipfile.ZIP_STORED
                    zout.writestr(info, data, compress_type=info.compress_type)
                for name, data in new_data.items():   # fichiers nouveaux (livre.css)
                    zi = zipfile.ZipInfo(name, now)
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = 0o644 << 16
                    zout.writestr(zi, data)
        except BaseException:
            os.unlink(tmp)
            raise

    if not opts.output and opts.backup:
        shutil.copy2(src, src + ".bak")
    shutil.copymode(src, tmp)   # mkstemp crée en 0600 : on reprend les droits de l'original
    os.replace(tmp, out_path)
    print("EPUB écrit : %s" % out_path)


if __name__ == "__main__":
    main()
