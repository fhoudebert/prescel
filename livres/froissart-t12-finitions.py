#!/usr/bin/env python3
# Finitions du tome XII avant relecture (EPUB maître) : page de titre de l'édition de 1871,
# titres, table imprimée, métadonnées. Usage : finalise.py entree.epub sortie.epub
import re, sys, zipfile, html

src, dst = sys.argv[1], sys.argv[2]
zin = zipfile.ZipFile(src)
files = {n: zin.read(n) for n in zin.namelist()}
T = lambda n: files[n].decode("utf-8")

HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Œuvres de Froissart. Chroniques, tome XII</title>
  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />
</head>
<body>
"""
# 1. page de titre de l'édition originale (Bruxelles, Devaux, 1871), d'après Google Livres
#    v9dTAAAAcAAJ ; le PDF Gallica est la réimpression en fac-similé (Osnabrück, 1967)
titre = HEAD + """  <div class="titre"><a id="page-1"></a><a id="page-2"></a><a id="page-3"></a>
  <p class="centre titre-livre">ŒUVRES<br />DE<br />FROISSART</p>
  <p class="centre">publiées</p>
  <p class="centre">AVEC LES VARIANTES DES DIVERS MANUSCRITS</p>
  <p class="centre">PAR</p>
  <p class="centre">M. le baron KERVYN DE LETTENHOVE</p>
  <p class="centre">Membre de l'Académie royale de Belgique,<br />Correspondant de l'Institut de France, de l'Académie de Munich, etc.</p>
  <hr />
  <p class="centre">CHRONIQUES</p>
  <p class="centre">TOME DOUZIÈME</p>
  <p class="centre">1386-1389</p>
  <p class="centre">(Depuis le voyage de Charles VI à l'Écluse, jusqu'à la fin de l'expédition du duc de Lancastre en Espagne)</p>
  <hr />
  <p class="centre">BRUXELLES<br />COMPTOIR UNIVERSEL D'IMPRIMERIE ET DE LIBRAIRIE<br />VICTOR DEVAUX ET C<sup>ie</sup><br />RUE SAINT-JEAN, 26</p>
  <p class="centre">1871</p>
  <a id="page-4"></a></div>
</body>
</html>
"""
files["OEBPS/Text/titre.xhtml"] = titre.encode("utf-8")

# 2. texte-001 : retirer la page de titre de la réimpression (1967) et les plats de reliure
t = T("OEBPS/Text/texte-001.xhtml")
a = t.index("<body>") + len("<body>")
b = t.index('<h1 id="titre-3">')
t = t[:a] + "\n  " + t[b:]
t = t.replace("""<h1 id="titre-3"><a id="page-5" />CHRONIQUES DE FRANCE D'ENGLETERRE, D'ESCOCE, DE BRETAIGNE, D'ESPAIGNE D'YTALIE DE FLANDRES ET D'ALEMAIGNE.</h1>""",
              """<h1 id="titre-3"><a id="page-5" />CHRONIQUES DE FRANCE, D'ENGLETERRE, D'ESCOCE, DE BRETAIGNE, D'ESPAIGNE, D'YTALIE, DE FLANDRES ET D'ALEMAIGNE.</h1>""")
assert "D'ESPAIGNE, D'YTALIE" in t
files["OEBPS/Text/texte-001.xhtml"] = t.encode("utf-8")

# 3. table imprimée : titre, en-tête de colonne, trois entrées lues en un paragraphe
t = T("OEBPS/Text/texte-004.xhtml")
t = t.replace('<p class="centre"><a id="page-401" />TAB L E.</p>', '<h1 id="titre-table"><a id="page-401" />TABLE.</h1>')
t = re.sub(r'<p class="a-verifier">Pag es</p>|<p>Pag es</p>', '<p class="droite">Pages</p>', t)
old = re.search(r'<p><a id="page-403" />Souffrances des Anglais 308 Le duc de Lancastre licencie son armée\. 311 '
                r'Les Anglais demandent un sauf-conduit au roi de Castille 315</p>\s*<table class="tableau">', t)
assert old, "entrées de la p. 403"
t = t[:old.start()] + ('<table class="tableau">\n'
     '<tr><td><a id="page-403" />Souffrances des Anglais</td><td>308</td></tr>\n'
     '<tr><td>Le duc de Lancastre licencie son armée.</td><td>311</td></tr>\n'
     '<tr><td>Les Anglais demandent un sauf-conduit au roi de Castille</td><td>315</td></tr>') + t[old.end():]
