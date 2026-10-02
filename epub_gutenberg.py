#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_gutenberg.py — Produit, à partir d'un EPUB relu, les deux fichiers « maîtres »
demandés par Project Gutenberg :

  * <nom>.txt   texte brut UTF-8 : lignes de 72 caractères au plus, paragraphes séparés
                par une ligne vide, quatre lignes vides avant chaque chapitre et deux
                après, italique en _soulignés_, notes en [1] reportées en fin de chapitre ;
  * <nom>.html  HTML5 valide (validator.w3.org) : une seule page, CSS intégrée,
                notes reliées dans les deux sens, aucun script.

Ce qui sert à la relecture disparaît : numéros de page (ancres GBS.…/page-…),
marqueurs a-verifier, classes de Prescel. Les notes sont renumérotées de 1 à N sur
tout le livre (dans l'imprimé, elles recommencent à 1 à chaque page).

Project Gutenberg ajoute lui-même son en-tête et sa licence : ne pas les écrire.
Avant l'envoi, la page de titre et son verso doivent passer la vérification des
droits sur https://copy.pglaf.org.

Usage :
  python3 epub_gutenberg.py livre.epub -o livre            # → livre.txt, livre.html
  python3 epub_gutenberg.py livre.epub -o livre --width 70 --note "Orthographe de l'édition conservée."
"""

import argparse
import html
import os
import re
import sys
import textwrap
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote
import posixpath

XHTML = "{http://www.w3.org/1999/xhtml}"
BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "blockquote", "hr"}
PAGE_ID = re.compile(r"^(?:GBS\.|page-|titre-|toc-)")


def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def classes(el):
    return set((el.get("class") or "").split())


def decode(data):
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    return data.decode(m.group(1).decode() if m else "utf-8")


def entities(text):
    import html.entities as he

    def rep(m):
        if m.group(1) in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        cp = he.name2codepoint.get(m.group(1))
        return "&#%d;" % cp if cp else m.group(0)
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", rep, text)


# --------------------------------------------------------------------------
# Lecture de l'EPUB → suite de blocs indépendante du format de sortie
# --------------------------------------------------------------------------
# Un bloc : {"kind": h1|h2|h3|p|hr|title, "cls": {...}, "runs": [(texte, style), …]}
# style : "" | "i" | "b" | "sup" | ("note", n) | "br"

class Book:
    def __init__(self):
        self.blocks = []          # [(n° de chapitre, bloc)]
        self.notes = {}           # n° → runs du texte de la note
        self.note_chapter = {}    # n° → chapitre
        self.title = ""
        self.author = ""
        self.lang = "fr"


def runs_of(el, notemap, out=None, style=""):
    """Texte d'un élément, en morceaux stylés ; ancres de page et marqueurs ignorés."""
    out = [] if out is None else out
    if el.text:
        out.append((el.text, style))
    for ch in el:
        n = lname(ch)
        if n == "br":
            out.append(("\n", "br"))
        elif n == "sup" and len(ch) and lname(ch[0]) == "a" and (ch[0].get("href") or "").startswith("#"):
            target = ch[0].get("href")[1:]
            if target in notemap:
                out.append(("", ("note", notemap[target])))
            else:
                out.append(("".join(ch.itertext()), "sup"))
        elif n == "a" and not ch.get("href"):
            runs_of(ch, notemap, out, style)          # ancre de page : on garde son texte éventuel
        elif n in ("i", "em", "cite"):
            runs_of(ch, notemap, out, "i")
        elif n in ("b", "strong"):
            runs_of(ch, notemap, out, "b" if style != "i" else "i")
        elif n == "sup":
            runs_of(ch, notemap, out, "sup")
        else:
            runs_of(ch, notemap, out, style)
        if ch.tail:
            out.append((ch.tail, style))
    return out


def fix_ocr_quotes(t):
    """« << » et « >> » de l'OCR → guillemets français."""
    t = re.sub(r"<<\s?", "« ", t)
    return re.sub(r"\s?>>>?", " »", t)


def clean_runs(runs):
    """Espaces normalisés ; texte vide retiré."""
    out = []
    for t, s in runs:
        if s == "br" or isinstance(s, tuple):
            out.append((t, s))
            continue
        t = fix_ocr_quotes(re.sub(r"[ \t\r\n]+", " ", t))
        if t:
            out.append((t, s))
    # pas d'espace en tête / en fin de bloc ni autour d'un saut de ligne
    while out and not isinstance(out[0][1], tuple) and out[0][1] != "br" and not out[0][0].strip():
        out.pop(0)
    while out and not isinstance(out[-1][1], tuple) and out[-1][1] != "br" and not out[-1][0].strip():
        out.pop()
    if out and not isinstance(out[0][1], tuple) and out[0][1] != "br":
        out[0] = (out[0][0].lstrip(), out[0][1])
    if out and not isinstance(out[-1][1], tuple) and out[-1][1] != "br":
        out[-1] = (out[-1][0].rstrip(), out[-1][1])
    return out


def read_epub(path):
    book = Book()
    z = zipfile.ZipFile(path)
    container = z.read("META-INF/container.xml").decode("utf-8", "replace")
    opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
    opf = decode(z.read(opf_path))
    t = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.S)
    a = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf, re.S)
    l = re.search(r"<dc:language[^>]*>(.*?)</dc:language>", opf, re.S)
    book.title = html.unescape(t.group(1).strip()).rstrip(" .…") if t else ""
    book.author = html.unescape(a.group(1).strip()) if a else ""
    book.lang = (l.group(1).strip() if l else "fr")[:2]
    items = {}
    for m in re.finditer(r"<item\b[^>]*>", opf):
        tag = m.group(0)
        i = re.search(r'\sid="([^"]+)"', tag)
        h = re.search(r'\shref="([^"]+)"', tag)
        if i and h:
            items[i.group(1)] = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), unquote(h.group(1))))
    spine = [items[i] for i in re.findall(r'<itemref\b[^>]*\sidref="([^"]+)"', opf) if i in items]

    docs = []
    for p in spine:
        root = ET.fromstring(entities(decode(z.read(p))).encode("utf-8"))
        body = root.find(XHTML + "body")
        if body is not None:
            docs.append((p, body))

    # 1. notes : id de la note → n° définitif, dans l'ordre des appels
    notemap, order = {}, 0
    note_ids = {}
    for p, body in docs:
        for el in body.iter():
            if lname(el) == "p" and "note" in classes(el):
                ids = [x.get("id") for x in el.iter() if x.get("id") and x.get("id").startswith("note")]
                for i in ids:
                    note_ids[i] = el
    for p, body in docs:
        for el in body.iter():
            if lname(el) == "sup" and len(el) and lname(el[0]) == "a":
                tgt = (el[0].get("href") or "").lstrip("#")
                if tgt in note_ids and tgt not in notemap:
                    order += 1
                    notemap[tgt] = order
    note_of_el = {}
    for tgt, n in notemap.items():
        note_of_el[id(note_ids[tgt])] = n

    # 2. blocs
    chapter = 0
    for p, body in docs:
        if not any(("".join(e.itertext())).strip() for e in body.iter()):
            continue                                   # page d'image seule (couverture)
        for el in body.iter():
            n = lname(el)
            if n not in BLOCK or n in ("div", "ul", "ol", "table"):
                continue
            if any(lname(c) in ("p", "h1", "h2", "h3", "li") for c in el):
                continue                               # conteneur : ses enfants sont traités
            if n in ("h1", "h2"):
                chapter += 1
            if n == "p" and "note" in classes(el):
                num = note_of_el.get(id(el))
                runs = clean_runs(runs_of(el, notemap))
                # le numéro imprimé (« 1. ») et la ponctuation finale de l'OCR (« , » « .. »)
                if runs and isinstance(runs[0][0], str):
                    runs[0] = (re.sub(r"^\s*\(?\d{1,3}[.)]\s*", "", runs[0][0]), runs[0][1])
                if runs:
                    last = re.sub(r"\s*[,;]\s*$", ".", runs[-1][0])
                    last = re.sub(r"\.{2}$", ".", last)
                    runs[-1] = (last, runs[-1][1])
                runs = clean_runs(runs)
                if num is None:
                    order += 1
                    num = order
                book.notes[num] = runs
                book.note_chapter[num] = chapter
                continue
            if n == "hr":
                book.blocks.append((chapter, {"kind": "hr", "cls": set(), "runs": []}))
                continue
            runs = clean_runs(runs_of(el, notemap))
            if not runs:
                continue
            kind = n if n in ("h1", "h2", "h3", "h4") else "p"
            book.blocks.append((chapter, {"kind": kind, "cls": classes(el), "runs": runs, "src": p}))
    return book


