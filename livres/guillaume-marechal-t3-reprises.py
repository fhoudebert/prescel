#!/usr/bin/env python3
"""Reprises du t. III de Guillaume le Maréchal après la chaîne OCR (DjVu + ABBYY) : page de titre et extrait
du règlement récrits d'après l'imprimé (la couche texte de ces pages est inutilisable), titre de la
traduction, titre et note de la table, puis table des matières (toc.ncx) refaite d'après les titres h1/h2
de l'EPUB final (les libellés suivent ainsi les corrections faites après abbyy_to_epub).

  python3 livres/guillaume-marechal-t3-reprises.py t3.epub t3-repris.epub
"""
import html
import re
import sys
import zipfile

TITRE = """<h1 id="titre">L'HISTOIRE<br />DE<br />GUILLAUME LE MARÉCHAL</h1>
<p class="centre">COMTE DE STRIGUIL ET DE PEMBROKE<br />RÉGENT D'ANGLETERRE DE 1216 À 1219</p>
<p class="centre">POÈME FRANÇAIS</p>
<p class="centre">PUBLIÉ POUR LA SOCIÉTÉ DE L'HISTOIRE DE FRANCE</p>
<p class="centre">Par Paul MEYER</p>
<p class="centre">TOME TROISIÈME</p>
<p class="centre">À PARIS<br />LIBRAIRIE RENOUARD<br />H. LAURENS, SUCCESSEUR<br />LIBRAIRE DE LA SOCIÉTÉ DE L'HISTOIRE DE FRANCE<br />RUE DE TOURNON, N° 6</p>
<p class="centre">M DCCCC I</p>
<h2 id="reglement">EXTRAIT DU RÈGLEMENT.</h2>
<p>Art. 14. — Le Conseil désigne les ouvrages à publier, et choisit les personnes les plus capables d'en préparer et d'en suivre la publication.</p>
<p>Il nomme, pour chaque ouvrage à publier, un Commissaire responsable, chargé d'en surveiller l'exécution.</p>
<p>Le nom de l'éditeur sera placé en tête de chaque volume.</p>
<p>Aucun volume ne pourra paraître sous le nom de la Société sans l'autorisation du Conseil, et s'il n'est accompagné d'une déclaration du Commissaire responsable, portant que le travail lui a paru mériter d'être publié.</p>
<p>Le Commissaire responsable soussigné déclare que le tome III de l'édition de l'Histoire de Guillaume le Maréchal, préparée par M. Paul Meyer, lui a paru digne d'être publié par la Société de l'Histoire de France.</p>
<p>Fait à Paris, le 25 octobre 1901.</p>
<p class="centre">Signé : L. DELISLE.</p>
<p>Certifié :</p>
<p>Le Secrétaire de la Société de l'Histoire de France,</p>
<p class="centre">A. DE BOISLISLE.</p>"""

NOTE_TABLE = ('<p class="note" id="note-271-1"><a href="#appel-271-1">1</a>. Les notes indiquées entre ( ) '
              'sont celles du troisième volume.</p>')

# (fichier, motif, remplacement, nombre attendu)
REPRISES = [
    ("partie-02", r"I\. L'auteur de L'HiSTomE\. Circonstances et date DE LA COMPOSITION\.",
     "I. L'auteur de l'<i>Histoire</i>. Circonstances et date de la composition.", 1),
    ("partie-04", r"ADDITIONS ET CORRECTIONS AU TOME IU\.", "ADDITIONS ET CORRECTIONS AU TOME III.", 1),
    ("partie-05", r'<p><a id="page-1"\s*/>L\'HISTOIRE DE GUILLAUME LE MARÉCHAL \(TRADUCTION ABRÉGÉE\)</p>',
     '<h1 id="traduction"><a id="page-1" />L\'HISTOIRE DE GUILLAUME LE MARÉCHAL<br />(TRADUCTION ABRÉGÉE)</h1>', 1),
    ("partie-06", r'<h2 id="(t\d+)"><a id="page-271"\s*/>TABLE1</h2>',
     '<h1 id="\\1"><a id="page-271" />TABLE<sup><a href="#note-271-1" id="appel-271-1">1</a></sup></h1>\n' + NOTE_TABLE, 1),
    ("partie-06", r" 1\. Les notes indiquées entre</p>", "</p>", 1),
    ("partie-06", r"Ansel, cinquième fils de Guil \(\) sont celles du troisième voli(<a id=\"page-272\"\s*/>) laume",
     "Ansel, cinquième fils de Guil\\1laume", 1),
]