assert "TAB L E" not in t
# pages blanches (vues 404 et 408 du PDF) : l'ancre de page reste, l'image part
t = re.sub(r'<div class="image">(<a id="page-\d+" />)<img src="\.\./Images/planche-00[34]\.png" alt="" /></div>',
           r'<div>\1</div>', t)
assert "planche-00" not in t
files["OEBPS/Text/texte-004.xhtml"] = t.encode("utf-8")

# 4. OPF : métadonnées de l'édition, page de titre en tête, plats de reliure retirés
o = T("OEBPS/content.opf")
o = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>Œuvres de Froissart. Chroniques, tome XII (1386-1389)</dc:title>", o, flags=re.S)
o = re.sub(r'<dc:creator[^>]*>.*?</dc:creator>',
           '<dc:creator opf:role="aut" opf:file-as="Froissart, Jean">Jean Froissart</dc:creator>\n'
           '    <dc:contributor opf:role="edt" opf:file-as="Kervyn de Lettenhove, Joseph">Joseph Kervyn de Lettenhove</dc:contributor>\n'
           '    <dc:publisher>Bruxelles : Victor Devaux et Cie</dc:publisher>', o, flags=re.S)
o = re.sub(r"<dc:date>.*?</dc:date>", '<dc:date>1871</dc:date>', o)
for n in ("planche-001", "planche-002", "planche-003", "planche-004"):
    o = re.sub(r'\s*<item id="img\d+" href="Images/%s\.png"[^>]*/>' % n, "", o)
    files.pop("OEBPS/Images/%s.png" % n, None)
o = o.replace('<item id="t001"', '<item id="titre" href="Text/titre.xhtml" media-type="application/xhtml+xml"/>\n    <item id="t001"', 1)
o = o.replace('<itemref idref="t001"/>', '<itemref idref="titre"/>\n    <itemref idref="t001"/>', 1)
files["OEBPS/content.opf"] = o.encode("utf-8")

# 5. toc.ncx : pages 1-4 vers la page de titre ; table des matières refaite
n = T("OEBPS/toc.ncx")
n = re.sub(r'Text/texte-001\.xhtml#page-([1-4])"', r'Text/titre.xhtml#page-\1"', n)
nav = [("Page de titre", "Text/titre.xhtml"),
       ("Chroniques de France, d'Engleterre, d'Escoce…", "Text/texte-001.xhtml#titre-3")]
for f in sorted(k for k in files if k.startswith("OEBPS/Text/texte-")):
    for m in re.finditer(r'<h1 id="([^"]+)">(?:<a id="[^"]+" />)?(NOTES|TABLE|ERRATA)\.', T(f)):
        nav.append((m.group(2).capitalize(), "Text/%s#%s" % (f.split("/")[-1], m.group(1))))
pts = "\n".join('    <navPoint id="nav-%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
                % (i, i, html.escape(lab, quote=False), src_) for i, (lab, src_) in enumerate(nav, 1))
n = re.sub(r"<navMap>.*?</navMap>", "<navMap>\n%s\n  </navMap>" % pts, n, flags=re.S)
n = re.sub(r"<docTitle><text>.*?</text></docTitle>", "<docTitle><text>Œuvres de Froissart. Chroniques, tome XII (1386-1389)</text></docTitle>", n, flags=re.S)
# playOrder des pages après la table des matières, dans l'ordre
k = [len(nav)]
def po(m):
    k[0] += 1
    return 'playOrder="%d"' % k[0]
head, sep, tail = n.partition("<pageList>")
n = head + sep + re.sub(r'playOrder="\d+"', po, tail)
files["OEBPS/toc.ncx"] = n.encode("utf-8")

# 6. CSS
c = T("OEBPS/Styles/livre.css")
if ".titre-livre" not in c:
    c += "\n/* page de titre */\n.titre { margin-top: 2em; }\n.titre-livre { font-size: 1.6em; font-weight: bold; margin-bottom: 1em; }\nhr { width: 30%; margin: 1.5em auto; }\n"
files["OEBPS/Styles/livre.css"] = c.encode("utf-8")

with zipfile.ZipFile(dst, "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
    for name, data in files.items():
        z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
print("écrit", dst)
