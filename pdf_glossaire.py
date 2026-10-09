#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_glossaire.py — Glossaire ou vocabulaire imprimé sur deux colonnes, en retrait suspendu
(la vedette commence à la marge de la colonne, la suite de l'article est en retrait), à
partir de la couche texte d'un PDF : un paragraphe par article, la vedette en gras.

  aesier 17540, mettre à l'aise,      → <p class="glossaire"><b>aesier</b> 17540, mettre à
     soulager; part. p. …                   l'aise, soulager; part. p. …</p>

Le titre courant (« 334 VOCABULAIRE. ») est retiré, les mots coupés en fin de ligne sont
recollés, un article qui continue d'une colonne ou d'une page à l'autre reste d'un tenant.
La vedette est le début de l'article jusqu'à la première virgule, au premier nombre ou à la
première parenthèse.

Usage : python3 pdf_glossaire.py livre.pdf -o glossaire.xhtml --pages 340-395 [--titre VOCABULAIRE]
Le fichier écrit est une page XHTML à ajouter à l'EPUB (livres/…-finitions.py).
"""
import argparse
import html
import re
import statistics


def columns(page):
    """Lignes de chaque colonne : [[(y, x0, texte)], [(y, x0, texte)]]."""
    words = [w for w in page.get_text("words") if w[4].strip()]
    if not words:
        return []
    mid = page.rect.width / 2
    cols = [[], []]
    for w in words:
        cols[0 if (w[0] + w[2]) / 2 < mid else 1].append(w)
    out = []
    for ws in cols:
        if not ws:
            out.append([])
            continue
        tol = 0.45 * statistics.median(w[3] - w[1] for w in ws)
        ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
        lines = []
        for w in ws:
            yc = (w[1] + w[3]) / 2
            if lines and abs(yc - lines[-1][0]) <= tol:
                lines[-1][2].append(w)
            else:
                lines.append([yc, 0, [w]])
        res = []
        for yc, _, lw in lines:
            lw.sort(key=lambda w: w[0])
            res.append((yc, lw[0][0], " ".join(w[4] for w in lw)))
        out.append(res)
    return out


def headword(text):
    m = re.match(r"([^\d,(;:]+?)(?=\s*(?:[\d,(;:]|$))", text)
    return (m.group(1).strip(), text[m.end():]) if m and len(m.group(1).strip()) < 40 else ("", text)


def main():
    ap = argparse.ArgumentParser(description="Glossaire sur deux colonnes, en retrait suspendu → XHTML.")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pages", required=True, help="pages du PDF (à partir de 1), ex. 340-395")
    ap.add_argument("--titre", default="VOCABULAIRE")
    ap.add_argument("--premiere-vue", type=int, default=None,
                    help="numéro de vue (ancres page-N) de la première page ; défaut : numéro de page du PDF")
    opts = ap.parse_args()
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    doc = pymupdf.open(opts.pdf)
    a, _, b = opts.pages.partition("-")
    a, b = int(a) - 1, int(b or a)
    u = doc[a].rect.width / 350.0
    entries, cur, carry = [], None, ""
    for i in range(a, b):
        view = (opts.premiere_vue + i - a) if opts.premiere_vue else i + 1
        anchor = '<a id="page-%d"></a>' % view
        for k, col in enumerate(columns(doc[i])):
            if not col:
                continue
            if re.search(r"VOCABULAIRE|GLOSSAIRE|^\d+$", col[0][2]) and col[0][0] < 0.1 * doc[i].rect.height:
                col = col[1:]                                   # titre courant, folio
            if not col:
                continue
            left = min(x for _, x, _ in col)
            for y, x, text in col:
                start = x < left + 3.5 * u
                if carry:
                    text = carry + text.lstrip()
                    carry = ""
                m = re.search(r"([^\W\d_])[-¬]$", text)
                if m:
                    carry, text = text[:-1], ""
                if start or cur is None:
                    if cur is not None:
                        entries.append(cur)
                    cur = {"text": "", "anchors": ""}
                if anchor and k == 0:
                    cur["anchors"] += anchor
                    anchor = ""
                if text:
                    cur["text"] = (cur["text"] + " " + text).strip()
    if carry and cur is not None:
        cur["text"] += " " + carry
    if cur is not None:
        entries.append(cur)

    body = []
    for e in entries:
        hw, rest = headword(e["text"])
        inner = ("<b>%s</b>%s" % (html.escape(hw, quote=False), html.escape(rest, quote=False))) if hw \
            else html.escape(e["text"], quote=False)
        body.append('  <p class="glossaire">%s%s</p>' % (e["anchors"], inner))
    with open(opts.output, "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>%s</title>
  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />
</head>
<body>
  <h1 id="glossaire">%s.</h1>
%s
</body>
</html>
""" % (html.escape(opts.titre.capitalize()), html.escape(opts.titre), "\n".join(body)))
    print("Articles : %d ; écrit %s" % (len(entries), opts.output))


if __name__ == "__main__":
    main()