# --------------------------------------------------------------------------
# Texte brut
# --------------------------------------------------------------------------

def plain_runs(runs, italic="_"):
    out = []
    for t, s in runs:
        if s == "br":
            out.append("\n")
        elif isinstance(s, tuple):
            out.append("[%d]" % s[1])
        elif s == "i" and t.strip():
            lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", t, re.S).groups()
            out.append("%s%s%s%s%s" % (lead, italic, core, italic, trail))
        elif s == "sup":
            out.append(t)
        else:
            out.append(t)
    text = "".join(out).replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"_(\s*)_", r"\1", text)            # italiques contiguës fusionnées


def wrap(text, width, indent=""):
    lines = []
    for part in text.split("\n"):
        lines += textwrap.wrap(part, width=width, initial_indent=indent, subsequent_indent=indent,
                               break_long_words=False, break_on_hyphens=False) or [""]
    return lines


def center(text, width):
    return [l.strip().center(width).rstrip() for l in wrap(text, width - 4)]


def to_text(book, width, note_txt, title_lines):
    out = []

    def blank(n):
        while out and out[-1] == "":
            out.pop()
        out.extend([""] * n)

    # page de titre
    for b in title_lines:
        out += center(plain_runs(b["runs"], ""), width) if b["kind"] != "hr" else [""]
        out.append("")
    current = None
    pending_notes = []

    def flush_notes():
        if not pending_notes:
            return
        blank(1)
        for n in pending_notes:
            text = "[%d] %s" % (n, plain_runs(book.notes[n]))
            first, *rest = wrap(text, width) or [""]
            out.append(first)
            out.extend(("    " + l.strip()) if l else l for l in rest)
            out.append("")
        pending_notes.clear()

    for chapter, b in book.blocks:
        if b.get("title_page"):
            continue
        if chapter != current:
            flush_notes()
            current = chapter
        k = b["kind"]
        text = plain_runs(b["runs"])
        notes_here = [s[1] for _, s in b["runs"] if isinstance(s, tuple)]
        if k in ("h1", "h2"):
            blank(4)
            out += center(text, width)
            blank(2)
        elif k in ("h3", "h4"):
            blank(2)
            out += center(text, width)
            blank(1)
        elif k == "hr":
            blank(1)
            out.append("*       *       *       *       *".center(width).rstrip())
            blank(1)
        elif "sommaire" in b["cls"]:
            out += wrap(text, width - 8, "    ")
            out.append("")
        elif b["cls"] & {"centre", "place", "publisher", "year"} or re.fullmatch(r"FIN\b.*", text.strip()):
            out += center(text, width)
            out.append("")
        elif "vers" in b["cls"]:
            out += ["    " + l for l in text.split("\n")]
            out.append("")
        else:
            out += wrap(text, width)
            out.append("")
        pending_notes.extend(notes_here)
    flush_notes()
    if note_txt:
        blank(4)
        out.append("NOTE DE TRANSCRIPTION".center(width).rstrip())
        out.append("")
        for para in note_txt:
            out += wrap(para, width)
            out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\r\n".join(out) + "\r\n"


