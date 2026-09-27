#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_to_epub.py — Transforme le PDF d'un livre numérisé en EPUB « brut »
que la chaîne Prescel sait ensuite traiter (structure, s long, découpage,
relecture).

Trois sources de texte, choisies page par page (--source auto) :
  alto  PDF de Gallica dont le document a été océrisé : l'OCR de la BnF est
        récupéré en ALTO (mots, positions, confiance, césures, marges déjà
        séparées) — bien meilleur que la couche texte du PDF, qui perd les
        espaces entre les mots ;
  text  couche texte du PDF (PDF natif, Internet Archive…) ;
  ocr   pas de texte : OCR Tesseract sur l'image de la page (ou sur l'image
        pleine résolution de Gallica avec --iiif).

La géométrie remplace les devinettes : titres courants et signatures (bandes
haute et basse), manchettes (hors de la colonne), paragraphes (retrait,
ligne courte, interligne), césures (fin de ligne), lettrines (hauteur),
paragraphes qui continuent sur la page suivante. Les numéros de page du livre
papier sont posés (liste des pages du toc.ncx) ; pour Gallica, la pagination
officielle est reprise et les pages de reliure sont ignorées.

Les mots dont l'OCR est peu sûr sont entourés de <span class="a-verifier">
(recherche « a-verifier » dans Sigil ; retirés par epub_review.py --unmark).

Dépendance : PyMuPDF (pip install pymupdf). OCR : Tesseract avec les modèles
« fra » et/ou « frm » (moyen français, lit le s long ſ).

Usage :
  python3 pdf_to_epub.py livre.pdf -o livre.epub
  python3 pdf_to_epub.py livre.pdf -o livre.epub --source ocr --lang fra --iiif
  python3 pdf_to_epub.py livre.pdf -o livre.epub --pages 10-40
"""

import argparse
import collections
import concurrent.futures
import datetime
import html
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
import xml.etree.ElementTree as ET

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf  # anciennes versions
    except ImportError:
        pymupdf = None

UA = "Mozilla/5.0 (Prescel; import de livres anciens)"
GALLICA = "https://gallica.bnf.fr"
SKIP_PAGE = re.compile(r"plat|contreplat|garde|dos\b|tranche|[ée]tui|charni[èe]re|reliure|mire|blanc", re.I)
TERMINAL = re.compile(r"[.!?:»]\s*$")
CSS = """/* Généré par pdf_to_epub.py */
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
# Modèle intermédiaire : pages → lignes → mots
# --------------------------------------------------------------------------

class Word:
    __slots__ = ("text", "x0", "y0", "x1", "y1", "conf", "subs", "hyp")

    def __init__(self, text, x0, y0, x1, y1, conf=1.0, subs=None, hyp=None):
        self.text, self.x0, self.y0, self.x1, self.y1 = text, x0, y0, x1, y1
        self.conf, self.subs, self.hyp = conf, subs, hyp


class Line:
    def __init__(self, words, zone="body"):
        self.words = [w for w in words if w.text]
        self.zone = zone
        self.x0 = min(w.x0 for w in self.words)
        self.x1 = max(w.x1 for w in self.words)
        self.y0 = min(w.y0 for w in self.words)
        self.y1 = max(w.y1 for w in self.words)

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def height(self):
        return self.y1 - self.y0


class Page:
    def __init__(self, index):
        self.index = index            # page du PDF, base 0
        self.view = None              # vue Gallica (f…)
        self.label = str(index + 1)   # numéro imprimé
        self.width = self.height = 1.0
        self.lines = []
        self.kind = "text"            # text | image | skip | empty
        self.source = None
        self.image = None             # (octets, extension) pour une planche


# --------------------------------------------------------------------------
# Gallica : identifiant, pagination, ALTO, images IIIF
# --------------------------------------------------------------------------

