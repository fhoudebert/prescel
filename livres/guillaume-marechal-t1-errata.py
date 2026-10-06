#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Errata de l'avant-propos du tome I de L'Histoire de Guillaume le Maréchal (éd. P. Meyer),
appliqué au texte : seules les leçons à lire (« lis. ») le sont ; les corrections proposées
(« corr. … ? »), les remarques et les titres courants (retirés de l'EPUB) restent dans
l'avant-propos, qui n'est pas modifié. Chaque correction est cherchée dans son contexte et
doit s'y trouver une seule fois.
Usage : guillaume-marechal-t1-errata.py entree.epub sortie.epub
"""
import re
import sys
import zipfile

# (vers, avant, après) — relus sur l'avant-propos du tome I
ERRATA = [
    (485, "broche taill[i][é]e", "broche taill[ié]e"),
    (895, "Si s'enlref[i]érent ad eslaz", "Si s'enlref[i]érent a deslaz"),
    (3865, "eorurent ad eslaz", "eorurent a deslaz"),
    (1516, "Et erra par totes [les] terres", "&amp; erra par totes [les] terres"),
    (1518, "En France e en Avauterre", "E en France e en Avauterre"),
    (1715, "Ensanglanta terre tote", "Ensanglanta la terre tote"),
    (142, "142 desmelée.", "142 desmeslée."),          # note du v. 142
    (843, "843 ermerent", "843 ermérent"),             # note du v. 843
    (631, "— 661 Bein. —", "— 631 Bein. —"),           # numéro de la note du v. 631
]

src, dst = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src)
files = {n: z.read(n) for n in z.namelist()}
done, todo = [], []
for v, old, new in ERRATA:
    hits = [n for n in files if n.startswith("OEBPS/Text/texte") and files[n].decode("utf-8").count(old) == 1]
    total = sum(files[n].decode("utf-8").count(old) for n in files if n.startswith("OEBPS/Text/texte"))
    if total == 1 and hits:
        n = hits[0]
        files[n] = files[n].decode("utf-8").replace(old, new).encode("utf-8")
        done.append((v, old, new))
    elif total == 0 and any(files[n].decode("utf-8").count(new) for n in files if n.startswith("OEBPS/Text/texte")):
        done.append((v, old, "déjà conforme"))
    else:
        todo.append((v, old, total))
# pour la note de transcription d'epub_gutenberg.py
opf = files["OEBPS/content.opf"].decode("utf-8")
opf = re.sub(r'\s*<meta name="prescel:errata"[^>]*/>', "", opf)
n_ok = len({v for v, a, b in done})
n_all = len({v for v, a, b in ERRATA})
opf = opf.replace("</metadata>", '  <meta name="prescel:errata" content="%d/%d"/>\n  </metadata>' % (n_ok, n_all), 1)
files["OEBPS/content.opf"] = opf.encode("utf-8")
with zipfile.ZipFile(dst, "w") as zo:
    zo.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
    for name, data in files.items():
        zo.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
for v, a, b in done:
    print("v. %d : %s → %s" % (v, a, b))
for v, a, n in todo:
    print("v. %d : « %s » trouvé %d fois — à faire à la main" % (v, a, n))
