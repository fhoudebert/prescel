#!/usr/bin/env python3
"""Replace les folios du manuscrit (« (f. 12 b) ») d'un poème édité vers par vers (pdf_vers.py), d'après une
autre numérisation de la même édition dont la couche texte les lit bien (PDF Google Livres).

Dans l'EPUB, l'OCR a souvent cassé ces repères de marge : moitié dans le vers, moitié en manchette
(« tote ; (/• » + « ^ ^ ^) »), chiffres lus de travers (« (f. 1 1 h) »), ou ponctuation du vers rejetée en
marge (« » », « ; »). Le script :
  1. lit dans la référence chaque folio et le vers imprimé à sa hauteur (même page, même ligne) ;
  2. retrouve ce vers dans l'EPUB, dans l'ordre, par ressemblance des lettres ;
  3. efface tous les fragments de folio des vers de l'EPUB (texte et manchettes) et pose le folio de la
     référence en manchette du vers retrouvé ;
  4. remet dans le vers la ponctuation rejetée en marge.
Les manchettes de date (« (31 juillet) », « (1192) ») ne sont pas touchées ; les autres manchettes
douteuses sont listées dans le journal.

  python3 epub_folios.py t1.epub google-t1.pdf -o t1-folios.epub --report folios.tsv
"""
import argparse
import difflib
import html
import re
import zipfile

import epub_ocr_vers as O
from epub_vers_reference import squelette

NB = " "
PRIV = "-"
FOLIO_REF = re.compile(r"\(\s*f\s*\.?\s*(\d+)\s*\.?\s*([abcd])?\s*\)")
# fragments de folio dans le texte d'un vers (fin de vers), ou manchette qui en est un morceau
FRAG_TEXTE = re.compile(r"[ %s]*[({]\s*(?:[f/ƒ]|if)[^()\w]{0,3}[\w ]{0,6}[^()\s]{0,4}\)?[ %s]*$" % (NB, NB))
DEBUT_TEXTE = re.compile(r"^[ %s]*\(\s*f\s*\.?\s*\d+\s*[abcd]?\s*\)[ %s]*" % (NB, NB))
DATE = re.compile(r"\d{3,4}\)|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre")


def folio_txt(n, col):
    return "(f. %s%s)" % (n, " " + col if col else "")


def folios_reference(pdf):
    """[(texte du vers à hauteur du folio, folio)] dans l'ordre du livre."""
    import pymupdf
    out = []
    for page in pymupdf.open(pdf):
        lignes = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t:
                    lignes.append((l["bbox"], t))
        for bb, t in lignes:
            m = FOLIO_REF.search(t)
            if not m:
                continue
            reste = FOLIO_REF.sub("", t).strip()
            if len(squelette(reste)) < 8:                 # folio seul sur sa ligne : le vers à sa hauteur
                y = (bb[1] + bb[3]) / 2
                voisins = [(abs((b2[1] + b2[3]) / 2 - y), t2) for b2, t2 in lignes
                           if t2 != t and b2[1] <= y <= b2[3] and len(squelette(t2)) >= 8]
                if not voisins:
                    continue
                reste = min(voisins)[1]
            reste = re.sub(r"^\d{2,5}\s+", "", reste)      # numéro de vers
            out.append((reste, folio_txt(m.group(1), m.group(2))))
    return out


