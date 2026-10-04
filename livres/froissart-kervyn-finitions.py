#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finitions d'un tome des Œuvres de Froissart, Chroniques (éd. Kervyn de Lettenhove, Bruxelles,
Devaux ; fac-similé d'Osnabrück 1967 sur Gallica), à passer après epub_errata.py --retirer et
avant la relecture :

- page de titre de l'édition de 1871 (d'après la numérisation Google Livres) ; page de titre de
  la réimpression, plats de reliure et pages blanches retirés (les ancres de page restent) ;
- titre de départ « CHRONIQUES DE FRANCE, D'ENGLETERRE… » avec sa ponctuation ;
- table imprimée refaite : lignes coupées recollées, numéros de page lus dans le titre remis
  en colonne, entrées lues en un paragraphe séparées ; l'entrée « Errata » part avec l'errata ;
- métadonnées de l'édition.

Usage :
  froissart-kervyn-finitions.py entree.epub sortie.epub --tome XIII --ordinal TREIZIÈME \
      --annees 1386-1389 --sous-titre "(Depuis la mort de Charles le Mauvais jusqu'à la trêve de Lelinghen)." \
      --date 1871 [--table-fix corrections.json]
--table-fix : {"titre lu par l'OCR": ["titre juste", "page ou null"], …} vérifié sur le scan.
"""
import argparse
import html
import json
import re
import sys
import zipfile

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst")
ap.add_argument("--tome", required=True); ap.add_argument("--ordinal", required=True)
ap.add_argument("--annees", required=True); ap.add_argument("--sous-titre", required=True)
ap.add_argument("--date", required=True); ap.add_argument("--table-fix")
A = ap.parse_args()
src, dst = A.src, A.dst
zin = zipfile.ZipFile(src)
files = {n: zin.read(n) for n in zin.namelist()}
T = lambda n: files[n].decode("utf-8")
texts = sorted(n for n in files if re.match(r"OEBPS/Text/texte-\d+\.xhtml$", n))
plain = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s))
HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Œuvres de Froissart. Chroniques, tome %(tome)s</title>
  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />
</head>
<body>
"""

# 1. début : page de titre de 1871
t = T(texts[0])
a = t.index("<body>") + len("<body>")
b = t.index('<h1 id="titre-3">')
front = "".join(re.findall(r'<a id="page-\d+" />', t[a:b]))
t = t[:a] + "\n  " + t[b:]
t = re.sub(r'(<h1 id="titre-3">(?:<a id="page-\d+" />)?)CHRONIQUES DE FRANCE[^<]*</h1>',
           r"\1CHRONIQUES DE FRANCE, D'ENGLETERRE, D'ESCOCE, DE BRETAIGNE, D'ESPAIGNE, D'YTALIE, "
           r"DE FLANDRE ET D'ALEMAIGNE.</h1>", t)
files[texts[0]] = t.encode("utf-8")
files["OEBPS/Text/titre.xhtml"] = ((HEAD + """  <div class="titre">%(front)s
  <p class="centre titre-livre">ŒUVRES<br />DE<br />FROISSART</p>
  <p class="centre">publiées</p>
  <p class="centre">AVEC LES VARIANTES DES DIVERS MANUSCRITS</p>
  <p class="centre">PAR</p>
  <p class="centre">M. le baron KERVYN DE LETTENHOVE</p>
  <p class="centre">Membre de l'Académie royale de Belgique,<br />Correspondant de l'Institut de France, de l'Académie de Munich, etc.</p>
  <hr />
  <p class="centre">CHRONIQUES</p>
  <p class="centre">TOME %(ordinal)s</p>
  <p class="centre">%(annees)s</p>
  <p class="centre">%(sous)s</p>
  <hr />
  <p class="centre">BRUXELLES<br />COMPTOIR UNIVERSEL D'IMPRIMERIE ET DE LIBRAIRIE<br />VICTOR DEVAUX ET C<sup>ie</sup><br />RUE SAINT-JEAN, 26</p>
  <p class="centre">%(date)s</p>
  </div>
</body>
</html>
""").replace("%(front)s", front) % {"tome": A.tome, "ordinal": A.ordinal, "annees": A.annees,
                                     "sous": html.escape(A.sous_titre, quote=False), "date": A.date}).encode("utf-8")

# 2. pages blanches et plats : l'ancre de page reste, l'image part
for n in texts:
    files[n] = re.sub(r'<div class="image">(<a id="page-\d+" />)<img [^>]*/></div>', r"<div>\1</div>",
                      T(n)).encode("utf-8")

# 3. table imprimée
tf = next(n for n in texts if re.search(r">(?:<a id=\"page-\d+\" />)?TABLE\.</h2>", T(n)))
t = T(tf)
m = re.search(r'<h2 id="([^"]+)">(<a id="page-\d+" />)?TABLE\.</h2>(.*?)<p class="centre">FIN DE LA TABLE\.</p>', t, re.S)
assert m, "table"
body = m.group(3)
anchors = re.findall(r'<a id="page-\d+" />', body)
segs = []                                    # (titre, page ou None)
for el in re.finditer(r"<tr>(.*?)</tr>|<p[^>]*>(.*?)</p>", body, re.S):
    if el.group(1) is not None:
        cells = [plain(c).strip() for c in re.findall(r"<td>(.*?)</td>|<td />", el.group(1))]
        cells = [c for c in cells] + [""] * (2 - len(cells))
        txt = cells[0] + ((" " + cells[1]) if re.fullmatch(r"\d{1,3}", cells[1] or "") else "")
    else:
        txt = plain(el.group(2)).strip()
    pos = 0
    for mm in re.finditer(r"(.+?)[\s.]*\s(\d{1,3})(?=\s|$)", txt):
        segs.append([mm.group(1).strip(), mm.group(2)])
        pos = mm.end()
    rest = txt[pos:].strip()
    if rest:
        segs.append([rest, None])
