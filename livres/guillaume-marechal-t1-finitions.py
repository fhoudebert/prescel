#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finitions du tome I de L'Histoire de Guillaume le Maréchal (éd. Paul Meyer, Société de
l'Histoire de France, 1891), après pdf_vers.py sur le PDF Internet Archive
(lhistoiredeguill01meyeuoft) :
- page de titre transcrite du scan ; pages de garde et fiches de bibliothèque retirées
  (les ancres de page restent) ;
- titres : « EXTRAIT DU RÈGLEMENT. », « AVANT-PROPOS. », titre de départ du poème ;
- « FIN DU TOME PREMIER. » et l'adresse de l'imprimeur sortis de la dernière note.
Usage : guillaume-marechal-t1-finitions.py entree.epub sortie.epub
"""
import re
import sys
import zipfile

src, dst = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src)
files = {n: z.read(n) for n in z.namelist()}
T = lambda n: files[n].decode("utf-8")
texts = sorted(n for n in files if re.match(r"OEBPS/Text/texte-\d+\.xhtml$", n))

t = T(texts[0])
a = t.index("<body>") + len("<body>")
b = t.index('<a id="page-11"></a>')
b = t.rindex("<p", 0, b)
front = "".join(re.findall(r'<a id="page-\d+"></a>', t[a:b]))
t = t[:a] + "\n" + t[b:]
t = re.sub(r'<p>(<a id="page-11"></a>)AfiT\. iA\. —', r'<h1 id="reglement">\1EXTRAIT DU RÈGLEMENT.</h1>\n<p>Art. 14. —', t)
t = re.sub(r'<p>(<a id="page-13"></a>)AVANT-PROPOS\. UHistoire', r'<h1 id="avant-propos">\1AVANT-PROPOS.</h1>\n<p>L\'Histoire', t)
t = re.sub(r'<p class="vers">(<a id="page-15"></a>)',
           r'<h1 id="poeme">\1L\'HISTOIRE DE GUILLAUME LE MARÉCHAL</h1>\n<p class="vers">', t, count=1)
assert 'id="poeme"' in t and 'id="avant-propos"' in t and 'id="reglement"' in t
files[texts[0]] = t.encode("utf-8")

last = T(texts[-1])
last = re.sub(r"\s*FIN DU TOME PREMIER\.\s*Nogent-[Il]e-Rotrou, imprimerie Daupeley-Gouverneur\.</p>",
              '</p>\n<p class="centre">FIN DU TOME PREMIER.</p>', last)
files[texts[-1]] = last.encode("utf-8")

files["OEBPS/Text/titre.xhtml"] = ("""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>L'Histoire de Guillaume le Maréchal, tome I</title>
  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />
</head>
<body>
  <div class="titre">%s
  <p class="centre titre-livre">L'HISTOIRE<br />DE<br />GUILLAUME LE MARÉCHAL</p>
  <p class="centre">COMTE DE STRIGUIL ET DE PEMBROKE<br />RÉGENT D'ANGLETERRE DE 1216 A 1219</p>
  <p class="centre">POÈME FRANÇAIS</p>
  <p class="centre">PUBLIÉ POUR LA SOCIÉTÉ DE L'HISTOIRE DE FRANCE</p>
  <p class="centre">PAR PAUL MEYER</p>
  <hr />
  <p class="centre">TOME PREMIER</p>
  <hr />
  <p class="centre">A PARIS<br />LIBRAIRIE RENOUARD<br />H. LAURENS, SUCCESSEUR<br />LIBRAIRE DE LA SOCIÉTÉ DE L'HISTOIRE DE FRANCE<br />RUE DE TOURNON, N<sup>o</sup> 6</p>
  <p class="centre">M DCCC XCI</p>
  </div>
</body>
</html>
""" % front).encode("utf-8")

o = T("OEBPS/content.opf")
o = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>L'Histoire de Guillaume le Maréchal, tome I</dc:title>", o, flags=re.S)
o = re.sub(r"<dc:creator[^>]*>.*?</dc:creator>",
           '<dc:creator opf:role="edt" opf:file-as="Meyer, Paul">Paul Meyer</dc:creator>\n'
           '    <dc:publisher>Paris : Renouard (Société de l\'Histoire de France)</dc:publisher>', o, flags=re.S)
if "<dc:date>" in o:
    o = re.sub(r"<dc:date>.*?</dc:date>", "<dc:date>1891</dc:date>", o)
o = re.sub(r'\s*<item id="[^"]+" href="Images/[^"]+"[^>]*/>', "", o)
for n in [k for k in files if k.startswith("OEBPS/Images/")]:
    del files[n]
for n in texts:
    files[n] = re.sub(r'<div class="image">(<a id="page-\d+"></a>)<img [^>]*/></div>', r"<div>\1</div>",
                      T(n)).encode("utf-8")
o = o.replace('<item id="t001"', '<item id="titre" href="Text/titre.xhtml" media-type="application/xhtml+xml"/>\n    <item id="t001"', 1)
o = o.replace('<itemref idref="t001"/>', '<itemref idref="titre"/>\n    <itemref idref="t001"/>', 1)
assert 'idref="titre"' in o
files["OEBPS/content.opf"] = o.encode("utf-8")
n = T("OEBPS/toc.ncx")
for pid in re.findall(r'id="(page-\d+)"', front):
    n = n.replace('Text/texte-001.xhtml#%s"' % pid, 'Text/titre.xhtml#%s"' % pid)
nav = [("Page de titre", "Text/titre.xhtml"), ("Extrait du règlement", "Text/texte-001.xhtml#reglement"),
       ("Avant-propos", "Text/texte-001.xhtml#avant-propos"),
       ("L'Histoire de Guillaume le Maréchal", "Text/texte-001.xhtml#poeme")]
pts = "\n".join('    <navPoint id="nav-%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
                % (i, i, l.replace("&", "&amp;"), s_) for i, (l, s_) in enumerate(nav, 1))
n = re.sub(r"<navMap>.*?</navMap>", "<navMap>\n%s\n  </navMap>" % pts, n, flags=re.S)
n = re.sub(r"<docTitle><text>.*?</text></docTitle>", "<docTitle><text>L'Histoire de Guillaume le Maréchal, tome I</text></docTitle>", n, flags=re.S)
k = [len(nav)]


def po(m):
    k[0] += 1
    return 'playOrder="%d"' % k[0]


h, sep, tail = n.partition("<pageList>")
files["OEBPS/toc.ncx"] = (h + sep + re.sub(r'playOrder="\d+"', po, tail)).encode("utf-8")
c = T("OEBPS/Styles/livre.css")
c += ("\n.titre { margin-top: 2em; }\n.titre-livre { font-size: 1.6em; font-weight: bold; }\n"
      "hr { width: 30%; margin: 1.5em auto; }\n")
files["OEBPS/Styles/livre.css"] = c.encode("utf-8")
with zipfile.ZipFile(dst, "w") as zo:
    zo.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
    for name, data in files.items():
        zo.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
print("écrit", dst)
