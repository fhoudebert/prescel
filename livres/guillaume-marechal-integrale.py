#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L'Histoire de Guillaume le Maréchal (éd. Paul Meyer, 1891-1901) : les trois tomes en un seul EPUB, avec un
sommaire qui permet d'aller partout.

- les tomes sont repris tels que les chaînes Gutenberg les produisent (epub/Guillaume_le_Marechal_T1.epub,
  T2, T3), marques de relecture retirées ; chaque tome garde sa feuille de style ;
- page de titre commune, puis un sommaire : pour chaque tome ses parties (introduction et ses chapitres,
  chronologie, traduction, table…), le poème par tranches de 500 vers, le vocabulaire et la table par
  lettre ; la table des matières de la liseuse (toc.ncx) suit le même plan, les numéros de page des
  tomes I et II (« I-12 », « II-338 ») dans la liste des pages ;
- renvois au poème reliés au vers (au numéro imprimé le plus proche, de quatre en quatre) : numéros
  de vers de la table du t. III et du vocabulaire du t. II, « [139] » de la traduction abrégée,
  « v. 14860 », « V. 895 » des notes, de l'introduction et des errata ; dans le poème, un lien tous les cent vers mène à la
  traduction abrégée du passage.

Usage :
  python3 livres/guillaume-marechal-integrale.py epub/Guillaume_le_Marechal_T1.epub \\
      epub/Guillaume_le_Marechal_T2.epub epub/Guillaume_le_Marechal_T3.epub epub/Guillaume_le_Marechal.epub
"""
import bisect
import html
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET

ICI = os.path.dirname(os.path.abspath(__file__))
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"
TOMES = ["I", "II", "III"]
DERNIER_VERS = 19214
TAG = re.compile(r"(<[^>]+>)")


def esc(s):
    return html.escape(s, quote=False)


def initiale(s):
    c = unicodedata.normalize("NFD", s.strip())[:1].upper()
    return c if "A" <= c <= "Z" else None


def joli(label):
    """Titres en capitales du t. III → casse ordinaire ; espaces laissées par l'italique."""
    label = html.unescape(label).strip()
    label = re.sub(r"(['’]) ", r"\1", label)
    label = re.sub(r" ([.,])", r"\1", label).rstrip(".")
    if label.isupper():
        label = label.lower()
        label = label[0].upper() + label[1:]
        label = re.sub(r"guillaume le maréchal", "Guillaume le Maréchal", label)
        label = re.sub(r"\btome iii\b", "tome III", label)
        label = label.replace("(traduction abrégée)", "— traduction abrégée")
    return label


class Tome:
    def __init__(self, num, path, tmp):
        self.num, self.prefixe = num, "t%d-" % num
        sans = os.path.join(tmp, "t%d.epub" % num)
        subprocess.run([sys.executable, os.path.join(ICI, "..", "epub_review.py"), path, "--unmark", "-o", sans],
                       check=True, stdout=subprocess.DEVNULL)
        z = zipfile.ZipFile(sans)
        self.data = {n: z.read(n) for n in z.namelist()}
        opf = self.data["OEBPS/content.opf"].decode("utf-8")
        items = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf))
        self.spine = [items[i] for i in re.findall(r'<itemref idref="([^"]+)"', opf)]
        self.css = self.data["OEBPS/Styles/livre.css"].decode("utf-8")
        self.textes = {h: self.data["OEBPS/" + h].decode("utf-8") for h in self.spine}
        ncx = ET.fromstring(self.data["OEBPS/toc.ncx"])
        self.nav = [self.point(p) for p in ncx.find(NCX + "navMap").findall(NCX + "navPoint")]
        self.pages = [(t.find(NCX + "navLabel/" + NCX + "text").text, t.find(NCX + "content").get("src"))
                      for t in ncx.iter(NCX + "pageTarget")]
        self.titre = ET.fromstring(self.data["OEBPS/content.opf"]).find(
            ".//{http://purl.org/dc/elements/1.1/}title").text

    def point(self, p):
        return (joli(p.find(NCX + "navLabel/" + NCX + "text").text), p.find(NCX + "content").get("src"),
                [self.point(q) for q in p.findall(NCX + "navPoint")])

    def nom(self, h):
        """Text/texte-001.xhtml → t1-texte-001.xhtml"""
        return self.prefixe + os.path.basename(h)


# --------------------------------------------------------------------------
# Liens
# --------------------------------------------------------------------------

