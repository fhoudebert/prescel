#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_tesseract.py — Lit avec Tesseract un PDF fait seulement d'images (numérisation Google,
Internet Archive sans texte) et écrit le texte page par page, pour servir de seconde lecture
indépendante à epub_reference.py --confirm.

L'OCR de Tesseract est d'ordinaire moins bonne que celle de Gallica ou de Google : seule, elle ne
corrige rien ; elle confirme une correction quand elle lit la même chose que la référence.

Usage :
  python3 pdf_tesseract.py livre.pdf -o livre-tesseract.txt [--lang fra] [--tessdata DOSSIER]
Le travail est repris là où il s'est arrêté (une page = un fichier dans livre-tesseract.d/).
Il faut Tesseract et son modèle français (paquet tesseract-ocr-fra, ou fra.traineddata
de github.com/tesseract-ocr/tessdata_fast dans --tessdata).
"""
import argparse
import os
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser(description="OCR Tesseract d'un PDF d'images, page par page.")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--lang", default="fra")
    ap.add_argument("--tessdata", help="dossier contenant fra.traineddata")
    ap.add_argument("--scale", type=float, default=0.5,
                    help="réduction des images avant lecture (0.5 : deux fois plus petit, plus rapide)")
    opts = ap.parse_args()
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    from PIL import Image
    doc = pymupdf.open(opts.pdf)
    work = os.path.splitext(opts.output)[0] + ".d"
    os.makedirs(work, exist_ok=True)
    tmp = tempfile.mkdtemp()
    cmd_extra = (["--tessdata-dir", opts.tessdata] if opts.tessdata else []) + ["-l", opts.lang, "--psm", "4"]
    for i in range(doc.page_count):
        out = os.path.join(work, "p%04d.txt" % i)
        if os.path.exists(out):
            continue
        imgs = doc[i].get_images()
        if not imgs:
            open(out, "w").close()
            continue
        pix = pymupdf.Pixmap(doc, imgs[0][0])
        if pix.n > 3 or pix.alpha:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        png = os.path.join(tmp, "p.png")
        pix.save(png)
        im = Image.open(png).convert("L")
        if opts.scale != 1:
            im = im.resize((int(im.size[0] * opts.scale), int(im.size[1] * opts.scale)))
        im.save(png)
        r = subprocess.run(["tesseract", png, "-"] + cmd_extra, capture_output=True, text=True)
        if r.returncode:
            sys.exit("Tesseract : %s" % r.stderr.strip()[:300])
        with open(out + ".part", "w", encoding="utf-8") as f:
            f.write(r.stdout)
        os.replace(out + ".part", out)
        print("page %d/%d" % (i + 1, doc.page_count), flush=True)
    with open(opts.output, "w", encoding="utf-8") as f:
        for i in range(doc.page_count):
            p = os.path.join(work, "p%04d.txt" % i)
            if os.path.exists(p):
                f.write(open(p, encoding="utf-8").read() + "\n")
    print("Texte écrit : %s" % opts.output)


if __name__ == "__main__":
    main()