def toc(docs, ordre, titre_livre, uid):
    """navMap : un point par h1, les h2 en dessous ; une partie sans h1 prend le titre de son fichier."""
    points = []
    for n in ordre:
        t = docs[n]
        court = n.split("OEBPS/", 1)[-1]
        rel = court[len("Text/"):] if court.startswith("Text/") else court
        hs = re.findall(r'<(h[12]) id="([^"]+)">(.*?)</h[12]>', t, re.S)
        if not hs or hs[0][0] != "h1":
            m = re.search(r"<title>(.*?)</title>", t)
            points.append(["h1", "Text/" + rel, html.unescape(m.group(1)) if m else rel, []])
        for niv, i, txt in hs:
            lab = re.sub(r"\s+", " ", html.unescape(re.sub(r"<sup>.*?</sup>|<[^>]+>", " ", txt))).strip()
            if niv == "h1":
                points.append(["h1", "Text/%s#%s" % (rel, i), lab, []])
            else:
                points[-1][3].append(("Text/%s#%s" % (rel, i), lab))
    out, k = [], 0
    for _, src, lab, enfants in points:
        k += 1
        out.append('<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/>'
                   % (k, k, html.escape(lab), src))
        for s2, l2 in enfants:
            k += 1
            out.append('<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/>'
                       '</navPoint>' % (k, k, html.escape(l2), s2))
        out.append("</navPoint>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
            '<head><meta name="dtb:uid" content="%s"/><meta name="dtb:depth" content="2"/>'
            '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>\n'
            '<docTitle><text>%s</text></docTitle>\n<navMap>\n%s\n</navMap>\n</ncx>\n'
            % (uid, html.escape(titre_livre), "\n".join(out)))


def main():
    src, dst = sys.argv[1:3]
    zin = zipfile.ZipFile(src)
    opf = next(n for n in zin.namelist() if n.endswith(".opf"))
    o = zin.read(opf).decode("utf-8")
    base = opf.rsplit("/", 1)[0] + "/"
    hrefs = dict(re.findall(r'<item\b[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', o))
    hrefs.update({i: h for h, i in re.findall(r'<item\b[^>]*?href="([^"]+)"[^>]*?id="([^"]+)"', o)})
    ordre = [base + hrefs[i] for i in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', o) if i in hrefs]
    docs = {n: zin.read(n).decode("utf-8") for n in ordre if n.endswith(".xhtml")}
    for n in docs:
        nom = n.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        t = docs[n]
        if nom == "partie-01":
            t = re.sub(r"(<body>\n?).*?(\n?</body>)", lambda m: m.group(1) + TITRE + m.group(2), t, count=1, flags=re.S)
            t = re.sub(r"<title>.*?</title>", "<title>Titre</title>", t)
        for f, motif, rep, k in REPRISES:
            if f == nom:
                t, nb = re.subn(motif, rep, t)
                assert nb == k, (f, motif[:60], nb)
        docs[n] = t
    ncx = next(n for n in zin.namelist() if n.endswith(".ncx"))
    nx = zin.read(ncx).decode("utf-8")
    uid = re.search(r'name="dtb:uid" content="([^"]+)"', nx).group(1)
    titre = html.unescape(re.search(r"<docTitle><text>(.*?)</text>", nx, re.S).group(1))
    zout = zipfile.ZipFile(dst, "w")
    for item in zin.infolist():
        if item.filename in docs:
            data = docs[item.filename].encode("utf-8")
        elif item.filename == ncx:
            data = toc(docs, [n for n in ordre if n in docs], titre, uid).encode("utf-8")
        else:
            data = zin.read(item.filename)
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    print("Reprises appliquées : page de titre, %d remplacements, table des matières refaite" % len(REPRISES))


if __name__ == "__main__":
    main()
