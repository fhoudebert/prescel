#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remplace la chronologie du t. III de Guillaume le Maréchal (partie-03.xhtml, p. cxlv-clvi) par la
transcription faite sur les images du DjVu (livres/guillaume-marechal-t3-chronologie.txt) : les deux OCR
mêlaient les deux colonnes du tableau (dates, lieux et renvois dans le désordre).

Une table par page (date | lieu ou fait | référence ; l'année en ligne de tête), les notes de la page
à la suite, ancres de page et identifiants de notes comme dans le reste du livre.

  python3 livres/guillaume-marechal-t3-chronologie.py entree.epub sortie.epub
"""
import html
import os
import re
import sys
import zipfile

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guillaume-marechal-t3-chronologie.txt")
FICHIER = "OEBPS/Text/partie-03.xhtml"
DEJA = set()


def enrichir(t, page):
    """Texte de la transcription → XHTML : « _…_ » italique, « [n] » appel de note."""
    t = html.escape(t, quote=False)
    t = re.sub(r"_(.+?)_", r"<i>\1</i>", t)
    def appel(m):
        ident = "appel-%s-%s" % (page, m.group(1))
        k = 2
        while ident in DEJA:                           # même note appelée deux fois (« Weston⁶ », « Warden⁶ »)
            ident = "appel-%s-%s-%d" % (page, m.group(1), k)
            k += 1
        DEJA.add(ident)
        return '<sup><a href="#note-%s-%s" id="%s">%s</a></sup>' % (page, m.group(1), ident, m.group(1))
    return re.sub(r"\[(\d+)\]", appel, t)


def lire(chemin):
    pages = []
    for ligne in open(chemin, encoding="utf-8"):
        ligne = ligne.rstrip("\n")
        if not ligne.strip() or ligne.startswith("# "):
            continue
        if ligne.startswith("@"):
            pages.append({"page": ligne[1:].strip(), "lignes": [], "notes": {}})
        elif ligne.startswith("="):
            pages[-1]["lignes"].append(("annee", ligne[1:].strip()))
        elif re.match(r"#\d+ ", ligne):
            n, texte = ligne[1:].split(" ", 1)
            pages[-1]["notes"].setdefault(int(n), []).append(texte)
        else:
            cellules = [c.strip() for c in ligne.split("|")]
            if len(cellules) != 3:
                sys.exit("Ligne mal formée (3 colonnes attendues) : %s" % ligne)
            pages[-1]["lignes"].append(("ligne", cellules))
    return pages


def xhtml(pages):
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"',
           '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">',
           '<html xmlns="http://www.w3.org/1999/xhtml">', "<head>", "  <title>Chronologie et itinéraire</title>",
           '  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />', "</head>", "<body>"]
    premiere = pages[0]["page"]
    out.append('<h1 id="t18"><a id="page-%s" />CHRONOLOGIE ET ITINÉRAIRE DE GUILLAUME LE MARÉCHAL%s</h1>'
               % (premiere, enrichir("[1]", premiere)))
    for p in pages:
        page = p["page"]
        out.append('<table class="chronologie">')
        ancre = "" if page == premiere else '<a id="page-%s" />' % page
        for genre, contenu in p["lignes"]:
            if genre == "annee":
                out.append('<tr><th colspan="3" class="annee">%s%s</th></tr>' % (ancre, enrichir(contenu, page)))
            else:
                d, lieu, ref = (enrichir(c, page) for c in contenu)
                out.append('<tr><td class="date">%s%s</td><td>%s</td><td class="ref">%s</td></tr>' % (ancre, d, lieu, ref))
            ancre = ""
        out.append("</table>")
        for n in sorted(p["notes"]):
            texte = "<br />".join(enrichir(t, page) for t in p["notes"][n])
            out.append('<p class="note" id="note-%s-%d"><a href="#appel-%s-%d">%d</a>. %s</p>' % (page, n, page, n, n, texte))
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def verifier(pages):
    """Chaque appel a sa note et chaque note son appel, page par page."""
    for p in pages:
        texte = " ".join(" ".join(c) if g == "ligne" else c for g, c in p["lignes"])
        appels = {int(n) for n in re.findall(r"\[(\d+)\]", texte)}
        if p["page"] == pages[0]["page"]:
            appels.add(1)                              # appel du titre
        if appels != set(p["notes"]):
            sys.exit("Page %s : appels %s, notes %s" % (p["page"], sorted(appels), sorted(p["notes"])))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    pages = lire(SOURCE)
    verifier(pages)
    zin = zipfile.ZipFile(src)
    zout = zipfile.ZipFile(dst, "w")
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == FICHIER:
            data = xhtml(pages).encode("utf-8")
        elif item.filename.endswith(".css") and b"table.chronologie" not in data:
            data += (b"\ntable.chronologie { border-collapse: collapse; margin: 0.5em 0; }\n"
                     b"table.chronologie td, table.chronologie th { padding: 0 0.4em; vertical-align: top; }\n"
                     b"table.chronologie th { padding-top: 0.6em; text-align: center; }\n"
                     b"table.chronologie td.date { white-space: nowrap; }\n")
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    n = sum(1 for p in pages for g, _ in p["lignes"] if g == "ligne")
    print("Chronologie : %d pages, %d lignes, %d notes" % (len(pages), n, sum(len(p["notes"]) for p in pages)))


if __name__ == "__main__":
    main()
