#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finitions du tome II de L'Histoire de Guillaume le Maréchal (éd. Paul Meyer, 1894), après
pdf_vers.py sur le PDF Gallica bpt6k203427s (vers 10153 à 19214) :
- page de titre transcrite du scan ; pages liminaires illisibles (cachet, garde) retirées,
  leurs ancres de page gardées ;
- titre de départ du poème ;
- métadonnées.
- le vocabulaire (fin du volume), préparé à part par pdf_glossaire.py (et réparé par
  epub_abimes.py), est ajouté en dernier fichier si on le donne en troisième argument, avec
  ses numéros de page (pagination Gallica).
Usage : guillaume-marechal-t2-finitions.py entree.epub sortie.epub [vocabulaire.xhtml]
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
b = t.index('<p class="vers">')
front = "".join(re.findall(r'<a id="page-\d+"></a>', t[a:b]))
t = t[:a] + '\n<h1 id="poeme">L\'HISTOIRE DE GUILLAUME LE MARÉCHAL</h1>\n' + t[b:]
files[texts[0]] = t.encode("utf-8")

files["OEBPS/Text/titre.xhtml"] = ("""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>L'Histoire de Guillaume le Maréchal, tome II</title>
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
  <p class="centre">TOME SECOND</p>
  <hr />
  <p class="centre">A PARIS<br />LIBRAIRIE RENOUARD<br />H. LAURENS, SUCCESSEUR<br />LIBRAIRE DE LA SOCIÉTÉ DE L'HISTOIRE DE FRANCE<br />RUE DE TOURNON, N<sup>o</sup> 6</p>
  <p class="centre">M DCCC XCIV</p>
  </div>
</body>
</html>
""" % front).encode("utf-8")

o = T("OEBPS/content.opf")
o = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>L'Histoire de Guillaume le Maréchal, tome II</dc:title>", o, flags=re.S)
o = re.sub(r"<dc:creator[^>]*>.*?</dc:creator>",
           '<dc:creator opf:role="edt" opf:file-as="Meyer, Paul">Paul Meyer</dc:creator>\n'
           '    <dc:publisher>Paris : Renouard (Société de l\'Histoire de France)</dc:publisher>', o, flags=re.S)
o = re.sub(r'\s*<item id="[^"]+" href="Images/[^"]+"[^>]*/>', "", o)
for n in [k for k in files if k.startswith("OEBPS/Images/")]:
    del files[n]
for n in texts:
    files[n] = re.sub(r'<div class="image">(<a id="page-\d+"></a>)<img [^>]*/></div>', r"<div>\1</div>",
                      T(n)).encode("utf-8")
o = o.replace('<item id="t001"', '<item id="titre" href="Text/titre.xhtml" media-type="application/xhtml+xml"/>\n    <item id="t001"', 1)
o = o.replace('<itemref idref="t001"/>', '<itemref idref="titre"/>\n    <itemref idref="t001"/>', 1)
files["OEBPS/content.opf"] = o.encode("utf-8")
n = T("OEBPS/toc.ncx")
for pid in re.findall(r'id="(page-\d+)"', front):
    n = n.replace('Text/texte-001.xhtml#%s"' % pid, 'Text/titre.xhtml#%s"' % pid)
nav = [("Page de titre", "Text/titre.xhtml"), ("L'Histoire de Guillaume le Maréchal", "Text/texte-001.xhtml#poeme")]
pts = "\n".join('    <navPoint id="nav-%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
                % (i, i, l, s_) for i, (l, s_) in enumerate(nav, 1))
n = re.sub(r"<navMap>.*?</navMap>", "<navMap>\n%s\n  </navMap>" % pts, n, flags=re.S)
n = re.sub(r"<docTitle><text>.*?</text></docTitle>", "<docTitle><text>L'Histoire de Guillaume le Maréchal, tome II</text></docTitle>", n, flags=re.S)
k = [len(nav)]


def po(m):
    k[0] += 1
    return 'playOrder="%d"' % k[0]


h, sep, tail = n.partition("<pageList>")
files["OEBPS/toc.ncx"] = (h + sep + re.sub(r'playOrder="\d+"', po, tail)).encode("utf-8")
if len(sys.argv) > 3:                           # vocabulaire en fin de volume
    import os
    voc = open(sys.argv[3], encoding="utf-8").read()
    files["OEBPS/Text/vocabulaire.xhtml"] = voc.encode("utf-8")
    o = T("OEBPS/content.opf")
    o = o.replace("</manifest>", '  <item id="vocabulaire" href="Text/vocabulaire.xhtml" '
                  'media-type="application/xhtml+xml"/>\n  </manifest>', 1)
    o = re.sub(r'(<itemref idref="[^"]+"\s*/>)(\s*</spine>)', r'\1\n    <itemref idref="vocabulaire"/>\2', o, count=1)
    files["OEBPS/content.opf"] = o.encode("utf-8")
    pag = os.path.join(os.path.expanduser("~"), ".cache", "prescel", "bpt6k203427s", "pagination.xml")
    labels = re.findall(r"<numero>([^<]*)</numero>", open(pag, encoding="utf-8").read()) if os.path.exists(pag) else []
    n = T("OEBPS/toc.ncx")
    have = set(re.findall(r'#(page-\d+)"', n))
    extra = ""
    for pid in re.findall(r'id="(page-\d+)"', voc):
        if pid in have:
            continue
        v = int(pid[5:])
        lab = labels[v - 1] if v <= len(labels) else str(v)
        extra += ('    <pageTarget id="pv-%d" type="%s" playOrder="1"><navLabel><text>%s</text></navLabel>'
                  '<content src="Text/vocabulaire.xhtml#%s"/></pageTarget>\n'
                  % (v, "normal" if lab.isdigit() else "front", lab, pid))
    n = n.replace("</pageList>", extra + "</pageList>")
    n = re.sub(r"(</navPoint>)(\s*</navMap>)", r'\1\n    <navPoint id="nav-voc" playOrder="1"><navLabel>'
               r'<text>Vocabulaire</text></navLabel><content src="Text/vocabulaire.xhtml"/></navPoint>\2', n, count=1)
    k2 = [0]

    def po2(m):
        k2[0] += 1
        return 'playOrder="%d"' % k2[0]

    files["OEBPS/toc.ncx"] = re.sub(r'playOrder="\d+"', po2, n).encode("utf-8")
c = T("OEBPS/Styles/livre.css")
c += ("\n.titre { margin-top: 2em; }\n.titre-livre { font-size: 1.6em; font-weight: bold; }\n"
      "hr { width: 30%; margin: 1.5em auto; }\n"
      "p.glossaire { text-indent: -1.5em; margin: 0.2em 0 0.2em 1.5em; }\n")
files["OEBPS/Styles/livre.css"] = c.encode("utf-8")
with zipfile.ZipFile(dst, "w") as zo:
    zo.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
    for name, data in files.items():
        zo.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
print("écrit", dst)