def par_texte(s, fonction, hors_liens=True):
    """Applique fonction aux nœuds de texte (pas dans un lien existant)."""
    parts = TAG.split(s)
    dans_a = 0
    for i, p in enumerate(parts):
        if i % 2:
            if re.match(r"<a\s[^>]*href", p):
                dans_a += 1
            elif p.startswith("</a") and dans_a:
                dans_a -= 1
        elif p and not (hors_liens and dans_a):
            parts[i] = fonction(p)
    return "".join(parts)


class Vers:
    """Numéros de vers imprimés du poème (t. I et II) : ancre v1234 sur chacun."""
    def __init__(self):
        self.nums, self.cibles = [], []

    def ancrer(self, fichier, s):
        vus = set()

        def ancre(m):
            n = int(m.group(1))
            if n in vus:
                return m.group(0)
            vus.add(n)
            self.nums.append(n)
            self.cibles.append("%s#v%d" % (fichier, n))
            return '<span class="numvers" id="v%d">%d</span>' % (n, n)
        return re.sub(r'<span class="numvers">(\d+)</span>', ancre, s)

    def fin(self):
        ordre = sorted(range(len(self.nums)), key=lambda k: self.nums[k])
        self.nums = [self.nums[k] for k in ordre]
        self.cibles = [self.cibles[k] for k in ordre]

    def cible(self, n, depuis):
        if not 1 <= n <= DERNIER_VERS or not self.nums:
            return None
        k = max(0, bisect.bisect_right(self.nums, n) - 1)
        c = self.cibles[k]
        return c[len(depuis):] if c.startswith(depuis + "#") else c


def lier_v(s, fichier, vers):
    """« v. 14860 », « v. 19169-76 », « vv. 4312-4318 »."""
    def f(t):
        def r(m):
            c = vers.cible(int(m.group(2)), fichier)
            return '%s<a href="%s">%s</a>' % (m.group(1), c, m.group(2)) if c else m.group(0)
        # « V. 895 » (errata) aussi, mais pas « t. V, 23 » ni « ch. V. 3 »
        return re.sub(r"(?<!t\. )(?<!ch\. )(\b(?:vv?|V)\.\s?)(\d{1,5})(?!\d)", r, t)
    return par_texte(s, f)


def lier_nombres(s, fichier, vers, classe=None):
    """Table, vocabulaire : chaque numéro de vers (hors parenthèses) mène au vers."""
    def para(m):
        if classe and classe not in m.group(1):
            return m.group(0)
        prof = [0]

        def f(t):
            out, pos = [], 0
            for mm in re.finditer(r"[()]|(?<![\w.])(\d{1,5})(?![\w°])", t):
                out.append(t[pos:mm.start()])
                pos = mm.end()
                g = mm.group(0)
                if g == "(":
                    prof[0] += 1
                elif g == ")":
                    prof[0] = max(0, prof[0] - 1)
                elif prof[0] == 0:
                    c = vers.cible(int(g), fichier)
                    if c:
                        out.append('<a href="%s">%s</a>' % (c, g))
                        continue
                out.append(g)
            out.append(t[pos:])
            return "".join(out)
        return m.group(1) + par_texte(m.group(2), f) + m.group(3)
    return re.sub(r"(<p[^>]*>)(.*?)(</p>)", para, s, flags=re.S)


def lier_traduction(s, fichier, vers):
    """« [139] » de la traduction abrégée : lien au vers et ancre tr139 pour le retour."""
    vus, ancres = set(), []

    def f(t):
        def r(m):
            n = int(m.group(1))
            c = vers.cible(n, fichier)
            if not c:
                return m.group(0)
            ident = ""
            if n not in vus:
                vus.add(n)
                ident = ' id="tr%d"' % n
                ancres.append(n)
            return '[<a href="%s"%s>%s</a>%s]' % (c, ident, m.group(1), m.group(2) or "")
        return re.sub(r"\[(\d{1,5})((?:\s?[-–]\s?\d{1,5})?)\]", r, t)
    return par_texte(s, f), sorted(ancres)


def retours(s, fichier_trad, ancres_trad):
    """Dans le poème, tous les cent vers : lien vers la traduction du passage."""
    fait = set()

    def r(m):
        n = int(m.group(1))
        tranche = n // 100
        if tranche in fait or not ancres_trad:
            return m.group(0)
        fait.add(tranche)
        k = bisect.bisect_right(ancres_trad, n) - 1
        if k < 0:
            return m.group(0)
        return m.group(0) + ' <a class="trad" href="%s#tr%d" title="Traduction abrégée">[trad.]</a>' % (
            fichier_trad, ancres_trad[k])
    return re.sub(r'<span class="numvers" id="v(\d+)">\d+</span>', r, s)


