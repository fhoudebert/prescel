#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_tesseract.py — Lit avec Tesseract un PDF fait seulement d'images (numérisation Google,
Internet Archive sans texte) ou un DjVu, et écrit le texte page par page, pour servir de seconde
lecture indépendante à epub_reference.py --confirm.

L'OCR de Tesseract est d'ordinaire moins bonne que celle de Gallica ou de Google : seule, elle ne
corrige rien ; elle confirme une correction quand elle lit la même chose que la référence.

Usage :
  python3 pdf_tesseract.py livre.pdf -o livre-tesseract.txt [--lang fra] [--tessdata DOSSIER]
  python3 pdf_tesseract.py livre.djvu -o livre-tesseract.txt --pages 12-475 --jobs 2 --scale 1
Le travail est repris là où il s'est arrêté (une page = un fichier dans livre-tesseract.d/).
Il faut Tesseract et son modèle français (paquet tesseract-ocr-fra, ou fra.traineddata
de github.com/tesseract-ocr/tessdata_fast dans --tessdata) ; pour un DjVu, ddjvu (djvulibre).
Pages (--pages) comptées à partir de 0, comme les vues d'abbyy_to_epub.py.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor


def pages_voulues(spec, n):
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), min(n - 1, int(b or a)) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description="OCR Tesseract d'un PDF d'images ou d'un DjVu, page par page.")
    ap.add_argument("livre", help="PDF ou DjVu")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--lang", default="fra")
    ap.add_argument("--tessdata", help="dossier contenant fra.traineddata")
    ap.add_argument("--scale", type=float, default=0.5,
                    help="réduction des images avant lecture (0.5 : deux fois plus petit, plus rapide)")
    ap.add_argument("--pages", default="", help="pages à lire, par ex. « 12-475 » (défaut : toutes)")
    ap.add_argument("--jobs", type=int, default=1, help="pages lues en parallèle")
    opts = ap.parse_args()
    from PIL import Image
    djvu = opts.livre.lower().endswith(".djvu")
    tmp = tempfile.mkdtemp()
    if djvu:
        lien = os.path.join(tmp, "livre.djvu")              # ddjvu n'aime pas les noms accentués
        os.symlink(os.path.abspath(opts.livre), lien)
        n = int(subprocess.run(["djvused", "-e", "n", lien], capture_output=True, text=True, check=True).stdout)
    else:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        doc = pymupdf.open(opts.livre)
        n = doc.page_count
    work = os.path.splitext(opts.output)[0] + ".d"
    os.makedirs(work, exist_ok=True)
    cmd_extra = (["--tessdata-dir", opts.tessdata] if opts.tessdata else []) + ["-l", opts.lang, "--psm", "4"]
    voulues = pages_voulues(opts.pages, n)

    def image(i, png):
        if djvu:
            pnm = png[:-4] + ".pnm"
            subprocess.run(["ddjvu", "-format=pnm", "-page=%d" % (i + 1), lien, pnm], check=True)
            im = Image.open(pnm).convert("L")
        else:
            imgs = doc[i].get_images()
            if not imgs:
                return False
            pix = pymupdf.Pixmap(doc, imgs[0][0])
            if pix.n > 3 or pix.alpha:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(png)
            im = Image.open(png).convert("L")
        if opts.scale != 1:
            im = im.resize((int(im.size[0] * opts.scale), int(im.size[1] * opts.scale)))
        im.save(png)
        return True

    def lire(i):
        out = os.path.join(work, "p%04d.txt" % i)
        if os.path.exists(out):
            return
        d = tempfile.mkdtemp(dir=tmp)
        png = os.path.join(d, "p.png")
        if not image(i, png):
            open(out, "w").close()
            return
        env = dict(os.environ, OMP_THREAD_LIMIT="1")
        r = subprocess.run(["tesseract", png, "-"] + cmd_extra, capture_output=True, text=True, env=env)
        if r.returncode:
            sys.exit("Tesseract : %s" % r.stderr.strip()[:300])
        with open(out + ".part", "w", encoding="utf-8") as f:
            f.write(r.stdout)
        os.replace(out + ".part", out)
        shutil.rmtree(d, ignore_errors=True)
        print("page %d/%d" % (i + 1, n), flush=True)

    if djvu or opts.jobs <= 1:                                # PyMuPDF n'est pas sûr d'un fil à l'autre
        with ThreadPoolExecutor(max(1, opts.jobs)) as ex:
            list(ex.map(lire, voulues))
    else:
        for i in voulues:
            lire(i)
    with open(opts.output, "w", encoding="utf-8") as f:
        for i in voulues:
            p = os.path.join(work, "p%04d.txt" % i)
            if os.path.exists(p):
                f.write(open(p, encoding="utf-8").read() + "\n")
    shutil.rmtree(tmp, ignore_errors=True)
    print("Texte écrit : %s" % opts.output)


if __name__ == "__main__":
    main()