# --------------------------------------------------------------------------
# HTML5
# --------------------------------------------------------------------------

CSS = """
body { margin-left: 10%; margin-right: 10%; }
h1, h2, h3 { text-align: center; clear: both; font-weight: normal; }
h1 { font-size: 2em; margin: 1em 0 0.5em; }
h2 { font-size: 1.5em; margin-top: 3em; margin-bottom: 1em; page-break-before: always; }
h3 { font-size: 1.2em; }
p { margin: 0.75em 0; text-indent: 1.5em; text-align: justify; }
p.center, p.titlepage { text-indent: 0; text-align: center; }
p.summary { text-indent: 0; margin: 0 10% 2em; font-style: italic; font-size: 0.95em; }
p.verse { text-indent: 0; margin-left: 3em; text-align: left; }
hr.tb { width: 30%; margin: 2em auto; }
hr.chap { width: 60%; margin: 3em auto 1em; clear: both; }
.titlepage { margin: 3em 0; }
.fnanchor { vertical-align: super; font-size: 0.75em; text-decoration: none; }
.footnotes { border-top: 1px solid #999; margin: 2em 10% 1em; font-size: 0.9em; }
.footnote p { text-indent: 0; margin: 0.5em 0 0.5em 2em; }
.footnote .label { margin-left: -2em; display: inline-block; width: 2em; }
.transnote { background-color: #eee; border: 1px dashed #999; margin: 3em 10%; padding: 0.5em 1em; }
.transnote p { text-indent: 0; }
"""


def html_runs(runs):
    out = []
    for t, s in runs:
        if s == "br":
            out.append("<br>\n")
        elif isinstance(s, tuple):
            n = s[1]
            out.append('<a id="FNanchor_%d" href="#Footnote_%d" class="fnanchor">[%d]</a>' % (n, n, n))
        elif s == "i":
            out.append("<i>%s</i>" % html.escape(t, quote=False))
        elif s == "b":
            out.append("<b>%s</b>" % html.escape(t, quote=False))
        elif s == "sup":
            out.append("<sup>%s</sup>" % html.escape(t, quote=False))
        else:
            out.append(html.escape(t, quote=False))
    return re.sub(r"</i>(\s*)<i>", r"\1", "".join(out))