def lettres(s, classe, prefixe):
    """Ancre sur la première entrée de chaque lettre (vocabulaire, table) : une lettre compte quand
    trois entrées de suite la portent, après la lettre précédente (une entrée mal classée ou mal lue
    ne la déplace pas)."""
    motif = re.compile(r"<p((?: class=\"%s\")?)>(.{0,80})" % classe if classe else r"<p()>(.{0,80})")
    entrees = list(motif.finditer(s))
    ini = [initiale(re.sub(r"<[^>]+>", "", m.group(2))) for m in entrees]
    choisies, derniere = {}, ""
    for k, c in enumerate(ini):
        if c and c > derniere and ini[k + 1:k + 3] == [c, c]:
            choisies[k] = c
            derniere = c
    out, pos = [], 0
    for k, m in enumerate(entrees):
        if k in choisies:
            out.append(s[pos:m.start()])
            out.append('<p%s id="%s-%s">' % (m.group(1), prefixe, choisies[k].lower()))
            pos = m.start() + len("<p%s>" % m.group(1))
    out.append(s[pos:])
    return "".join(out), [choisies[k] for k in sorted(choisies)]


# --------------------------------------------------------------------------
# Assemblage
# --------------------------------------------------------------------------

CSS_COMMUN = """body { font-family: serif; margin: 0 1em; }
h1 { text-align: center; font-size: 1.4em; margin: 1.5em 0 1em; }
h2 { font-size: 1.15em; margin: 1.5em 0 0.4em; }
h3 { font-size: 1em; margin: 1em 0 0.3em; }
p { margin: 0.2em 0; }
p.t1 { text-align: center; font-size: 1.6em; font-weight: bold; margin-top: 2.5em; }
p.t2 { text-align: center; font-size: 1em; margin: 0.5em 0; }
p.t3 { text-align: center; font-size: 0.85em; margin: 0.3em 0; }
ul { list-style: none; padding-left: 1.2em; margin: 0.2em 0; }
p.grille { line-height: 1.8; }
p.grille a { margin-right: 0.6em; white-space: nowrap; }
"""

TITRE = """<p class="t1">L'HISTOIRE DE GUILLAUME LE MARÉCHAL</p>
<p class="t2">COMTE DE STRIGUIL ET DE PEMBROKE<br />RÉGENT D'ANGLETERRE DE 1216 À 1219</p>
<p class="t3">POÈME FRANÇAIS</p>
<p class="t3">PUBLIÉ POUR LA SOCIÉTÉ DE L'HISTOIRE DE FRANCE</p>
<p class="t2">PAR PAUL MEYER</p>
<p class="t2">TOMES I À III</p>
<p class="t3">PARIS<br />LIBRAIRIE RENOUARD, H. LAURENS, SUCCESSEUR<br />1891-1901</p>
<p class="t3">Les trois tomes réunis : tome I (1891), poème, vers 1 à 10152 ; tome II (1894), vers 10153 à 19214
et vocabulaire ; tome III (1901), introduction, chronologie, traduction abrégée et table.
Les numéros de vers de la table, du vocabulaire, de la traduction et des notes mènent au vers.</p>"""


def xhtml(titre, corps, css):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
            '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head>\n  <title>%s</title>\n  <link href="../Styles/%s" rel="stylesheet" type="text/css" />\n'
            '</head>\n<body>\n%s\n</body>\n</html>\n' % (esc(titre), css, corps))


