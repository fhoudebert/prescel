#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finitions du tome XIII des Chroniques de Froissart (éd. J. A. Buchon, Paris, Verdière, 1825 ;
Gallica bpt6k63133057), à passer après epub_structure.py et avant la relecture :

- page de titre transcrite du scan (vue 13), faux-titre, verso et pages blanches retirés ;
- titres : « LES CHRONIQUES DE JEAN FROISSART. LIVRE QUATRIÈME. », chapitres XXIV à LV
  numérotés dans l'ordre (l'OCR lit « XXYÏI », « XXXW », « CHAPLTRE ») ; le titre de chaque
  chapitre, imprimé en petites capitales et mal lu, est repris de la table du volume, en
  minuscules, dans un <p class="sommaire">, à relire sur le scan ;
- appendice (faux-titre « APPENDICE. ») et table refaite en tableau, avec les numéros de page
  du livre tirés des ancres de page (et non de l'OCR de la table) ;
- métadonnées de l'édition.

Usage : froissart-t13-finitions.py entree.epub sortie.epub
"""
import html
import re
import sys
import zipfile

ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
         (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
FIRST, LAST = 24, 55


def roman(n):
    out = ""
    for v, r in ROMAN:
        while n >= v:
            out += r
            n -= v
    return out


src, dst = sys.argv[1], sys.argv[2]
zin = zipfile.ZipFile(src)
files = {n: zin.read(n) for n in zin.namelist()}
T = lambda n: files[n].decode("utf-8")
texts = sorted(n for n in files if re.match(r"OEBPS/Text/texte-\d+\.xhtml$", n))
plain = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s))

# page imprimée de chaque ancre (pageList du toc.ncx)
ncx = T("OEBPS/toc.ncx")
label = {m.group(2): m.group(1) for m in re.finditer(
    r"<pageTarget\b[^>]*>\s*<navLabel>\s*<text>([^<]*)</text>\s*</navLabel>\s*<content src=\"[^\"#]*#([^\"]+)\"", ncx)}

# 1. titres de chapitre d'après la table imprimée
table_file = next(f for f in texts if re.search(r">(?:<a id=\"page-\d+\" />)?TABLE</h2>", T(f)))
last = T(table_file)
tab = re.search(r'<h2 id="[^"]+"><a id="page-\d+" />TABLE</h2>.*?<p>(CHAPITRE XX.*?)</p>', last, re.S)
assert tab, "table du volume introuvable"
entries = re.split(r"\s*-?(?:CHAPITRE|CHAP\.)\s+[XLVIl1U]+\.\s*", " " + plain(tab.group(1)))[1:]
assert len(entries) == LAST - FIRST + 1, "table : %d entrées" % len(entries)
titles = []
for e in entries:
    e = re.sub(r"\s*APPENDICE\s+\S+\s*$", "", e.strip())
    e = re.sub(r"(?:\s+[\d\sioOlI.\-^•*£<>&;Cf]{1,8})+$", "", e)           # numéro de page OCR
    e = re.sub(r"\s*\.*\s*$", ".", e)                                     # point final
    e = re.sub(r"\s+([,;:.])", r"\1", e)
    titles.append(e[0].upper() + e[1:])

# 2. chapitres dans le texte
CHAP = re.compile(r"^\W*CHAP[A-Z1ÏL]{3,6}\b", re.I)
n_chap = [FIRST]
toc_rows = []


def caps(s):
    letters = [c for c in plain(s) if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.6


def chapter_heads(t):
    """Remplace chaque début de chapitre (titre OCR et lignes en capitales qui suivent)."""
    out, pos = [], 0
    # chapitre L : « … fut cause. 1 CHAPITRE L.</p> » en fin de paragraphe
    t = re.sub(r"(<a id=\"page-\d+\" />)?\s*\d?\s*CHAPITRE L\.</p>",
               lambda m: "</p>\n  <p class=\"centre\">%sCHAPITRE L.</p>" % (m.group(1) or ""), t)
    elems = list(re.finditer(r"  <(h1|h2|p)\b([^>]*)>(.*?)</\1>\n", t, re.S))
    i = 0
    while i < len(elems):
        m = elems[i]
        txt = plain(m.group(3)).strip()
        if CHAP.match(txt) and n_chap[0] <= LAST and len(txt) < 400:
            n = n_chap[0]
            n_chap[0] += 1
            anchors = re.findall(r'<a id="[^"]+" />', m.group(3))
            j = i + 1
            while j < len(elems) and (elems[j].group(1) == "h1" or "sommaire" in elems[j].group(2)
                                      or caps(elems[j].group(3))) and j - i <= 4:
                anchors += re.findall(r'<a id="[^"]+" />', elems[j].group(3))
                j += 1
            pages = [re.search(r'id="([^"]+)"', a).group(1) for a in anchors]
            # lignes du titre en capitales collées au premier paragraphe (« ONCLES DU ROI, … ROI. EN ce temps »)
            if j < len(elems) and elems[j].group(1) == "p":
                raw = elems[j].group(3)
                cm = re.match(r"((?:<[^>]+>|\([^)<]*\)|[^a-zà-ÿ<(])+?[.,;:](?:</span>)?)\s+"
                              r"(?=(?:<[^>]+>)?[A-ZÀ-Ý][A-ZÀ-Ý.']*(?:</span>)?\s+(?:<[^>]+>)?[a-zà-ÿ])", raw)
                if cm and len(plain(cm.group(1))) > 15:
                    keep = "".join(re.findall(r'<a id="[^"]+" />', cm.group(1)))
                    newp = "  <%s%s>%s%s</%s>\n" % ("p", elems[j].group(2), keep, raw[cm.end():], "p")
                    t = t[:elems[j].start()] + newp + t[elems[j].end():]
                    elems = list(re.finditer(r"  <(h1|h2|p)\b([^>]*)>(.*?)</\1>\n", t, re.S))
            out.append(t[pos:m.start()])
            out.append('  <h2 id="chap-%d">%sCHAPITRE %s.</h2>\n  <p class="sommaire">%s</p>\n'
                       % (n, "".join(anchors), roman(n), html.escape(titles[n - FIRST], quote=False)))
            toc_rows.append((n, pages))
            pos = elems[j - 1].end()
            i = j
        else:
            i += 1
    out.append(t[pos:])
    return "".join(out)


for n in texts:
    files[n] = chapter_heads(T(n)).encode("utf-8")
assert n_chap[0] == LAST + 1, "chapitres trouvés jusqu'à %s" % roman(n_chap[0] - 1)

# 3. début : page de titre, faux-titre, verso et pages blanches retirés
t = T(texts[0])
a = t.index("<body>") + len("<body>")
b = t.index('<h1 id="titre-5">')
front_anchors = re.findall(r'<a id="page-\d+" />', t[a:b])
t = t[:a] + "\n  " + t[b:]
t = re.sub(r'<h1 id="titre-5">(<a id="page-15" />)LES CHRONIQUES</h1>\s*<p class="centre">DE</p>\s*'
           r'<p class="centre">JEAN F[^<]*</p>\s*<h1 id="titre-11">LIVRE QUATRIÈME</h1>',
           r'<h1 id="titre-5">\1LES CHRONIQUES DE JEAN FROISSART.<br />LIVRE QUATRIÈME.</h1>', t)
assert "LIVRE QUATRIÈME.</h1>" in t
files[texts[0]] = t.encode("utf-8")
titre = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Les chroniques de Jean Froissart, tome XIII</title>
  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />
</head>
<body>
  <div class="titre">%s
  <p class="centre titre-livre">COLLECTION<br />DES CHRONIQUES<br />NATIONALES FRANÇAISES,</p>
  <p class="centre">ÉCRITES EN LANGUE VULGAIRE</p>
  <p class="centre">DU TREIZIÈME AU SEIZIÈME SIÈCLE,</p>
  <p class="centre">AVEC NOTES ET ÉCLAIRCISSEMENTS,</p>
  <p class="centre">PAR J. A. BUCHON.</p>
  <hr />
  <p class="centre">TOME XIII.</p>
  <hr />
  <p class="centre">PARIS,<br />VERDIÈRE, LIBRAIRE, QUAI DES AUGUSTINS, N<sup>o</sup> 25.<br />J. CAREZ, RUE HAUTE FEUILLE, N<sup>o</sup> 18.</p>
  <p class="centre">1825.</p>
  </div>
</body>
</html>
""" % "".join(front_anchors)
files["OEBPS/Text/titre.xhtml"] = titre.encode("utf-8")

# 4. fin : appendice, table, pages blanches
t = T(table_file)
t = re.sub(r'<div class="image">(<a id="page-459" />)<img [^>]*/></div>',
           r'<h1 id="appendice">\1APPENDICE.</h1>', t)
t = t.replace('<h1 id="titre-32">', '<h2 id="titre-32">', 1)
t = re.sub(r'(<h2 id="titre-32">.*?)</h1>', r"\1</h2>", t, count=1, flags=re.S)
t = re.sub(r'<div class="image">(<a id="page-\d+" />)<img [^>]*/></div>', r"<div>\1</div>", t)
rows = []
alltext = "".join(T(f) for f in texts)
for n, pages in toc_rows:
    k = alltext.index('<h2 id="chap-%d">' % n)
    k2 = alltext.index("</h2>", k)
    before = re.findall(r'<a id="(page-\d+)" />', alltext[:k2])
    pg = label.get(before[-1], "") if before else ""
    rows.append('<tr><td>Chapitre %s. %s</td><td>%s</td></tr>'
                % (roman(n), html.escape(titles[n - FIRST], quote=False), pg))
app = re.search(r'<h1 id="appendice"><a id="(page-\d+)" />', t)
rows.append('<tr><td>Appendice.</td><td>%s</td></tr>' % label.get(app.group(1), ""))
t = re.sub(r'(<h2 id="titre-45">(<a id="page-\d+" />))TABLE</h2>\s*<p class="centre">DES</p>\s*'
           r'<p>CHAPITRES CONTENUS DANS CE VOLUME\.</p>\s*<p>CHAPITRE XX.*?</p>',
           lambda m: '<h1 id="table">%sTABLE<br />DES CHAPITRES CONTENUS DANS CE VOLUME.</h1>\n'
                     '  <p class="droite">Pages</p>\n  <table class="tableau">\n%s\n</table>\n  <div>%s</div>'
                     % (m.group(2), "\n".join(rows),
                        "".join(re.findall(r'<a id="page-\d+" />', m.group(0))[1:])), t, flags=re.S)
assert '<table class="tableau">' in t
t = re.sub(r"<p>FIN DE LA TABLE DU TREIZIÈME [^<]*(?:<[^>]+>[^<]*)*?</p>",
           '<p class="centre">FIN DE LA TABLE DU TREIZIÈME VOLUME.</p>', t)
files[table_file] = t.encode("utf-8")
for n in [f for f in texts if f != table_file]:
    files[n] = re.sub(r'<div class="image">(<a id="page-\d+" />)<img [^>]*/></div>', r"<div>\1</div>",
                      T(n)).encode("utf-8")

# 5. OPF, toc.ncx, CSS
o = T("OEBPS/content.opf")
o = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>Les chroniques de Jean Froissart, tome XIII</dc:title>", o, flags=re.S)
o = re.sub(r'<dc:creator[^>]*>.*?</dc:creator>',
           '<dc:creator opf:role="aut" opf:file-as="Froissart, Jean">Jean Froissart</dc:creator>\n'
           '    <dc:contributor opf:role="edt" opf:file-as="Buchon, Jean-Alexandre">J. A. Buchon</dc:contributor>\n'
           '    <dc:publisher>Paris : Verdière</dc:publisher>', o, flags=re.S)
o = re.sub(r"<dc:date>.*?</dc:date>", "<dc:date>1825</dc:date>", o)
o = re.sub(r'\s*<item id="[^"]+" href="Images/[^"]+"[^>]*/>', "", o)
for n in [k for k in files if k.startswith("OEBPS/Images/")]:
    del files[n]
o = o.replace('<item id="t001"', '<item id="titre" href="Text/titre.xhtml" media-type="application/xhtml+xml"/>\n    <item id="t001"', 1)
o = o.replace('<itemref idref="t001"/>', '<itemref idref="titre"/>\n    <itemref idref="t001"/>', 1)
assert 'idref="titre"' in o
files["OEBPS/content.opf"] = o.encode("utf-8")

n = ncx
for a in front_anchors:
    pid = re.search(r'id="([^"]+)"', a).group(1)
    n = n.replace("Text/texte-001.xhtml#%s\"" % pid, "Text/titre.xhtml#%s\"" % pid)
nav = [("Page de titre", "Text/titre.xhtml"),
       ("Les chroniques de Jean Froissart. Livre quatrième", "Text/texte-001.xhtml#titre-5")]
for f in texts:
    for m in re.finditer(r'<h2 id="(chap-(\d+))">', T(f)):
        k = int(m.group(2))
        nav.append(("Chapitre %s. %s" % (roman(k), titles[k - FIRST]), "Text/%s#%s" % (f.split("/")[-1], m.group(1))))
nav += [("Appendice", "Text/%s#appendice" % table_file.split("/")[-1]),
        ("Table", "Text/%s#table" % table_file.split("/")[-1])]
pts = "\n".join('    <navPoint id="nav-%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
                % (i, i, html.escape(lab, quote=False), s_) for i, (lab, s_) in enumerate(nav, 1))
n = re.sub(r"<navMap>.*?</navMap>", "<navMap>\n%s\n  </navMap>" % pts, n, flags=re.S)
n = re.sub(r"<docTitle><text>.*?</text></docTitle>", "<docTitle><text>Les chroniques de Jean Froissart, tome XIII</text></docTitle>", n, flags=re.S)
k = [len(nav)]


def po(m):
    k[0] += 1
    return 'playOrder="%d"' % k[0]


head, sep, tail = n.partition("<pageList>")
files["OEBPS/toc.ncx"] = (head + sep + re.sub(r'playOrder="\d+"', po, tail)).encode("utf-8")
c = T("OEBPS/Styles/livre.css")
if ".titre-livre" not in c:
    c += ("\n/* page de titre, sommaires de chapitre */\n.titre { margin-top: 2em; }\n"
          ".titre-livre { font-size: 1.4em; font-weight: bold; margin-bottom: 1em; }\n"
          "hr { width: 30%; margin: 1.5em auto; }\n"
          "p.sommaire { font-variant: small-caps; text-align: justify; text-indent: 0; margin: 0 2em 1.5em 2em; }\n")
files["OEBPS/Styles/livre.css"] = c.encode("utf-8")

with zipfile.ZipFile(dst, "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
    for name, data in files.items():
        z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
print("chapitres %s à %s, table de %d lignes ; écrit %s" % (roman(FIRST), roman(LAST), len(rows), dst))