entries = []
for title, page in segs:
    if entries and entries[-1][1] is None and not entries[-1][0].endswith("."):
        entries[-1] = [entries[-1][0] + " " + title, page]          # ligne coupée
    else:
        entries.append([title, page])
entries = [e for e in entries if not re.fullmatch(r"Errata\.?", e[0])]
# mots que l'OCR de la table a perdus (vérifiés sur le scan, vue 387)
FIX = {k: tuple(v) for k, v in json.load(open(A.table_fix, encoding="utf-8")).items()} if A.table_fix else {}
for e in entries:
    if e[0] in FIX:
        e[0], pg = FIX[e[0]]
        e[1] = e[1] or pg
    else:                                     # sinon, correction d'un morceau du titre
        for k, (v, pg) in FIX.items():
            if k in e[0]:
                e[0] = e[0].replace(k, v)
                e[1] = e[1] or pg
pages = [int(p) for _, p in entries if p]
bad = [i for i in range(1, len(pages)) if pages[i] < pages[i - 1]]
rows = []
for title, page in entries:
    title = re.sub(r"\s+", " ", title).strip()
    title = title[:-1] if title.endswith(".") and not title.endswith("..") else title
    rows.append('<tr><td>%s</td><td>%s</td></tr>' % (html.escape(title, quote=False), page or ""))
new = ('<h1 id="table">%sTABLE.</h1>\n  <p class="droite">Pages</p>\n  <table class="tableau">\n%s\n</table>\n'
       '  <div>%s</div>\n  <p class="centre">FIN DE LA TABLE.</p>'
       % (m.group(2) or "", "\n".join(rows), "".join(anchors)))
t = t[:m.start()] + new + t[m.end():]
files[tf] = t.encode("utf-8")

# 4. métadonnées, sommaire, CSS
o = T("OEBPS/content.opf")
o = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>Œuvres de Froissart. Chroniques, tome %s (%s)</dc:title>" % (A.tome, A.annees), o, flags=re.S)
o = re.sub(r'<dc:creator[^>]*>.*?</dc:creator>',
           '<dc:creator opf:role="aut" opf:file-as="Froissart, Jean">Jean Froissart</dc:creator>\n'
           '    <dc:contributor opf:role="edt" opf:file-as="Kervyn de Lettenhove, Joseph">Joseph Kervyn de Lettenhove</dc:contributor>\n'
           '    <dc:publisher>Bruxelles : Victor Devaux et Cie</dc:publisher>', o, flags=re.S)
o = re.sub(r"<dc:date>.*?</dc:date>", "<dc:date>%s</dc:date>" % A.date, o)
o = re.sub(r'\s*<item id="[^"]+" href="Images/[^"]+"[^>]*/>', "", o)
for n in [k for k in files if k.startswith("OEBPS/Images/")]:
    del files[n]
o = o.replace('<item id="t001"', '<item id="titre" href="Text/titre.xhtml" media-type="application/xhtml+xml"/>\n    <item id="t001"', 1)
o = o.replace('<itemref idref="t001"/>', '<itemref idref="titre"/>\n    <itemref idref="t001"/>', 1)
assert 'idref="titre"' in o
files["OEBPS/content.opf"] = o.encode("utf-8")

n = T("OEBPS/toc.ncx")
for a in re.findall(r'id="(page-\d+)"', front):
    n = n.replace('Text/texte-001.xhtml#%s"' % a, 'Text/titre.xhtml#%s"' % a)
nav = [("Page de titre", "Text/titre.xhtml"),
       ("Chroniques de France, d'Engleterre, d'Escoce…", "Text/texte-001.xhtml#titre-3")]
for f in texts:
    for mm in re.finditer(r'<h1 id="([^"]+)">(?:<a id="[^"]+" />)?(NOTES|TABLE)\.', T(f)):
        nav.append((mm.group(2).capitalize(), "Text/%s#%s" % (f.split("/")[-1], mm.group(1))))
pts = "\n".join('    <navPoint id="nav-%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
                % (i, i, html.escape(l, quote=False), s_) for i, (l, s_) in enumerate(nav, 1))
n = re.sub(r"<navMap>.*?</navMap>", "<navMap>\n%s\n  </navMap>" % pts, n, flags=re.S)
n = re.sub(r"<docTitle><text>.*?</text></docTitle>",
           "<docTitle><text>Œuvres de Froissart. Chroniques, tome %s (%s)</text></docTitle>" % (A.tome, A.annees), n, flags=re.S)
k = [len(nav)]


def po(mm):
    k[0] += 1
    return 'playOrder="%d"' % k[0]


head, sep, tail = n.partition("<pageList>")
files["OEBPS/toc.ncx"] = (head + sep + re.sub(r'playOrder="\d+"', po, tail)).encode("utf-8")
c = T("OEBPS/Styles/livre.css")
if ".titre-livre" not in c:
    c += ("\n/* page de titre */\n.titre { margin-top: 2em; }\n"
          ".titre-livre { font-size: 1.6em; font-weight: bold; margin-bottom: 1em; }\n"
          "hr { width: 30%; margin: 1.5em auto; }\np.droite { text-align: right; text-indent: 0; }\n")
files["OEBPS/Styles/livre.css"] = c.encode("utf-8")

with zipfile.ZipFile(dst, "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
    for name, data in files.items():
        z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
print("table : %d entrées (%d sans page)%s ; écrit %s"
      % (len(entries), sum(1 for e in entries if not e[1]),
         " ; ordre des pages à vérifier : " + ", ".join(entries[i][0][:30] for i in bad) if bad else "", dst))