def est_fragment(man):
    """Une manchette qui n'est qu'un morceau de folio (« 1 d) », « ^ ^ ^) », « (f. 1 1 h) »)."""
    v = html.unescape(man).strip()
    if DATE.search(v) and not re.match(r"\(?\s*[f/]", v):
        return False
    return bool(re.fullmatch(r"[\s(]*(?:[f/ƒ]|if)?[\s.'•^\-]*[\d\s^•]*[abcdh^]?\s*\)?[\s\d]*", v)) \
        or bool(re.match(r"\(\s*(?:[f/ƒ]|if|Z)", v)) \
        or bool(re.fullmatch(r"\(?[\w^\-]{0,3}\s?\d{1,2}\s?[A-Za-z]?\^?\)?|M[a-d]\)", v))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("reference", help="PDF à couche texte de la même édition (Google Livres)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--report", help="journal TSV")
    opts = ap.parse_args()

    refs = folios_reference(opts.reference)
    zin = zipfile.ZipFile(opts.epub)
    opf = next(n for n in zin.namelist() if n.endswith(".opf"))
    o = zin.read(opf).decode("utf-8")
    base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
    hrefs = dict(re.findall(r'<item\b[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', o))
    hrefs.update({i: h for h, i in re.findall(r'<item\b[^>]*?href="([^"]+)"[^>]*?id="([^"]+)"', o)})
    ordre = [base + hrefs[i] for i in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', o) if i in hrefs]

    # 1. tous les vers de l'EPUB, dans l'ordre de lecture
    docs = {n: zin.read(n).decode("utf-8") for n in ordre if n.endswith(".xhtml")}
    # marques de relecture imbriquées dans une manchette : on garde leur texte seul
    plat = re.compile(r'(<span class="manchette">)((?:[^<]|<span class="a-verifier"[^>]*>[^<]*</span>)*?)(</span>)(?!</span>)')
    for n in docs:
        docs[n] = plat.sub(lambda m: m.group(1) + re.sub(r"<[^>]+>", "", m.group(2)) + m.group(3), docs[n])
    vers = []                                             # (fichier, n° du paragraphe, n° de ligne, texte)
    paras = {}
    for n, t in docs.items():
        ps = list(re.finditer(r'(<p class="([^"]*)"([^>]*)>)(.*?)(</p>)', t, re.S))
        paras[n] = ps
        for k, m in enumerate(ps):
            if "vers" not in m.group(2).split():
                continue
            for j, l in enumerate(re.split(r"<br\s*/>", m.group(4))):
                txt = html.unescape(re.sub(r"<span class=\"(?:numvers|manchette)\">[^<]*</span>|<[^>]+>", " ", l))
                vers.append((n, k, j, squelette(txt)))

    # 2. chaque folio de la référence → un vers de l'EPUB (dans l'ordre)
    poser = {}
    log = []
    pos = 0
    for texte, folio in refs:
        sq = squelette(texte)
        best, bi = 0, None
        for i in range(pos, min(len(vers), pos + 700)):
            if abs(len(vers[i][3]) - len(sq)) > max(6, len(sq) // 3):
                continue
            r = difflib.SequenceMatcher(None, sq, vers[i][3], autojunk=False).ratio()
            if r > best:
                best, bi = r, i
                if r > 0.95:
                    break
        if bi is not None and best >= 0.75:
            poser[vers[bi][:3]] = folio
            pos = bi + 1
            log.append(("posé", folio, texte))
        else:
            log.append(("non retrouvé", folio, texte))

    # 3. réécriture
    stats = {"posés": len(poser), "fragments ôtés": 0, "ponctuation remise": 0}
    nouveaux = {}
    for n, t in docs.items():
        out, last = [], 0
        for k, m in enumerate(paras[n]):
            if "vers" not in m.group(2).split():
                continue
            lignes = re.split(r"(<br\s*/>)", m.group(4))
            for j in range(0, len(lignes), 2):
                l = lignes[j]
                avant = l
                mans = re.findall(r' ?<span class="manchette">([^<]*)</span>', l)
                garder = []
                for man in mans:
                    v = html.unescape(man).strip()
                    if re.fullmatch(r"[«»;:!?.,\s]+", v):                     # ponctuation rejetée en marge
                        stats["ponctuation remise"] += 1
                        l = l.replace('<span class="manchette">%s</span>' % man, "", 1)
                        l = re.sub(r"(\s*<span class=\"numvers\">)", NB + v + r"\1", l, count=1) \
                            if '<span class="numvers">' in l else l.rstrip() + NB + v
                    elif est_fragment(man) or FOLIO_REF.fullmatch(v):
                        stats["fragments ôtés"] += 1
                        l = l.replace(' <span class="manchette">%s</span>' % man, "", 1) \
                             .replace('<span class="manchette">%s</span>' % man, "", 1)
                    elif re.fullmatch(r"[a-zà-ÿ]+[,;.]?", v) and not DATE.search(v):   # mot du vers rejeté en marge
                        stats["ponctuation remise"] += 1
                        l = l.replace(' <span class="manchette">%s</span>' % man, "", 1) \
                             .replace('<span class="manchette">%s</span>' % man, "", 1)
                        l = re.sub(r"(\s*<span class=\"numvers\">)", " " + v + r"\1", l, count=1) \
                            if '<span class="numvers">' in l else l.rstrip() + " " + v
                        log.append(("mot remis dans le vers", v, html.unescape(re.sub(r"<[^>]+>", "", l))[:60]))
                    else:
                        garder.append(v)
                        if not DATE.search(v):
                            log.append(("manchette gardée", v, html.unescape(re.sub(r"<[^>]+>", "", l))[:60]))
                # fragments dans le texte : fin de vers (avant le numéro) et folio en tête du vers
                li = O.Ligne(l)
                s = li.s
                coeur = re.match(r"^(.*?)([%s\s]*)$" % PRIV, s, re.S)
                corps, fin = coeur.group(1), coeur.group(2)
                c2 = FRAG_TEXTE.sub(lambda m: m.group(0) if re.search("[%s]" % PRIV, m.group(0)) else "", corps)
                c2 = DEBUT_TEXTE.sub("", c2)
                if c2 != corps:
                    stats["fragments ôtés"] += 1
                    li.s = c2.rstrip() + fin
                    l = li.out()
                f = poser.get((n, k, j // 2))
                if f:
                    man = ' <span class="manchette">%s</span>' % f
                    l = re.sub(r"(\s*)$", man + r"\1", l, count=1) if '<span class="numvers">' not in l \
                        else re.sub(r'(<span class="numvers">[^<]*</span>)', r"\1" + man, l, count=1)
                if l != avant:
                    lignes[j] = l
            out.append(t[last:m.start(4)] + "".join(lignes))
            last = m.end(4)
        out.append(t[last:])
        nouveaux[n] = "".join(out)

    zout = zipfile.ZipFile(opts.output, "w")
    for item in zin.infolist():
        data = nouveaux[item.filename].encode("utf-8") if item.filename in nouveaux else zin.read(item.filename)
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    nr = sum(1 for x in log if x[0] == "non retrouvé")
    print("folios de la référence : %d, posés : %d, non retrouvés : %d ; fragments ôtés : %d ; "
          "ponctuation remise dans le vers : %d" % (len(refs), stats["posés"], nr, stats["fragments ôtés"],
                                                    stats["ponctuation remise"]))
    if opts.report:
        with open(opts.report, "w", encoding="utf-8") as f:
            f.write("action\tfolio / manchette\tvers\n")
            for a, b, c in log:
                f.write("%s\t%s\t%s\n" % (a, b, c))


if __name__ == "__main__":
    main()
