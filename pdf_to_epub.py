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
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
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
# apparat critique en bas de page (éditions savantes : Kervyn de Lettenhove, Luce…) :
# « 1-2 Gens. 3-4 Viel. 5-6 Chose. » — l'OCR lit souvent le tiret « _ » ou « . »
APPARATUS = re.compile(r"(?:^|\s)(?<!pp\.\s)(?<!p\.\s)\d{1,2}\s?[-_–—]\s?\d{1,2}\b|^\d{1,2}\s+[A-ZÀ-Ý]")
# note de bas de page numérotée « (1) … », que l'OCR lit souvent « (i) », « (I) », « (l) », « (2") »
NOTE_START = re.compile(r"""^\(\s*([0-9iIl]{1,2})\s*["”'’]?\s*\)""")
NOTE_CALL = re.compile(r"""^\(([0-9iIl]{1,2})["”'’]?\)([.,;:!?»]*)$""")


def note_num(s):
    return re.sub(r"[iIl]", "1", s)


# appel de variante : nombre isolé de 1 ou 2 chiffres dans le texte courant (« ses 1 princes »)
CALL = re.compile(r"^(\d{1,2})([.,;:!?»)]*)$")
# appel collé au mot par l'OCR : « jours10 », « Or3 », « porteroient6plus »
GLUED_CALL = re.compile(r"^([^\W\d_]{2,})(\d{1,2})([^\W\d_]{2,})?([.,;:!?»]*)$")
CSS = """/* Généré par pdf_to_epub.py */
body { margin: 0 1em; font-family: serif; }
p { margin: 0 0 0.6em 0; text-indent: 0; text-align: justify; }
h1, h2, h3, h4 { text-align: center; margin: 1em 0 0.6em 0; }
.marge { font-size: 85%; font-style: italic; margin: 0.2em 0 0.2em 2em; text-align: left; }
.centre { text-align: center; }
.droite { text-align: right; }
.image { text-align: center; margin: 1em 0; }
p.vers { text-align: left; margin: 0 0 1em 2em; }
table.tableau { border-collapse: collapse; margin: 1em 0; font-size: 90%; }
table.tableau td { border: 1px solid #aaa; padding: 0.2em 0.4em; vertical-align: top; }
ol.liste, ul.liste { list-style: none; margin: 0.5em 0 1em 1em; padding: 0; }
ol.liste li, ul.liste li { margin: 0.2em 0; text-indent: -1em; padding-left: 1em; }
img { max-width: 100%; max-height: 100%; }
p.variantes { font-size: 80%; text-indent: 0; margin: 0.3em 0 1em 0; border-top: 1px solid #ccc; padding-top: 0.2em; }
sup.var { font-size: 65%; line-height: 0; color: #666; }
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

# Délai entre deux requêtes à Gallica : il s'allonge quand le serveur répond « trop de
# requêtes » (HTTP 429) et raccourcit doucement ensuite, sans descendre sous le minimum.
PACE = {"delay": 1.0, "min": 1.0, "max": 20.0, "throttled": 0}


class Throttled(Exception):
    """Gallica refuse encore après toutes les tentatives (429 / 503)."""


def http_get(url, tries=8, check=None):
    """Télécharge url. Les refus temporaires (429, 502, 503, 504, page d'erreur au lieu du
    document) sont retentés avec une attente croissante (en-tête Retry-After respecté)."""
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if check is not None and not check(data):
                raise urllib.error.HTTPError(url, 503, "réponse inattendue (page d'erreur ?)", None, None)
            time.sleep(PACE["delay"])                  # politesse envers le serveur
            PACE["delay"] = max(PACE["min"], PACE["delay"] * 0.95)
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                raise
            if e.code in (429, 502, 503, 504):
                PACE["throttled"] += 1
                PACE["delay"] = min(PACE["max"], PACE["delay"] * 2)
                ra = (e.headers or {}).get("Retry-After") if e.headers is not None else None
                wait = int(ra) if ra and str(ra).strip().isdigit() else min(300, 10 * 2 ** k)
                print("  Gallica : %s (HTTP %d) — pause de %d s, puis une requête toutes les %.0f s"
                      % ("trop de requêtes" if e.code == 429 else "serveur occupé", e.code, wait,
                         PACE["delay"]), flush=True)
                time.sleep(wait)
                continue
            time.sleep(2 * (k + 1))
        except Exception as e:                         # réseau, délai dépassé…
            last = e
            time.sleep(min(60, 3 * 2 ** k))
    if isinstance(last, urllib.error.HTTPError) and last.code in (429, 502, 503, 504):
        raise Throttled(str(last))
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


def alto_ok(data):
    return b"<alto" in data[:3000] and b"</alto>" in data[-200:]


def gallica_alto(ark, view, cache):
    path = os.path.join(cache, "alto-%04d.xml" % view)
    if os.path.exists(path):
        with open(path, "rb") as f:
            if alto_ok(f.read()):
                return path
        os.remove(path)                    # page d'erreur ou fichier tronqué gardé par erreur
    data = http_get("%s/RequestDigitalElement?O=%s&E=ALTO&Deb=%d" % (GALLICA, ark, view), check=alto_ok)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def alto_bytes(path):
    """Contenu de l'ALTO prêt pour le parseur. Gallica annonce « ISO-8859-1 » mais envoie
    souvent de l'UTF-8 : lu tel quel, « é » deviendrait « Ã© ». Si le texte est de l'UTF-8
    valide, la déclaration est corrigée."""
    with open(path, "rb") as f:
        data = f.read()
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    if m and m.group(1).lower() not in (b"utf-8", b"utf8"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return data                     # vraiment en Latin-1
        if re.search(rb"[\x80-\xff]", data):
            data = data[:m.start(1)] + b"UTF-8" + data[m.end(1):]
    return data


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
    root = ET.fromstring(alto_bytes(path))
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

    def __init__(self, mark_conf, variantes=False, line_quotes=True):
        self.mark_conf = mark_conf
        self.variantes = variantes      # apparat en bas de page → <p class="variantes">, appels en exposant
        self.line_quotes = line_quotes  # retirer les « répétés en tête de ligne dans une citation
        self.n_variantes = self.n_calls = self.n_quotes = 0
        self.footnotes = False          # notes « (1) … » en bas de page → <p class="note">
        self.n_notes = 0
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

    def text_target(self):
        """Où ajouter du texte dans le bloc ouvert (dernier élément de liste, dernière cellule)."""
        b = self.open_p
        if b is None:
            return None
        if b["type"] == "list":
            return b["items"][-1] if b.get("items") else None
        if b["type"] == "table":
            return b["rows"][-1][-1] if b.get("rows") else None
        return b

    def flush_hyphen(self):
        tgt = self.text_target()
        if self.hyphen and self.hyphen != "\x00" and tgt is not None:
            self.add_words(tgt, [(self.hyphen + "-", 1.0)])
        self.hyphen = None

    @staticmethod
    def anchor(page):
        return ("anchor", "page-%s" % (page.view or page.index + 1))

    def add_words(self, block, words, calls=False):
        for t, conf in words:
            nc = NOTE_CALL.match(t) if self.footnotes and block.get("type") == "p" else None
            if nc:
                # « (i) » → « (1) », collé au mot qui précède pour que l'appel soit reconnu
                if block["parts"] and block["parts"][-1][0] in ("text", "doubt"):
                    block["parts"].append(("text", " (%s)%s" % (note_num(nc.group(1)), nc.group(2))))
                else:
                    block["parts"].append(("text", "(%s)%s" % (note_num(nc.group(1)), nc.group(2))))
                continue
            g = GLUED_CALL.match(t) if calls else None
            if g:
                # le mot, l'appel, puis l'éventuel mot suivant collé
                self.add_words(block, [(g.group(1), conf)])
                block["parts"].append(("call", g.group(2)))
                self.n_calls += 1
                if g.group(3):
                    self.add_words(block, [(g.group(3) + g.group(4), conf)])
                elif g.group(4):
                    block["parts"].append(("text", g.group(4)))
                continue
            m = CALL.match(t) if calls else None
            if m and any(p[0] in ("text", "doubt") for p in block["parts"]):
                block["parts"].append(("call", m.group(1)))     # collé au mot qui précède
                if m.group(2):
                    block["parts"].append(("text", m.group(2)))
                self.n_calls += 1
                continue
            if any(p[0] in ("text", "doubt") for p in block["parts"]) and block["parts"][-1][0] != "br":
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
        words = list(line.words)
        if carry and carry != "\x00" and len(words) > 1 and words[0].text in ("«", "»"):
            # « des-⏎« confis » : le guillemet de début de ligne s'intercale dans le mot coupé
            words = words[1:]
        for i, w in enumerate(words):
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
            head = lw.text[:-1] if lw.text.endswith(("-", "¬")) else None
            if lw.hyp == 1 and lw.subs and head and not re.search(r"[A-Za-zÀ-ÿ]", lw.subs[len(head):] or "x"):
                # SUBS_CONTENT faux (« des« ») : la seconde moitié est le mot qui suit le
                # guillemet de la ligne suivante
                out.pop()
                self.hyphen = head
            elif lw.hyp == 1 and lw.subs:
                subs = lw.subs
                if head and subs.startswith(head) and subs[len(head):len(head) + 1].isupper():
                    subs = head + "-" + subs[len(head):]    # « Nostre-Dame » : vrai trait d'union
                out[-1] = (subs, last_c)
                self.hyphen = "\x00"
            elif re.search(r"[A-Za-zÀ-ÿſ][-¬]$", last_t) and len(last_t) > 2:
                out.pop()
                self.hyphen = last_t[:-1]
        return out

    @staticmethod
    def apparatus_lines(body, h, pitch=None):
        """Dernier groupe de lignes du bas de page, séparé du texte par un grand blanc : apparat
        critique (variantes) ou notes. Liste vide s'il n'y en a pas.
        pitch : interligne du texte courant (médiane du livre). L'apparat, composé plus petit,
        a un interligne plus serré : c'est le signe le plus sûr, qui permet aussi de reconnaître
        une longue variante (« Sec. réd. ») qui occupe la moitié de la page."""
        body = [l for l in body if l.text.strip()]
        if len(body) < 3:
            return []
        steps = [b.y0 - a.y0 for a, b in zip(body, body[1:]) if 0 < b.y0 - a.y0 < 3 * h]
        pitch = pitch or median(steps, 1.3 * h)
        top, bottom = body[0].y0, body[-1].y1
        found = None
        for i in range(1, len(body)):
            if body[i].y0 - body[i - 1].y0 <= 1.45 * pitch:
                continue
            group = body[i:]
            while len(group) > 1 and Builder.caps_line(group[-1]):
                group = group[:-1]                  # « FIN DU TOME XII. » sous l'apparat
            letters = [c for c in " ".join(l.text for l in group) if c.isalpha()]
            if not letters or sum(c.isupper() for c in letters) / len(letters) > 0.6:
                continue                            # « FIN DU TOME XII. », titre en capitales
            gsteps = [b.y0 - a.y0 for a, b in zip(group, group[1:]) if 0 < b.y0 - a.y0 < 3 * h]
            # interligne serré sur tout le groupe, sans autre grand blanc (sinon c'est le blanc
            # suivant qui sépare le texte de l'apparat : intertitre au milieu de la page)
            small = len(gsteps) >= 2 and median(gsteps) <= 0.92 * pitch and max(gsteps) <= 1.45 * pitch
            low = group[0].y0 >= top + 0.4 * (bottom - top)
            big = body[i].y0 - body[i - 1].y0 > 1.8 * pitch
            numbered = any(APPARATUS.search(l.text) for l in group)
            if small:
                return group                        # composé plus petit : c'est l'apparat
            if low and (big or numbered) and len(group) <= 16:
                found = group                       # sinon le dernier grand blanc du bas de page
        return found or []

    @staticmethod
    def caps_line(line):
        letters = [c for c in line.text if c.isalpha()]
        return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.8

    def quote_depth(self):
        """Guillemets ouverts et pas encore fermés dans le paragraphe en cours."""
        t = "".join(p[1] for p in (self.open_p or {}).get("parts", []) if p[0] in ("text", "doubt"))
        return t.count("«") - t.count("»")

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

    @staticmethod
    def verse_lines(body, typical, h):
        """Vers : au moins 3 lignes de suite nettement plus courtes que la justification
        habituelle du livre, commençant par une capitale, à interligne régulier."""
        def short(l):
            t = l.text.strip()
            return (l.x1 - l.x0) < 0.72 * typical and len(t) >= 8 and (t[:1].isupper() or t[:1] in "«“\"'")
        found, run = set(), []
        for l in body + [None]:
            if l is not None and short(l) and (not run or l.y0 - run[-1].y1 < 1.3 * h):
                run.append(l)
                continue
            if len(run) >= 3:
                found.update(id(x) for x in run)
            run = [l] if l is not None and short(l) else []
        return found

    @staticmethod
    def cells_of(line, colw, h):
        """Découpe une ligne en cellules aux grands blancs (bien plus larges qu'une espace)."""
        gap_min = max(0.06 * colw, 1.6 * h)
        cells, cur = [], [line.words[0]]
        for a, b in zip(line.words, line.words[1:]):
            if b.x0 - a.x1 > gap_min:
                cells.append(cur)
                cur = [b]
            else:
                cur.append(b)
        cells.append(cur)
        return cells

    def table_lines(self, body, colw, h):
        """Tableaux : au moins 3 lignes voisines coupées en 2 cellules ou plus par de grands
        blancs, dont les colonnes s'alignent. Renvoie {id(ligne): (n° du tableau, cellules)}."""
        out, runs, run = {}, [], []
        for l in body:
            cells = self.cells_of(l, colw, h)
            near = run and l.y0 - run[-1][0].y1 < 2.2 * h
            if len(cells) >= 2:
                if not near and run:
                    runs.append(run)
                    run = []
                run.append((l, cells))
            elif near and run and len(run) >= 2:
                run.append((l, cells))          # ligne d'une seule cellule au milieu d'un tableau
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        tid = 0
        for run in runs:
            while run and len(run[-1][1]) < 2:
                run.pop()
            if sum(1 for _, c in run if len(c) >= 2) < 3:
                continue
            # colonnes : débuts de cellules regroupés (tolérance 5 % de la justification)
            starts = sorted(c[0].x0 for _, cells in run for c in cells)
            cols = []
            for x in starts:
                if not cols or x - cols[-1][-1] > 0.05 * colw:
                    cols.append([x])
                else:
                    cols[-1].append(x)
            cols = [min(c) for c in cols if len(c) >= 2] or [min(c) for c in cols]
            if len(cols) < 2:
                continue
            tid += 1
            for l, cells in run:
                row = [None] * len(cols)
                for c in cells:
                    k = max((i for i, x in enumerate(cols) if x <= c[0].x0 + 0.05 * colw), default=0)
                    row[k] = (row[k] or []) + c
                out[id(l)] = (tid, row)
        return out

    @staticmethod
    def list_lines(body, left, colw, h):
        """Listes : au moins 3 lignes de suite qui commencent par une marque (« 1. », « a) »,
        « — », « • ») au même retrait ; les lignes entre deux marques, plus en retrait, sont
        la suite de l'élément. Renvoie {id(ligne): ("item"|"cont", n° de liste, numérotée)}."""
        mark = re.compile(r"^(?:(\d{1,3})[.)°]|[a-z][.)]|[•·–—*-])\s")
        out, lid = {}, 0
        i = 0
        while i < len(body):
            l = body[i]
            m = mark.match(l.text)
            if not m or l.x0 > left + 0.15 * colw:
                i += 1
                continue
            x_mark = l.x0
            items, j = [], i
            while j < len(body):
                lj = body[j]
                mj = mark.match(lj.text)
                if mj and abs(lj.x0 - x_mark) < 0.03 * colw:
                    items.append((j, "item"))
                elif items and not mj and lj.x0 > x_mark + 0.01 * colw and \
                        lj.y0 - body[j - 1].y1 < 1.2 * h:
                    items.append((j, "cont"))
                else:
                    break
                j += 1
            if sum(1 for _, k in items if k == "item") >= 3:
                lid += 1
                ordered = bool(m.group(1))
                for k, kind in items:
                    out[id(body[k])] = (kind, lid, ordered)
                i = j
            else:
                i += 1
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
            self.emit({"type": "image", "parts": [self.anchor(page)], "image": page.image})
            return
        left, right, h, colw = getattr(page, "col", (0, page.width, 10, page.width))
        cw = colw / 60.0                       # largeur approximative d'un caractère
        body = sorted([l for l in page.lines if l.zone == "body"], key=lambda l: (l.y0, l.x0))
        notes = []
        if self.footnotes:
            grp = self.apparatus_lines(body, h, getattr(self, "pitch", None))
            if grp and NOTE_START.match(grp[0].text.strip()):
                notes = grp
                body = [l for l in body if l not in notes]
        app = []
        self.page_var = self.variantes and page.index not in getattr(self, "no_apparatus", ())
        if self.page_var:
            app = self.apparatus_lines(body, h, getattr(self, "pitch", None))
            body = [l for l in body if l not in app]
        body = self.attach_lettrines(body, h)
        verse = self.verse_lines(body, getattr(page, "typical", colw), h)
        tables = self.table_lines([l for l in body if id(l) not in verse], colw, h)
        lists = self.list_lines([l for l in body if id(l) not in verse and id(l) not in tables],
                                left, colw, h)
        for l in page.lines:
            if l.zone in ("top", "bottom"):
                self.dropped[l.text] += 1
        anchor_done = False
        prev = None
        for line in body:
            text = line.text.strip()
            if not text:
                continue
            if id(line) in tables:
                tid, cells = tables[id(line)]
                blk = self.open_p
                if blk is None or blk["type"] != "table" or blk.get("tid") != (page.index, tid):
                    blk = self.new_block("table")
                    blk["tid"], blk["rows"] = (page.index, tid), []
                row = []
                for cell in cells:
                    c = {"parts": []}
                    if cell is not None:
                        self.add_words(c, [(w.text, w.conf) for w in cell])
                    row.append(c)
                if not anchor_done:
                    row[0]["parts"].insert(0, self.anchor(page))
                    anchor_done = True
                blk["rows"].append(row)
                self.hyphen = None
                prev = line
                continue
            if id(line) in lists:
                kind, lid, ordered = lists[id(line)]
                blk = self.open_p
                if blk is None or blk["type"] != "list" or blk.get("lid") != (page.index, lid):
                    if kind == "cont" and blk is not None and blk["type"] == "list":
                        pass                     # suite d'élément sur la page suivante
                    else:
                        blk = self.new_block("list")
                        blk["lid"], blk["items"], blk["ordered"] = (page.index, lid), [], ordered
                if kind == "item" or not blk["items"]:
                    self.flush_hyphen()          # mot coupé en fin d'élément : on le garde tel quel
                    blk["items"].append({"parts": []})
                item = blk["items"][-1]
                if not anchor_done:
                    item["parts"].append(self.anchor(page))
                    anchor_done = True
                self.add_words(item, self.words_of(line))
                prev = line
                continue
            if self.open_p is not None and self.open_p["type"] in ("table", "list"):
                self.close()
            if id(line) in verse:
                # vers : une ligne = un vers ; nouvelle strophe si retrait ou blanc
                gap = (line.y0 - prev.y1) if prev is not None else 0
                new_stanza = (self.open_p is None or self.open_p["type"] != "vers" or
                              gap > 1.2 * h or (prev is not None and line.x0 - prev.x0 > 1.5 * cw
                                                and id(prev) in verse and prev.x0 < line.x0))
                if new_stanza:
                    self.new_block("vers")
                else:
                    self.open_p["parts"].append(("br",))
                if not anchor_done:
                    self.open_p["parts"].append(self.anchor(page))
                    anchor_done = True
                self.hyphen = None
                self.add_words(self.open_p, [(w.text, w.conf) for w in line.words])
                prev = line
                continue
            if self.open_p is not None and self.open_p["type"] == "vers":
                self.close()
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
            if self.line_quotes and not starts_new and len(words) > 1 and words[0][0] == "«" \
                    and self.quote_depth() > 0:
                words = words[1:]                    # « répété en tête de ligne dans une citation
                self.n_quotes += 1
            self.add_words(self.open_p, words, calls=self.page_var)
            if centred:
                self.close()
            prev = line
        if not anchor_done:                    # page sans texte courant
            target = self.open_p or (self.blocks[-1] if self.blocks else None)
            if target is None or target["type"] == "image":
                target = self.emit({"type": "p", "parts": []})
            target["parts"].append(self.anchor(page))
        if notes:
            cur, carry = None, None
            for ln in notes:
                m = NOTE_START.match(ln.text.strip())
                ws = [(w.text, w.conf) for w in ln.words]
                if m or cur is None:
                    cur = {"type": "note", "parts": []}
                    if m:
                        # « (i) » en tête de note → « (1) »
                        k = 0
                        acc = ""
                        while k < len(ws) and not acc.endswith(")"):
                            acc += ws[k][0]
                            k += 1
                        ws = [("(%s)" % note_num(m.group(1)), 1.0)] + ws[k:]
                    self.n_notes += 1
                    if self.open_p is None:
                        self.emit(cur)
                    else:
                        self.margin_queue.append(cur)
                if carry and ws:
                    ws[0] = (carry + ws[0][0], ws[0][1])
                    carry = None
                if ws and re.search(r"[A-Za-zÀ-ÿ][-¬]$", ws[-1][0]):
                    carry = ws.pop()[0][:-1]
                self.add_words(cur, ws)
        if app:
            blk = {"type": "variantes", "page": page.label, "parts": []}
            words, carry = [], None
            for k, ln in enumerate(app):
                ws = [(w.text, w.conf) for w in ln.words]
                if self.line_quotes and k and len(ws) > 1 and ws[0][0] == "«":
                    t = " ".join(x[0] for x in words)
                    if t.count("«") > t.count("»"):
                        ws = ws[1:]
                        self.n_quotes += 1
                if carry and ws:
                    ws[0] = (carry + ws[0][0], min(ws[0][1], 1.0))
                    carry = None
                if ws and re.search(r"[A-Za-zÀ-ÿ][-¬]$", ws[-1][0]) and ln is not app[-1]:
                    carry = ws.pop()[0][:-1]
                words += ws
            # « 1_2 », « 3.4 », « 5—6 » : intervalle d'appels imprimé « 1-2 »
            words = [(re.sub(r"^(\d{1,2})[_.–—](\d{1,2})$", r"\1-\2", t), c) for t, c in words]
            self.add_words(blk, words)
            self.n_variantes += 1
            if self.open_p is None:
                self.emit(blk)
            else:
                self.margin_queue.append(blk)
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


def block_parts(b):
    """Toutes les parties d'un bloc, y compris celles des cellules et des éléments de liste."""
    out = list(b.get("parts", []))
    for row in b.get("rows", []):
        for c in row:
            out += c["parts"]
    for it in b.get("items", []):
        out += it["parts"]
    return out


def render_parts(parts):
    out = []
    for p in parts:
        if p[0] == "text":
            out.append(esc(p[1]))
        elif p[0] == "doubt":
            out.append('<span class="a-verifier" title="OCR peu sûr (%d %%)">%s</span>'
                       % (round(p[2] * 100), esc(p[1])))
        elif p[0] == "anchor":
            out.append('<a id="%s"></a>' % p[1])
        elif p[0] == "call":
            out.append('<sup class="var">%s</sup>' % p[1])
        elif p[0] == "br":
            out.append("<br />")
    return re.sub(r" {2,}", " ", "".join(out)).strip()


def render_block(b, img_names):
    parts = []
    for p in b["parts"]:
        if p[0] == "text":
            parts.append(esc(p[1]))
        elif p[0] == "doubt":
            parts.append('<span class="a-verifier" title="OCR peu sûr (%d %%)">%s</span>'
                         % (round(p[2] * 100), esc(p[1])))
        elif p[0] == "br":
            parts.append("<br />")
        elif p[0] == "anchor":
            parts.append('<a id="%s"></a>' % p[1])
        elif p[0] == "call":
            parts.append('<sup class="var">%s</sup>' % p[1])
    inner = "".join(parts).strip()
    inner = re.sub(r" {2,}", " ", inner)
    if b["type"] == "table":
        rows = []
        for row in b["rows"]:
            tds = "".join("<td>%s</td>" % render_parts(c["parts"]) for c in row)
            rows.append("<tr>%s</tr>" % tds)
        return '<table class="tableau">\n%s\n</table>' % "\n".join(rows)
    if b["type"] == "list":
        tag = "ol" if b.get("ordered") else "ul"
        lis = "\n".join("<li>%s</li>" % render_parts(it["parts"]) for it in b["items"])
        return '<%s class="liste">\n%s\n</%s>' % (tag, lis, tag)
    if b["type"] == "image":
        name = img_names.get(id(b))
        return '<div class="image">%s<img src="../Images/%s" alt="" /></div>' % (inner, name)
    if not re.sub(r"<[^>]+>", "", inner).strip():
        return '<div>%s</div>' % inner if inner else ""
    if b["type"] == "note":
        return '<p class="note">%s</p>' % inner
    if b["type"] == "variantes":
        return '<p class="variantes" title="p. %s">%s</p>' % (html.escape(str(b.get("page", ""))), inner)
    cls = {"marge": ' class="marge"', "centre": ' class="centre"', "vers": ' class="vers"'}.get(b["type"], "")
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
            for p in block_parts(b):
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

def compact_ranges(nums):
    """[3, 4, 5, 9] → « 3-5, 9 »."""
    out, nums = [], sorted(set(nums))
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else "%d-%d" % (nums[i], nums[j]))
        i = j + 1
    return ", ".join(out)


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
    ap.add_argument("--variantes", choices=["auto", "oui", "non"], default="auto",
                    help="apparat critique en bas de page (« 1-2 Gens. 3-4 Viel. ») mis à part dans "
                         "<p class=\"variantes\">, appels de variante en exposant (auto : si le livre en a)")
    ap.add_argument("--notes", choices=["auto", "oui", "non"], default="auto",
                    help="notes « (1) … » en bas de page mises à part dans <p class=\"note\"> (auto : si le livre en a)")
    ap.add_argument("--garder-guillemets-de-ligne", action="store_true",
                    help="garder les « répétés en tête de chaque ligne d'une citation "
                         "(par défaut retirés : seuls restent l'ouvrant et le fermant)")
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
    missing = []
    if source == "alto":
        for k, p in enumerate(todo, 1):
            try:
                parse_alto(gallica_alto(ark, p.view, cache), p)
            except Exception as e:
                # pas de page perdue : la couche texte du PDF prend le relais (moins bonne,
                # mais mieux qu'une page vide) ; une relance complète la page depuis Gallica
                missing.append(p)
                print("  vue %s : ALTO indisponible (%s) — couche texte du PDF à la place" % (p.view, e),
                      flush=True)
                p.lines = []
                parse_text_layer(doc, p)
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
    widths = sorted(p.col[3] for p in pages if p.kind == "text" and hasattr(p, "col"))
    typical = widths[len(widths) * 3 // 4] if widths else None
    for p in pages:
        if typical and hasattr(p, "col"):
            p.typical = typical
    # Apparat critique : pages dont le bas porte un groupe « 1-2 Gens. 3-4 Viel. »
    app_pages = []
    steps = []
    for p in pages:
        if p.kind == "text" and hasattr(p, "col"):
            body = sorted([l for l in p.lines if l.zone == "body"], key=lambda l: (l.y0, l.x0))[:10]
            steps += [b2.y0 - b1.y0 for b1, b2 in zip(body, body[1:]) if 0 < b2.y0 - b1.y0 < 3 * p.col[2]]
    pitch = median(steps, 0) or None              # interligne du texte courant (haut des pages)
    if opts.variantes != "non":
        for p in pages:
            if p.kind != "text" or not hasattr(p, "col"):
                continue
            body = sorted([l for l in p.lines if l.zone == "body"], key=lambda l: (l.y0, l.x0))
            group = Builder.apparatus_lines(body, p.col[2], pitch)
            if group and any(APPARATUS.search(l.text) for l in group):
                app_pages.append(p.index)
    ntext = sum(1 for p in pages if p.kind == "text")
    note_pages = 0
    if opts.notes != "non":
        for p in pages:
            if p.kind != "text" or not hasattr(p, "col"):
                continue
            body = sorted([l for l in p.lines if l.zone == "body"], key=lambda l: (l.y0, l.x0))
            group = Builder.apparatus_lines(body, p.col[2], pitch)
            if group and NOTE_START.match(group[0].text.strip()):
                note_pages += 1
    use_var = opts.variantes == "oui" or (opts.variantes == "auto" and len(app_pages) >= max(3, 0.15 * ntext))
    b = Builder(mark, variantes=use_var, line_quotes=not opts.garder_guillemets_de_ligne)
    b.pitch = pitch
    b.footnotes = opts.notes == "oui" or (opts.notes == "auto" and note_pages >= 3)
    if b.footnotes:
        print("Notes en bas de page repérées sur %d pages" % note_pages)
    if use_var and app_pages and opts.variantes == "auto":
        # avant la première et après la dernière page à variantes (introduction, notes de
        # l'éditeur, table), un blanc en bas de page n'est pas un apparat
        first, last = min(app_pages), max(app_pages)
        b.no_apparatus = {p.index for p in pages if p.index < first or p.index > last}
        print("Apparat critique repéré : %d pages sur %d (pages imprimées %s à %s)"
              % (len(app_pages), ntext, pages[first].label, pages[last].label))
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

    if use_var:
        print("Variantes : %d blocs mis à part (<p class=\"variantes\">), %d appels en exposant "
              "(<sup class=\"var\">)" % (b.n_variantes, b.n_calls))
    if b.footnotes:
        print("Notes mises à part : %d (<p class=\"note\">)" % b.n_notes)
    if b.n_quotes:
        print("Guillemets répétés en tête de ligne retirés : %d" % b.n_quotes)
    paras = sum(1 for x in b.blocks if x["type"] in ("p", "centre"))
    marg = sum(1 for x in b.blocks if x["type"] == "marge")
    print("Pages traitées : %d (%d planches, %d ignorées)" % (len(todo), nimg,
          sum(1 for p in pages if p.kind == "skip")))
    print("Paragraphes : %d — manchettes : %d — mots peu sûrs signalés : %d" % (paras, marg, b.low_conf))
    if b.dropped:
        print("Titres courants, folios et signatures retirés : %d lignes" % sum(b.dropped.values()))
        print("   " + ", ".join("« %s »×%d" % (k, v) if v > 1 else "« %s »" % k
                                for k, v in b.dropped.most_common(25)))
    if missing:
        print("ATTENTION : %d page(s) sans ALTO (Gallica a refusé ou n'a pas répondu) : vues %s. "
              "Elles viennent de la couche texte du PDF, moins fidèle. Relancez l'import plus tard : "
              "les pages déjà reçues sont gardées dans le cache et seules les manquantes sont "
              "redemandées." % (len(missing), compact_ranges([p.view for p in missing])))
    if PACE["throttled"]:
        print("Gallica a demandé de ralentir %d fois (délai final : %.0f s par page)."
              % (PACE["throttled"], PACE["delay"]))
    print("Durée : %.0f s" % (time.time() - t0))
    print("EPUB écrit : %s (%d fichiers, %d pages repérées)" % (opts.output, nfiles, npages))


if __name__ == "__main__":
    main()
