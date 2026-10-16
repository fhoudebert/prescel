#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_apparat_scan.py — Appels de variantes et apparat d'une édition Kervyn (Froissart) remis
d'après la numérisation : lecture des images par scan_apparat.py, apparat relu à vue.

Étapes (modules de scripts/apparat/) :
  1. tableaux   prose prise pour un tableau par l'OCR, remise en paragraphe ;
  2. blocs      blocs d'apparat mêlés au récit (récit dans le bloc, apparat en tête de paragraphe) ;
  3. blocs      chaque bloc <p class="variantes" title="p. N"> refait avec la numérotation de
                l'apparat relu (« 1-2 Remonstrèrent. — 3-4 Estrangers. — 5-6 Bien. »), les mots
                pris au maître, corrigés par la lecture Tesseract du bas de page et par l'EPUB
                Google quand le maître est fautif ; bloc manquant ajouté après son paragraphe ;
  4. appels     appels <sup class="var">k</sup> placés après le mot où la numérisation montre un
                exposant (k = rang sur la page, vérifié sur l'apparat relu) ; restes d'appels mal
                lus (« ' », « ° », chiffre collé au mot, lettre isolée) retirés ; appels du maître
                sans place sur l'image retirés ;
  5. exposants  exposants des nombres romains en <sup> minuscule (IIII<sup>xx</sup> = 80,
                V<sup>c</sup> = 500, VII<sup>m</sup> = 7 000, XIX<sup>e</sup>) : formes collées,
                dates « mil CCC. IIII<sup>xx</sup> et … » (1380-1399), table EXPOSANTS lue à vue,
                <sup class="var">XX</sup> d'une relecture antérieure normalisés ;
  6. paragraphes coupés par un bloc d'apparat recollés ; marques « à vérifier » devenues sans
     objet levées.

Le fichier de corrections (Python) du volume donne VUES (vues hors d'ordre), DROP / ADD
(appels relus à vue), PARTIAL, EXPOSANTS et REMPLACEMENTS ; voir livres/froissart-t13-appels.py.

Usage :
  python3 scripts/epub_apparat_scan.py maitre.epub sortie.epub --scan scan.json \\
      --apparat livres/froissart-t13-apparat-lu.txt --corrections livres/froissart-t13-appels.py \\
      [--google Oeuvres_de_Froissart-13.epub] [--mots auto] [--rapport rapport.tsv]
"""
import argparse
import collections
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apparat import conf, texte, tableaux, blocs, appels, exposants, recollage, marques  # noqa: E402


def write_epub(src, raws, dst):
    zin = zipfile.ZipFile(src)
    with zipfile.ZipFile(dst, "w") as zo:
        for info in zin.infolist():
            d = raws[info.filename].encode("utf-8") if info.filename in raws else zin.read(info)
            zo.writestr(info, d, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)


def _apply(raws, edits):
    raws, conflicts = appels.apply(raws, edits)
    if conflicts:
        raise SystemExit("modifications en conflit : %r" % conflicts[:5])
    return raws


def pipeline(raws):
    log = collections.OrderedDict()
    raws, tlog = tableaux.stage(raws)
    log["tableaux"] = (tlog, [])
    e0, r0 = blocs.fix_blocks(raws)
    raws = _apply(raws, e0)
    log["blocs"] = (e0, r0)
    e1, r1 = blocs.stage(raws)
    raws = _apply(raws, e1)
    log["apparat"] = (e1, r1)
    _, e2, r2 = appels.solve(raws=raws)
    raws = _apply(raws, e2)
    log["appels"] = (e2, r2)
    raws, xlog = exposants.stage(raws)
    rep = []
    raws = exposants.from_scan(raws, xlog, rep)
    log["exposants"] = (xlog, rep)
    raws, jlog = recollage.stage(raws)
    log["paragraphes recollés"] = (jlog, [])
    rlog, rrep = [], []
    for r in getattr(conf.CORR, "REMPLACEMENTS", []):
        n = 0
        for f in raws:
            if len(r) > 2:
                raws[f], k = re.subn(r[0], r[1], raws[f])
            else:
                k = raws[f].count(r[0])
                raws[f] = raws[f].replace(r[0], r[1])
            n += k
        (rlog if n else rrep).append((r[0], r[1], n))
    log["remplacements"] = (rlog, [(a, "introuvable") for a, *_ in rrep])
    raws, mlog = marques.stage(raws)
    log["marques levées"] = (mlog, [])
    return raws, log


def cell(x):
    s = re.sub(r"<[^>]+>", "", x) if isinstance(x, str) else str(x)
    return re.sub(r"\s+", " ", s).strip()[:200]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--scan", required=True, help="JSON de scan_apparat.py")
    ap.add_argument("--apparat", required=True, help="apparat relu à vue")
    ap.add_argument("--corrections", required=True, help="corrections du volume (Python)")
    ap.add_argument("--google", help="EPUB Google Livres de la même édition (autre OCR de l'apparat)")
    ap.add_argument("--mots", default="auto", help="liste de mots français (epub_longs.py ; « auto »)")
    ap.add_argument("--decalage-ancres", type=int, default=4, help="ancre page-N = page imprimée N - décalage")
    ap.add_argument("--rapport", help="rapport TSV des modifications et remarques")
    a = ap.parse_args()
    from epub_longs import load_wordlist
    conf.configure(a.src, a.scan, a.apparat, a.corrections, google=a.google,
                   words=load_wordlist(a.mots) or (), offset=a.decalage_ancres)
    _, raws = texte.load(a.src)
    raws, log = pipeline(raws)
    write_epub(a.src, raws, a.dst)
    for k, (e, r) in log.items():
        print("%-22s %4d modifications ; %3d remarques" % (k, len(e), len(r)))
    if a.rapport:
        with open(a.rapport, "w", encoding="utf-8") as f:
            f.write("étape\ttype\tdétail\n")
            for k, (e, r) in log.items():
                for x in e:
                    x = x[3:] if len(x) == 5 and isinstance(x[1], int) else x   # (fichier, début, fin, texte, note)
                    f.write("%s\tmodification\t%s\n" % (k, "\t".join(cell(y) for y in (x if isinstance(x, tuple) else (x,)))))
                for x in r:
                    f.write("%s\tremarque\t%s\n" % (k, "\t".join(cell(y) for y in (x if isinstance(x, tuple) else (x,)))))
        print("rapport :", a.rapport)


if __name__ == "__main__":
    main()