def main():
    t1, t2, t3, dst = sys.argv[1:5]
    tmp = tempfile.mkdtemp()
    tomes = [Tome(k + 1, p, tmp) for k, p in enumerate((t1, t2, t3))]
    vers = Vers()
    sorties = {}                       # nom de fichier → contenu
    for t in tomes:
        for h, s in t.textes.items():
            s = s.replace("../Styles/livre.css", "../Styles/t%d.css" % t.num)
            if t.num < 3:
                s = vers.ancrer(t.nom(h), s)
            sorties[t.nom(h)] = s
    vers.fin()
    # traduction, table, vocabulaire, renvois « v. »
    trad = "t3-partie-05.xhtml"
    sorties[trad], ancres_trad = lier_traduction(sorties[trad], trad, vers)
    sorties["t3-partie-06.xhtml"] = lier_nombres(sorties["t3-partie-06.xhtml"], "t3-partie-06.xhtml", vers)
    sorties["t2-vocabulaire.xhtml"] = lier_nombres(sorties["t2-vocabulaire.xhtml"], "t2-vocabulaire.xhtml", vers,
                                                    classe="glossaire")
    for n in list(sorties):
        if n != "t3-partie-06.xhtml":
            sorties[n] = lier_v(sorties[n], n, vers)
    for n in list(sorties):
        if n.startswith(("t1-texte", "t2-texte")):
            sorties[n] = retours(sorties[n], trad, ancres_trad)
    sorties["t2-vocabulaire.xhtml"], lettres_voc = lettres(sorties["t2-vocabulaire.xhtml"], "glossaire", "voc")
    s6 = sorties["t3-partie-06.xhtml"]
    i = s6.index("</h1>")
    corps, lettres_table = lettres(s6[i:], None, "table")
    sorties["t3-partie-06.xhtml"] = s6[:i] + corps

    # sommaire : arbre (titre, src, enfants)
    def src(t, s):
        h, _, frag = s.partition("#")
        return t.nom(h) + ("#" + frag if frag else "")

    def reprise(t, nav):
        return [(lab, src(t, s), reprise(t, enf)) for lab, s, enf in nav]

    def tranches(premier, dernier):
        out = []
        for a in range(premier - premier % 500, dernier + 1, 500):
            debut = max(a, premier)
            c = vers.cible(debut, "")
            if c:
                out.append(("Vers %d" % debut, c, []))
        return out

    arbre = []
    nav1 = reprise(tomes[0], tomes[0].nav)
    nav2 = reprise(tomes[1], tomes[1].nav)
    nav3 = reprise(tomes[2], tomes[2].nav)
    for nav, (a, b) in ((nav1, (1, 10152)), (nav2, (10153, DERNIER_VERS))):
        for k, (lab, s, enf) in enumerate(nav):
            if lab.startswith("L'Histoire de Guillaume le Maréchal"):
                nav[k] = ("Le poème, vers %d à %d" % (a, b), s, tranches(a, b))
    for k, (lab, s, enf) in enumerate(nav2):
        if lab.startswith("Vocabulaire"):
            nav2[k] = (lab, s, [(c, "t2-vocabulaire.xhtml#voc-%s" % c.lower(), []) for c in lettres_voc])
    for k, (lab, s, enf) in enumerate(nav3):
        if "traduction" in lab:
            enf = []
            for a in range(0, DERNIER_VERS + 1, 1000):
                j = bisect.bisect_left(ancres_trad, max(a, 1))
                if j < len(ancres_trad) and ancres_trad[j] < a + 1000:
                    enf.append(("Vers %d" % max(a, 1), "%s#tr%d" % (trad, ancres_trad[j]), []))
            nav3[k] = ("Traduction abrégée du poème", s, enf)
        elif lab == "Table":
            nav3[k] = (lab, s, [(c, "t3-partie-06.xhtml#table-%s" % c.lower(), []) for c in lettres_table])
        elif lab.startswith("L'histoire de Guillaume le Maréchal"):
            nav3[k] = ("Page de titre", s, enf)
    for t, nav in zip(tomes, (nav1, nav2, nav3)):
        arbre.append(("Tome %s" % TOMES[t.num - 1], nav[0][1], nav))

    def html_arbre(noeuds, niveau=0):
        out = ["<ul>"]
        for lab, s, enf in noeuds:
            if enf and all(not e[2] and len(e[0]) <= 12 for e in enf):     # tranches de vers, lettres
                grille = " ".join('<a href="%s">%s</a>' % (e[1], esc(e[0].replace("Vers ", ""))) for e in enf)
                out.append('<li><a href="%s">%s</a><p class="grille">%s</p></li>' % (s, esc(lab), grille))
            else:
                out.append('<li><a href="%s">%s</a>%s</li>' % (s, esc(lab), html_arbre(enf, niveau + 1) if enf else ""))
        out.append("</ul>")
        return "\n".join(out)
    corps = ['<h1 id="sommaire">Sommaire</h1>']
    for lab, s, enf in arbre:
        corps.append('<h2><a href="%s">%s</a></h2>' % (s, esc(lab)))
        corps.append(html_arbre(enf))
    sorties["sommaire.xhtml"] = xhtml("Sommaire", "\n".join(corps), "commun.css")
    sorties["titre.xhtml"] = xhtml("L'Histoire de Guillaume le Maréchal", TITRE, "commun.css")

    # écriture
    ordre = ["titre.xhtml", "sommaire.xhtml"] + [t.nom(h) for t in tomes for h in t.spine]
    z = zipfile.ZipFile(dst, "w")
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)

    def w(n, d):
        z.writestr(n, d, compress_type=zipfile.ZIP_DEFLATED)
    w("META-INF/container.xml", '<?xml version="1.0"?>\n<container version="1.0" '
      'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n<rootfiles><rootfile '
      'full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n</container>\n')
    w("OEBPS/Styles/commun.css", CSS_COMMUN)
    for t in tomes:
        w("OEBPS/Styles/t%d.css" % t.num, t.css + "\na.trad { font-size: 0.75em; text-decoration: none; }\n")
    for n in ordre:
        w("OEBPS/Text/" + n, sorties[n])
    bid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "prescel/guillaume-le-marechal-integrale"))
    man = ['    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
           '    <item id="css0" href="Styles/commun.css" media-type="text/css"/>']
    man += ['    <item id="css%d" href="Styles/t%d.css" media-type="text/css"/>' % (t.num, t.num) for t in tomes]
    man += ['    <item id="x%d" href="Text/%s" media-type="application/xhtml+xml"/>' % (k, n) for k, n in enumerate(ordre)]
    spine = ['    <itemref idref="x%d"/>' % k for k in range(len(ordre))]
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" '
           'unique-identifier="bookid" version="2.0">\n  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
           'xmlns:opf="http://www.idpf.org/2007/opf">\n'
           "    <dc:title>L'Histoire de Guillaume le Maréchal (tomes I à III)</dc:title>\n"
           '    <dc:creator opf:role="edt" opf:file-as="Meyer, Paul">Paul Meyer</dc:creator>\n'
           "    <dc:publisher>Paris : Renouard (Société de l'Histoire de France)</dc:publisher>\n"
           '    <dc:date>1891</dc:date>\n    <dc:language>fr</dc:language>\n'
           "    <dc:subject>Guillaume le Maréchal, comte de Pembroke</dc:subject>\n"
           '    <dc:identifier id="bookid">%s</dc:identifier>\n'
           '  </metadata>\n  <manifest>\n%s\n  </manifest>\n  <spine toc="ncx">\n%s\n  </spine>\n'
           '  <guide>\n    <reference type="title-page" title="Titre" href="Text/titre.xhtml"/>\n'
           '    <reference type="toc" title="Sommaire" href="Text/sommaire.xhtml"/>\n  </guide>\n</package>\n'
           % (bid, "\n".join(man), "\n".join(spine)))
    w("OEBPS/content.opf", opf)
    compteur, ordres, ids = [0], {}, [0]

    def ordre_de(cible):                      # même cible, même playOrder (exigé par epubcheck)
        if cible not in ordres:
            compteur[0] += 1
            ordres[cible] = compteur[0]
        ids[0] += 1
        return ids[0], ordres[cible]

    def points(noeuds, prof):
        out = []
        for lab, s, enf in noeuds:
            k, o = ordre_de(s)
            out.append('%s<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
                       '<content src="Text/%s"/>' % ("  " * prof, k, o, esc(lab), s))
            out += points(enf, prof + 1)
            out.append("%s</navPoint>" % ("  " * prof))
        return out
    nav = points([("Page de titre", "titre.xhtml", []), ("Sommaire", "sommaire.xhtml", [])] + arbre, 1)
    pages = []
    for t in tomes:
        for lab, s in t.pages:
            if lab and lab != "NP":
                k, o = ordre_de(src(t, s))
                pages.append('  <pageTarget id="p%d" type="normal" value="%d" playOrder="%d"><navLabel><text>%s-%s'
                             '</text></navLabel><content src="Text/%s"/></pageTarget>'
                             % (k, k, o, TOMES[t.num - 1], esc(lab), src(t, s)))
    ncx = ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" '
           'version="2005-1">\n<head><meta name="dtb:uid" content="%s"/><meta name="dtb:depth" content="4"/>'
           '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>\n'
           "<docTitle><text>L'Histoire de Guillaume le Maréchal</text></docTitle>\n<navMap>\n%s\n</navMap>\n"
           '<pageList><navLabel><text>Pages</text></navLabel>\n%s\n</pageList>\n</ncx>\n'
           % (bid, "\n".join(nav), "\n".join(pages)))
    w("OEBPS/toc.ncx", ncx)
    z.close()
    nliens = sum(s.count('<a href="t1-') + s.count('<a href="t2-') + s.count('<a href="#v') for s in sorties.values())
    print("Fichiers : %d ; vers repérés : %d ; renvois au poème : %d ; traduction : %d ancres"
          % (len(ordre), len(vers.nums), nliens, len(ancres_trad)))


if __name__ == "__main__":
    main()