def to_html(book, title_lines, note_txt):
    e = html.escape
    title = book.title or "Sans titre"
    out = ["<!DOCTYPE html>", '<html lang="%s">' % book.lang, "<head>", '<meta charset="utf-8">',
           "<title>%s%s</title>" % (e(title), (" | " + e(book.author)) if book.author else ""),
           '<style>%s</style>' % CSS, "</head>", "<body>"]
    if title_lines:
        out.append('<div class="titlepage">')
        first = True
        for b in title_lines:
            if b["kind"] == "hr":
                out.append('<hr class="tb">')
                continue
            if first:
                out.append("<h1>%s</h1>" % html_runs(b["runs"]))
                first = False
            else:
                out.append('<p class="titlepage">%s</p>' % html_runs(b["runs"]))
        out.append("</div>")
    current, pending = None, []

    def flush():
        if not pending:
            return
        out.append('<div class="footnotes">')
        for n in pending:
            out.append('<div class="footnote"><p id="Footnote_%d"><a href="#FNanchor_%d" class="label">[%d]</a> %s</p></div>'
                       % (n, n, n, html_runs(book.notes[n])))
        out.append("</div>")
        pending.clear()

    for chapter, b in book.blocks:
        if b.get("title_page"):
            continue
        if chapter != current:
            flush()
            current = chapter
        k = b["kind"]
        body = html_runs(b["runs"])
        notes_here = [s[1] for _, s in b["runs"] if isinstance(s, tuple)]
        if k in ("h1", "h2"):
            out.append('<hr class="chap">')
            out.append("<h2>%s</h2>" % body)
        elif k in ("h3", "h4"):
            out.append("<h3>%s</h3>" % body)
        elif k == "hr":
            out.append('<hr class="tb">')
        elif "sommaire" in b["cls"]:
            out.append('<p class="summary">%s</p>' % body)
        elif "vers" in b["cls"]:
            out.append('<p class="verse">%s</p>' % body)
        elif b["cls"] & {"centre", "place", "publisher", "year"} or re.fullmatch(r"FIN\b.*", "".join(t for t, _ in b["runs"]).strip()):
            out.append('<p class="center">%s</p>' % body)
        else:
            out.append("<p>%s</p>" % body)
        pending.extend(notes_here)
    flush()
    if note_txt:
        out.append('<div class="transnote">')
        out.append("<p><b>Note de transcription</b></p>")
        for para in note_txt:
            out.append("<p>%s</p>" % e(para, quote=False))
        out.append("</div>")
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="EPUB → texte et HTML5 pour Project Gutenberg.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", required=True, help="nom de base des fichiers produits")
    ap.add_argument("--width", type=int, default=72, help="longueur maximale des lignes du texte (défaut 72)")
    ap.add_argument("--title-file", default="titre",
                    help="fichier de la page de titre dans l'EPUB (début du nom ; défaut « titre »)")
    ap.add_argument("--note", action="append", default=[],
                    help="paragraphe de la note de transcription (répétable)")
    opts = ap.parse_args()

    book = read_epub(opts.epub)
    # page de titre : blocs du fichier de titre
    title_lines = []
    for chapter, b in book.blocks:
        if os.path.basename(b.get("src", "")).startswith(opts.title_file):
            b["title_page"] = True
            title_lines.append(b)
    # les blocs de la page de titre ne comptent pas comme chapitre
    if title_lines:
        first_ch = min(ch for ch, b in book.blocks if b.get("title_page"))
        if any(b["kind"] in ("h1", "h2") for b in title_lines):
            pass
    notes = list(opts.note)
    if book.notes:
        notes.append("Les notes, numérotées page par page dans l'imprimé, sont numérotées de 1 à %d "
                     "et placées à la fin de chaque chapitre." % len(book.notes))

    txt = to_text(book, opts.width, notes, title_lines)
    with open(opts.output + ".txt", "w", encoding="utf-8", newline="") as f:
        f.write(txt)
    page = to_html(book, title_lines, notes)
    with open(opts.output + ".html", "w", encoding="utf-8") as f:
        f.write(page)

    lines = txt.split("\r\n")
    longest = max(len(l) for l in lines)
    print("Texte : %s.txt — %d lignes, la plus longue : %d caractères" % (opts.output, len(lines), longest))
    print("HTML  : %s.html — %d blocs, %d notes" % (opts.output, len(book.blocks), len(book.notes)))


if __name__ == "__main__":
    main()