def http_get(url, tries=3, delay=0.4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            time.sleep(delay)            # politesse envers le serveur
            return data
        except Exception as e:           # réseau, 5xx…
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def is_gallica_pdf(doc):
    md = doc.metadata or {}
    return "Bibliothèque nationale de France" in (md.get("creator") or "") or \
        (doc.page_count and "gallica.bnf.fr" in doc[0].get_text())


def find_ark(pdf_path, doc, explicit=None):
    if explicit:
        m = re.search(r"(bpt6k\w+|btv1b\w+|\w{10,})", explicit.split("/")[-1] if "/" in explicit else explicit)
        return m.group(1) if m else explicit
    m = re.search(r"(bpt6k\w+|btv1b\w+)", os.path.basename(pdf_path))
    if m:
        return m.group(1)
    for i in range(min(2, doc.page_count)):
        m = re.search(r"ark:/12148/(\w+)", doc[i].get_text())
        if m:
            return m.group(1)
    return None


def gallica_prefix_pages(doc):
    """Pages ajoutées par Gallica en tête du PDF (notice, conditions d'utilisation)."""
    n = 0
    for i in range(min(3, doc.page_count)):
        t = doc[i].get_text()
        if "gallica.bnf.fr" in t or "Conditions d'utilisation" in t or "Les contenus accessibles" in t:
            n = i + 1
    return n


def gallica_pagination(ark, cache):
    path = os.path.join(cache, "pagination.xml")
    if not os.path.exists(path):
        data = http_get("%s/services/Pagination?ark=%s" % (GALLICA, ark))
        with open(path, "wb") as f:
            f.write(data)
    t = open(path, encoding="utf-8").read()
    has_text = "<hasContent>true</hasContent>" in t
    labels = [html.unescape(x) for x in re.findall(r"<numero>([^<]*)</numero>", t)]
    return labels, has_text


def gallica_alto(ark, view, cache):
    path = os.path.join(cache, "alto-%04d.xml" % view)
    if not os.path.exists(path):
        data = http_get("%s/RequestDigitalElement?O=%s&E=ALTO&Deb=%d" % (GALLICA, ark, view))
        with open(path, "wb") as f:
            f.write(data)
    return path


def gallica_image(ark, view, cache):
    path = os.path.join(cache, "iiif-%04d.jpg" % view)
    if not os.path.exists(path):
        data = http_get("%s/iiif/ark:/12148/%s/f%d/full/full/0/native.jpg" % (GALLICA, ark, view))
        with open(path, "wb") as f:
            f.write(data)
    return path


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_alto(path, page):
    root = ET.parse(path).getroot()
    pg = next((e for e in root.iter() if local(e.tag) == "Page"), None)
    if pg is None:
        return
    page.width = float(pg.get("WIDTH") or 1)
    page.height = float(pg.get("HEIGHT") or 1)

    def walk(el, zone):
        for ch in el:
            name = local(ch.tag)
            z = {"TopMargin": "top", "BottomMargin": "bottom", "LeftMargin": "margin",
                 "RightMargin": "margin", "PrintSpace": "body"}.get(name, zone)
            if name == "TextLine":
                words = []
                for s in ch:
                    if local(s.tag) != "String":
                        continue
                    x = float(s.get("HPOS", 0)); y = float(s.get("VPOS", 0))
                    w = float(s.get("WIDTH", 0)); h = float(s.get("HEIGHT", 0))
                    st = s.get("SUBS_TYPE")
                    words.append(Word(s.get("CONTENT", ""), x, y, x + w, y + h,
                                      float(s.get("WC", 1) or 1), s.get("SUBS_CONTENT"),
                                      {"HypPart1": 1, "HypPart2": 2}.get(st)))
                if words and any(w.text for w in words):
                    page.lines.append(Line(words, z))
            else:
                walk(ch, z)
    walk(pg, "body")
    page.source = "alto"


# --------------------------------------------------------------------------
# Couche texte du PDF et OCR
# --------------------------------------------------------------------------

def text_layer_quality(doc, indices):
    """(proportion de « mots » de plus de 14 lettres, nombre de caractères).
    La couche texte des PDF Gallica colle beaucoup de mots (« principalesdulieuqu'ils ») :
    au-delà de 2 % de mots très longs, elle est inutilisable."""
    chars, words = 0, []
    for i in indices[:: max(1, len(indices) // 20)]:
        t = doc[i].get_text()
        chars += len(t)
        words += [w for w in t.split() if re.search(r"[A-Za-zÀ-ÿ]", w)]
    long_ratio = sum(len(w) > 14 for w in words) / len(words) if words else 1.0
    return long_ratio, chars


def text_layer_usable(doc, indices):
    long_ratio, chars = text_layer_quality(doc, indices)
    return chars > 150 * max(1, min(20, len(indices))) and long_ratio < 0.02


def parse_text_layer(doc, page):
    p = doc[page.index]
    page.width, page.height = p.rect.width, p.rect.height
    groups = collections.OrderedDict()
    for x0, y0, x1, y1, txt, b, l, _n in p.get_text("words"):
        groups.setdefault((b, l), []).append(Word(txt, x0, y0, x1, y1))
    for words in groups.values():
        page.lines.append(Line(words))
    page.source = "text"


def page_image(doc, page, cache, ark, iiif):
    if iiif and ark and page.view:
        return gallica_image(ark, page.view, cache)
    p = doc[page.index]
    imgs = p.get_images(full=True)
    path = os.path.join(cache, "page-%04d" % (page.index + 1))
    if imgs:
        best = max(imgs, key=lambda im: im[2] * im[3])
        info = doc.extract_image(best[0])
        path += "." + info["ext"]
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(info["image"])
    else:
        path += ".png"
        if not os.path.exists(path):
            p.get_pixmap(dpi=300).save(path)
    return path


def run_tesseract(img, base, lang, tessdata):
    env = dict(os.environ)
    if tessdata:
        env["TESSDATA_PREFIX"] = tessdata
    if not os.path.exists(base + ".hocr"):
        # -c plutôt que la config « hocr » : fonctionne aussi avec un dossier de modèles
        # personnel qui n'a pas de sous-dossier configs/
        r = subprocess.run(["tesseract", img, base, "-l", lang, "-c", "tessedit_create_hocr=1",
                            "-c", "tessedit_create_txt=0"], capture_output=True, env=env)
        if r.returncode != 0 or not os.path.exists(base + ".hocr"):
            raise RuntimeError("Tesseract : " + r.stderr.decode("utf-8", "replace").strip()[:300])
    return base + ".hocr"


def parse_hocr(path, page):
    t = open(path, encoding="utf-8").read()
    m = re.search(r"class=['\"]ocr_page['\"][^>]*?title=(?:'[^']*?|\"[^\"]*?)bbox (\d+) (\d+) (\d+) (\d+)", t)
    if m:
        page.width, page.height = float(m.group(3)), float(m.group(4))
    for lm in re.finditer(r"<span class=['\"]ocr_(?:line|caption|header|textfloat)['\"][^>]*>(.*?)</span>\s*(?=<span class=['\"]ocr_(?:line|caption|header|textfloat)|</p>)", t, re.S):
        words = []
        for wm in re.finditer(r"<span class=['\"]ocrx_word['\"][^>]*title=['\"]bbox (\d+) (\d+) (\d+) (\d+); x_wconf (\d+)['\"][^>]*>(.*?)</span>", lm.group(1), re.S):
            txt = html.unescape(re.sub(r"<[^>]+>", "", wm.group(6))).strip()
            if txt:
                x0, y0, x1, y1 = map(float, wm.group(1, 2, 3, 4))
                words.append(Word(txt, x0, y0, x1, y1, int(wm.group(5)) / 100.0))
        if words:
            page.lines.append(Line(words))
    page.source = "ocr"


# --------------------------------------------------------------------------
# Reconstruction par la géométrie
# --------------------------------------------------------------------------

def median(vals, default=1.0):
    vals = [v for v in vals if v > 0]
    return statistics.median(vals) if vals else default


def classify_page(page):
    """Bandes haute/basse et manchettes quand la source ne les donne pas (texte, OCR)."""
    body = [l for l in page.lines if l.zone == "body"]
    if not body:
        return
    body.sort(key=lambda l: (l.y0, l.x0))
    widths = [l.x1 - l.x0 for l in body]
    colw = sorted(widths)[int(len(widths) * 0.8)] if widths else page.width
    long_lines = [l for l in body if (l.x1 - l.x0) >= 0.6 * colw] or body
    left = median([l.x0 for l in long_lines], 0)
    right = median([l.x1 for l in long_lines], page.width)
    colw = max(1.0, right - left)
    h = median([l.height for l in long_lines], 10)
    page.col = (left, right, h, colw)
    if page.source == "alto":
        top_given = True
    else:
        top_given = False
    # Bandes haute et basse : tout ce qui est au-dessus de la première ligne pleine
    # (ou sous la dernière) et reste court est titre courant, folio, signature ou
    # réclame. L'ALTO de Gallica les sépare déjà (TopMargin / BottomMargin).
    if not top_given and len(body) > 3:
        full = [l for l in body if (l.x1 - l.x0) >= 0.6 * colw]
        if full:
            first_full, last_full = min(full, key=lambda l: l.y0), max(full, key=lambda l: l.y1)
            for l in body:
                short = (l.x1 - l.x0) < 0.55 * colw or len(l.text) < 12
                if l.y1 <= first_full.y0 + 0.3 * h and short and l.y0 < 0.25 * page.height:
                    l.zone = "top"
                elif l.y0 >= last_full.y1 - 0.3 * h and short and l.y1 > 0.75 * page.height:
                    l.zone = "bottom"
            # une ligne de titre courant pleine largeur (« VOYAGE DV GEN. BEAVLIEV 12 »)
            first = min((l for l in body if l.zone == "body"), key=lambda l: l.y0, default=None)
            if first is not None and first.y0 < 0.18 * page.height and re.search(r"\b\d{1,4}\b", first.text):
                letters = [c for c in first.text if c.isalpha()]
                if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
                    first.zone = "top"
    # manchettes : hors de la colonne principale
    for l in body:
        if l.zone != "body":
            continue
        w = l.x1 - l.x0
        if w < 0.45 * colw and (l.x1 <= left + 0.2 * colw and l.x0 < left - 0.02 * colw or
                                 l.x0 >= right - 0.2 * colw and l.x1 > right + 0.02 * colw):
            l.zone = "margin"


class Builder:
    """Assemble les paragraphes de toutes les pages, dans l'ordre de lecture."""

    def __init__(self, mark_conf):
        self.mark_conf = mark_conf
        self.blocks = []            # {"type": p|centre|marge|image, "parts": [...]}
        self.open_p = None          # paragraphe en cours (peut continuer page suivante)
        self.hyphen = None          # fragment de mot coupé en fin de ligne, ou "\x00" (ALTO)
        self.margin_queue = []      # manchettes à placer après le paragraphe en cours
        self.dropped = collections.Counter()
        self.low_conf = 0
        self.lettrine = None

    # -- blocs ---------------------------------------------------------------
    def emit(self, block):
        self.blocks.append(block)
        return block

    def flush_margins(self):
        for m in self.margin_queue:
            self.emit(m)
        self.margin_queue = []

    def new_block(self, kind):
        self.flush_hyphen()
        if self.open_p is not None:
            self.flush_margins()
        self.open_p = self.emit({"type": kind, "parts": []})
        return self.open_p

    def close(self):
        self.flush_hyphen()
        self.open_p = None
        self.flush_margins()

    def flush_hyphen(self):
        if self.hyphen and self.hyphen != "\x00" and self.open_p is not None:
            self.add_words(self.open_p, [(self.hyphen + "-", 1.0)])
        self.hyphen = None

    @staticmethod
    def anchor(page):
        return ("anchor", "page-%s" % (page.view or page.index + 1))

    def add_words(self, block, words):
        for t, conf in words:
            if any(p[0] in ("text", "doubt") for p in block["parts"]):
                block["parts"].append(("text", " "))
            if self.mark_conf and conf < self.mark_conf and len(t) > 1:
                block["parts"].append(("doubt", t, conf))
                self.low_conf += 1
            else:
                block["parts"].append(("text", t))

    def last_text(self):
        parts = [p for p in (self.open_p or {}).get("parts", []) if p[0] in ("text", "doubt")]
        return parts[-1][1] if parts else ""

    # -- une ligne -----------------------------------------------------------
    def words_of(self, line):
        """Mots de la ligne, en recollant la césure de la ligne précédente."""
        out = []
        carry, self.hyphen = self.hyphen, None
        for i, w in enumerate(line.words):
            t = w.text
            if i == 0 and carry:
                if carry == "\x00":
                    if w.hyp == 2:
                        continue            # mot complet déjà donné par SUBS_CONTENT
                else:
                    t = carry + t
            out.append((t, w.conf))
        if out:
            lw = line.words[-1]
            last_t, last_c = out[-1]
            if lw.hyp == 1 and lw.subs:
                out[-1] = (lw.subs, last_c)
                self.hyphen = "\x00"
            elif re.search(r"[A-Za-zÀ-ÿſ][-¬]$", last_t) and len(last_t) > 2:
                out.pop()
                self.hyphen = last_t[:-1]
        return out

    @staticmethod
    def attach_lettrines(body, h):
        """Lettrine (une capitale seule, plus haute qu'une ligne, à gauche du texte) :
        rattachée au premier mot de la première ligne qu'elle accompagne."""
        out = []
        for l in body:
            t = l.text.strip()
            if len(t) == 1 and t.isalpha() and t.isupper() and l.height > 1.15 * h:
                beside = [o for o in body if o is not l and o.x0 > l.x1 - 2
                          and l.y0 - 3.5 * h < o.y0 < l.y1 + 0.5 * h and o.words]
                if beside:
                    tgt = min(beside, key=lambda o: o.y0)
                    w = tgt.words[0]
                    if w.text[:1].isupper():
                        w.text = t + w.text
                        continue
            out.append(l)
        return out

    def margin_notes(self, page):
        """Lignes de manchette voisines regroupées en une seule note (césures recollées)."""
        notes, cur, last = [], [], None
        for m in sorted((l for l in page.lines if l.zone == "margin"), key=lambda l: l.y0):
            if last is not None and (m.y0 - last.y1 > 1.2 * max(1, last.height) or
                                     abs(m.x0 - last.x0) > 3 * max(1, last.height)):
                notes.append(cur)
                cur = []
            cur.append(m)
            last = m
        if cur:
            notes.append(cur)
        for lines in notes:
            words = []
            for ln in lines:
                ws = [(w.text, w.conf) for w in ln.words]
                if words and ws and re.search(r"[-¬]$", words[-1][0]):
                    words[-1] = (words[-1][0][:-1] + ws[0][0], min(words[-1][1], ws[0][1]))
                    ws = ws[1:]
                words += ws
            yield words

    # -- une page ------------------------------------------------------------
    def page(self, page):
        if page.kind == "skip":
            return
        if page.kind == "image":
            self.close()
            b = self.emit({"type": "image", "parts": [self.anchor(page)], "image": page.image})
            return
        left, right, h, colw = getattr(page, "col", (0, page.width, 10, page.width))
        cw = colw / 60.0                       # largeur approximative d'un caractère
        body = sorted([l for l in page.lines if l.zone == "body"], key=lambda l: (l.y0, l.x0))
        body = self.attach_lettrines(body, h)
        for l in page.lines:
            if l.zone in ("top", "bottom"):
                self.dropped[l.text] += 1
        anchor_done = False
        prev = None
        for line in body:
            text = line.text.strip()
            if not text:
                continue
            tall = line.height > 1.9 * h
            if tall and len(text) == 1 and text.isalpha():
                self.close()
                self.lettrine = text            # lettrine : rattachée à la ligne suivante
                prev = line
                continue
            indent = line.x0 - left
            centred = indent > 0.12 * colw and (right - line.x1) > 0.12 * colw and len(text) < 80
            gap = (line.y0 - prev.y1) if prev is not None else 0
            starts_new = (
                self.open_p is None or centred or tall
                or (1.2 * cw < indent < 0.3 * colw and
                    (prev is None or line.x0 - prev.x0 > 1.2 * cw))
                or (prev is not None and gap > 1.6 * h)
                or (prev is not None and prev.x1 < right - 5 * cw and TERMINAL.search(prev.text))
                or (prev is None and TERMINAL.search(self.last_text()) and indent > 0.6 * cw)
            )
            if starts_new:
                self.new_block("centre" if centred else "p")
            if not anchor_done:
                self.open_p["parts"].append(self.anchor(page))
                anchor_done = True
            words = self.words_of(line)
            if self.lettrine and words:
                words[0] = (self.lettrine + words[0][0], words[0][1])
                self.lettrine = None
            self.add_words(self.open_p, words)
            if centred:
                self.close()
            prev = line
        if not anchor_done:                    # page sans texte courant
            target = self.open_p or (self.blocks[-1] if self.blocks else None)
            if target is None or target["type"] == "image":
                target = self.emit({"type": "p", "parts": []})
            target["parts"].append(self.anchor(page))
        for words in self.margin_notes(page):
            blk = {"type": "marge", "parts": []}
            self.add_words(blk, words)
            if self.open_p is None:
                self.emit(blk)
            else:
                self.margin_queue.append(blk)

    def finish(self):
        self.close()


# --------------------------------------------------------------------------
# Écriture de l'EPUB
# --------------------------------------------------------------------------

def esc(s):
    return html.escape(s, quote=False)


def render_block(b, img_names):
    parts = []
    for p in b["parts"]:
        if p[0] == "text":
            parts.append(esc(p[1]))
        elif p[0] == "doubt":
            parts.append('<span class="a-verifier" title="OCR peu sûr (%d %%)">%s</span>'
                         % (round(p[2] * 100), esc(p[1])))
        elif p[0] == "anchor":
            parts.append('<a id="%s"></a>' % p[1])
    inner = "".join(parts).strip()
    inner = re.sub(r" {2,}", " ", inner)
    if b["type"] == "image":
        name = img_names.get(id(b))
        return '<div class="image">%s<img src="../Images/%s" alt="" /></div>' % (inner, name)
    if not re.sub(r"<[^>]+>", "", inner).strip():
        return '<div>%s</div>' % inner if inner else ""
    cls = {"marge": ' class="marge"', "centre": ' class="centre"'}.get(b["type"], "")
    return "<p%s>%s</p>" % (cls, inner)


XHTML_HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>%s</title>
  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />
</head>
<body>
"""


def write_epub(out_path, blocks, pages, meta, per_file):
    book_id = meta.get("identifier") or "urn:uuid:" + str(uuid.uuid4())
    title = meta.get("title") or "Livre"
    # images de planches
    img_names, images = {}, []
    for b in blocks:
        if b["type"] == "image" and b.get("image"):
            data, ext = b["image"]
            name = "planche-%03d.%s" % (len(images) + 1, "jpg" if ext in ("jpeg", "jpg") else ext)
            img_names[id(b)] = name
            images.append((name, data))
    # regroupement en fichiers : on ne coupe qu'entre deux blocs
    files, cur = [], []
    for b in blocks:
        cur.append(b)
        if len(cur) >= per_file and b["type"] != "marge":
            files.append(cur)
            cur = []
    if cur:
        files.append(cur)
    xhtml, page_targets = [], []
    for i, group in enumerate(files, 1):
        name = "texte-%03d.xhtml" % i
        body = "\n".join(x for x in (render_block(b, img_names) for b in group) if x)
        xhtml.append((name, XHTML_HEAD % esc(title) + body + "\n</body>\n</html>\n"))
        for b in group:
            for p in b["parts"]:
                if p[0] == "anchor":
                    page_targets.append((name, p[1]))
    labels = {"page-%s" % (p.view or p.index + 1): p.label for p in pages}

    manifest = ['    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '    <item id="css" href="Styles/livre.css" media-type="text/css"/>']
    spine = []
    for i, (name, _) in enumerate(xhtml, 1):
        manifest.append('    <item id="t%03d" href="Text/%s" media-type="application/xhtml+xml"/>' % (i, name))
        spine.append('    <itemref idref="t%03d"/>' % i)
    for i, (name, _) in enumerate(images, 1):
        mt = "image/jpeg" if name.endswith(".jpg") else "image/" + name.rsplit(".", 1)[1]
        manifest.append('    <item id="img%03d" href="Images/%s" media-type="%s"/>' % (i, name, mt))
    metas = []
    if meta.get("source"):
        metas.append("    <dc:source>%s</dc:source>" % esc(meta["source"]))
    if meta.get("scan_url"):
        metas.append('    <meta name="prescel:scan-url" content="%s"/>' % html.escape(meta["scan_url"]))
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>%s</dc:title>
    <dc:creator opf:role="aut">%s</dc:creator>
    <dc:language>%s</dc:language>
    <dc:identifier id="bookid">%s</dc:identifier>
    <dc:date>%s</dc:date>
%s
  </metadata>
  <manifest>
%s
  </manifest>
  <spine toc="ncx">
%s
  </spine>
</package>
""" % (esc(title), esc(meta.get("author") or "Inconnu"), meta.get("language", "fr"), esc(book_id),
       datetime.date.today().isoformat(), "\n".join(metas), "\n".join(manifest), "\n".join(spine))

    nav, order = [], 0
    for i, (name, _) in enumerate(xhtml, 1):
        order += 1
        first = next((l for n, a in page_targets if n == name for l in [labels.get(a)] if l), "")
        nav.append('    <navPoint id="nav-%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
                   '<content src="Text/%s"/></navPoint>'
                   % (order, order, esc("Partie %d (p. %s)" % (i, first) if first else "Partie %d" % i), name))
    plist = []
    for k, (name, aid) in enumerate(page_targets, 1):
        lab = labels.get(aid, aid[5:])
        typ = "normal" if lab.isdigit() else "front"
        val = ' value="%s"' % lab if lab.isdigit() else ""
        plist.append('    <pageTarget id="pt-%d" type="%s"%s playOrder="%d"><navLabel><text>%s</text></navLabel>'
                     '<content src="Text/%s#%s"/></pageTarget>' % (k, typ, val, order + k, esc(lab), name, aid))
    maxnum = max([int(labels[a]) for _, a in page_targets if labels.get(a, "").isdigit()] or [0])
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="%s"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="%d"/>
    <meta name="dtb:maxPageNumber" content="%d"/>
  </head>
  <docTitle><text>%s</text></docTitle>
  <navMap>
%s
  </navMap>
  <pageList>
    <navLabel><text>Pages</text></navLabel>
%s
  </pageList>
</ncx>
""" % (esc(book_id), len(page_targets), maxnum, esc(title), "\n".join(nav), "\n".join(plist))
    # playOrder : les pages suivent l'ordre de lecture, avec les entrées de navMap
    ncx = renumber(ncx, xhtml)

    fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   '</rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/Styles/livre.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        for name, text in xhtml:
            z.writestr("OEBPS/Text/" + name, text, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in images:
            z.writestr("OEBPS/Images/" + name, data, compress_type=zipfile.ZIP_STORED)
    os.chmod(tmp, 0o644)
    os.replace(tmp, out_path)
    return len(xhtml), len(page_targets), len(images)


def renumber(ncx, xhtml):
    """playOrder = ordre de lecture (fichier, puis position de l'ancre)."""
    order = {name: i for i, (name, _) in enumerate(xhtml)}
    pos = {}
    for name, text in xhtml:
        for m in re.finditer(r'id="([^"]+)"', text):
            pos[(name, m.group(1))] = m.start()
    pat = re.compile(r'<(navPoint|pageTarget)\b[^>]*playOrder="\d+"[^>]*>.*?<content src="Text/([^"#]+)(?:#([^"]+))?"', re.S)
    keys = []
    for m in pat.finditer(ncx):
        keys.append((order.get(m.group(2), 0), pos.get((m.group(2), m.group(3)), -1) if m.group(3) else -1))
    rank = {k: i + 1 for i, k in enumerate(sorted(set(keys)))}
    it = iter(keys)
    return pat.sub(lambda m: re.sub(r'playOrder="\d+"', 'playOrder="%d"' % rank[next(it)], m.group(0), count=1), ncx)


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def parse_range(spec, n):
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a) - 1, min(n, int(b))))
        elif part.strip():
            out.append(int(part) - 1)
    return [i for i in out if 0 <= i < n]


def metadata_from(doc, ark):
    meta = {"language": "fr"}
    md = doc.metadata or {}
    meta["title"] = (md.get("title") or "").strip()
    meta["author"] = (md.get("author") or "").strip()
    if doc.page_count > 1:
        t = doc[1].get_text()
        m = re.search(r"^(.+?)\.\s*Auteur du texte", t, re.S | re.M)
        if m and not meta["author"]:
            meta["author"] = " ".join(m.group(1).split())
    if ark:
        meta["source"] = "%s/ark:/12148/%s" % (GALLICA, ark)
        meta["identifier"] = meta["source"]
        meta["scan_url"] = meta["source"] + "/f{page}.item"
    return meta


def main():
    ap = argparse.ArgumentParser(description="PDF de livre numérisé → EPUB brut pour Prescel.")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", required=True, help="EPUB à produire")
    ap.add_argument("--source", choices=["auto", "alto", "text", "ocr"], default="auto")
    ap.add_argument("--ark", help="identifiant Gallica (bpt6k…, btv1b…) si le nom du fichier ne le donne pas")
    ap.add_argument("--lang", default="fra", help="langue(s) Tesseract : fra, frm, fra+frm…")
    ap.add_argument("--tessdata", help="dossier des modèles Tesseract (sinon TESSDATA_PREFIX)")
    ap.add_argument("--iiif", action="store_true",
                    help="OCR sur l'image pleine résolution de Gallica plutôt que celle du PDF")
    ap.add_argument("--pages", help="pages du PDF à traiter, ex. 3-120 (défaut : toutes)")
    ap.add_argument("--cache", help="dossier de cache (ALTO, images, OCR) ; défaut : <sortie>.cache")
    ap.add_argument("--mark-conf", type=float, default=None,
                    help="entourer les mots dont la confiance OCR est sous ce seuil, de 0 à 1 "
                         "(0 = jamais ; défaut : 0,5 pour l'ALTO, 0,4 pour Tesseract)")
    ap.add_argument("--keep-furniture", action="store_true",
                    help="garder titres courants et signatures (en manchette)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                    help="OCR en parallèle (défaut : cœurs - 1)")
    ap.add_argument("--per-file", type=int, default=400, help="blocs par fichier XHTML")
    opts = ap.parse_args()

    if pymupdf is None:
        sys.exit("PyMuPDF est nécessaire : pip install pymupdf")
    doc = pymupdf.open(opts.pdf)
    cache = opts.cache or re.sub(r"\.epub$", "", opts.output) + ".cache"
    os.makedirs(cache, exist_ok=True)
    ark = find_ark(opts.pdf, doc, opts.ark)
    prefix = gallica_prefix_pages(doc) if (ark or is_gallica_pdf(doc)) else 0
    if not ark and is_gallica_pdf(doc):
        print("PDF de Gallica sans identifiant dans son nom : indiquez --ark (ex. bpt6k9627352r) "
              "pour utiliser l'OCR de la BnF et la pagination.")
    meta = metadata_from(doc, ark)
    print("PDF : %d pages%s" % (doc.page_count, (" — Gallica %s (%d pages de notice ignorées)" % (ark, prefix)) if ark else ""))

    pages = [Page(i) for i in range(doc.page_count)]
    for p in pages[:prefix]:
        p.kind = "skip"

    # Pagination Gallica : numéros imprimés, pages de reliure
    has_alto = False
    if ark:
        try:
            labels, has_alto = gallica_pagination(ark, cache)
            n_views = doc.page_count - prefix
            if len(labels) == n_views:
                for v, lab in enumerate(labels, 1):
                    p = pages[prefix + v - 1]
                    p.view, p.label = v, lab.strip() or str(v)
                    if SKIP_PAGE.search(lab):
                        p.kind = "skip"
                print("Pagination Gallica : %d vues, OCR BnF %s" % (n_views, "disponible" if has_alto else "absent"))
            else:
                print("Avertissement : le PDF (%d vues) ne couvre pas tout le document (%d) : "
                      "pagination d'origine non reprise." % (n_views, len(labels)))
                has_alto = False
        except Exception as e:
            print("Avertissement : Gallica injoignable (%s) ; on continue sans." % e)

    wanted = set(parse_range(opts.pages, doc.page_count))
    todo = [p for p in pages if p.index in wanted and p.kind != "skip"]
    for p in pages:
        if p.index not in wanted:
            p.kind = "skip"

    source = opts.source
    if source == "auto":
        if has_alto:
            source = "alto"
        else:
            source = "text" if text_layer_usable(doc, [p.index for p in todo] or [0]) else "ocr"
    print("Source du texte : %s" % {"alto": "ALTO de Gallica (OCR BnF)", "text": "couche texte du PDF",
                                     "ocr": "OCR Tesseract (%s)" % opts.lang}[source])
    if source == "ocr" and not shutil.which("tesseract"):
        sys.exit("Tesseract est introuvable : installez-le (paquet tesseract-ocr) ou choisissez une autre source.")

    t0 = time.time()
    if source == "alto":
        for k, p in enumerate(todo, 1):
            try:
                parse_alto(gallica_alto(ark, p.view, cache), p)
            except Exception as e:
                print("  vue %s : ALTO indisponible (%s)" % (p.view, e))
            if k % 20 == 0 or k == len(todo):
                print("  ALTO %d/%d" % (k, len(todo)), flush=True)
    elif source == "text":
        for p in todo:
            parse_text_layer(doc, p)
    else:
        def job(p):
            img = page_image(doc, p, cache, ark, opts.iiif)
            hocr = run_tesseract(img, os.path.join(cache, "ocr-%04d-%s" % (p.index + 1, opts.lang.replace("+", "_"))),
                                 opts.lang, opts.tessdata)
            parse_hocr(hocr, p)
            return p
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=opts.workers) as ex:
            for fut in concurrent.futures.as_completed([ex.submit(job, p) for p in todo]):
                fut.result()
                done += 1
                if done % 5 == 0 or done == len(todo):
                    el = time.time() - t0
                    print("  OCR %d/%d — %.0f s écoulées, reste ~%.0f s"
                          % (done, len(todo), el, el / done * (len(todo) - done)), flush=True)

    # Pages sans texte : planche (image) ou page blanche
    for p in todo:
        body = [l for l in p.lines if len(l.text.strip()) > 2]
        if len(" ".join(l.text for l in body)) < 30:
            imgs = doc[p.index].get_images(full=True)
            if imgs and not (p.view and SKIP_PAGE.search(p.label or "")):
                best = max(imgs, key=lambda im: im[2] * im[3])
                info = doc.extract_image(best[0])
                p.kind, p.image = "image", (info["image"], info["ext"])
                p.lines = []
            else:
                p.kind = "empty"
        else:
            classify_page(p)
            if opts.keep_furniture:
                for l in p.lines:
                    if l.zone in ("top", "bottom"):
                        l.zone = "margin"

    mark = opts.mark_conf if opts.mark_conf is not None else (0.4 if source == "ocr" else 0.5)
    b = Builder(mark)
    for p in pages:
        if p.kind in ("text", "image"):
            b.page(p)
        elif p.kind == "empty":
            p.kind = "text"
            b.page(p)
    b.finish()

    if not ark:
        # numéros imprimés repérés dans les titres courants
        for p in pages:
            nums = [re.search(r"\b(\d{1,4})\b", l.text) for l in p.lines if l.zone == "top"]
            nums = [m.group(1) for m in nums if m]
            if nums:
                p.label = nums[0]
    if not meta.get("title"):
        meta["title"] = os.path.splitext(os.path.basename(opts.pdf))[0]
    nfiles, npages, nimg = write_epub(opts.output, b.blocks, pages, meta, opts.per_file)

    paras = sum(1 for x in b.blocks if x["type"] in ("p", "centre"))
    marg = sum(1 for x in b.blocks if x["type"] == "marge")
    print("Pages traitées : %d (%d planches, %d ignorées)" % (len(todo), nimg,
          sum(1 for p in pages if p.kind == "skip")))
    print("Paragraphes : %d — manchettes : %d — mots peu sûrs signalés : %d" % (paras, marg, b.low_conf))
    if b.dropped:
        print("Titres courants, folios et signatures retirés : %d lignes" % sum(b.dropped.values()))
        print("   " + ", ".join("« %s »×%d" % (k, v) if v > 1 else "« %s »" % k
                                for k, v in b.dropped.most_common(25)))
    print("Durée : %.0f s" % (time.time() - t0))
    print("EPUB écrit : %s (%d fichiers, %d pages repérées)" % (opts.output, nfiles, npages))


if __name__ == "__main__":
    main()
