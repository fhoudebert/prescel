#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_romains.py — Nombres en chiffres romains du récit donnés en chiffres arabes, pour une édition de
lecture (moyen français : Froissart).

Les éditions anciennes écrivent les nombres en chiffres romains, avec des exposants multiplicateurs :
IIII<sup>xx</sup> = 4 × 20 = 80, VI<sup>xx</sup> = 120, V<sup>c</sup> = 500, VII<sup>m</sup> = 7 000 ;
et les ordinaux XIX<sup>e</sup> = 19ᵉ. Le script lit les groupes et leurs liaisons :

  mil CCC. IIII<sup>xx</sup> et VIII   → 1388        (date : pas d'espace des milliers)
  IIII<sup>xx</sup> et XII ans         → 92 ans
  XXII<sup>c</sup> frans               → 2 200 frans
  VII<sup>m</sup> lances               → 7 000 lances
  le XIX<sup>e</sup> jour              → le 19<sup>e</sup> jour
  XII lances, CCCC lances              → 12 lances, 400 lances

Laissés en chiffres romains : un nombre derrière un nom propre ou un titre (Charles VI, Richard II,
le pape Urbain VI, tome XIII, chapitre II), une lettre seule sans exposant (« I », « V », « C » :
souvent une initiale ou une lettre mal lue), les titres, l'apparat (<p class="variantes">), les
appels de variante et tout ce qui suit l'élément --jusqua (notes de l'éditeur).

Usage :
  python3 scripts/epub_romains.py entree.epub -o sortie.epub [--jusqua titre-4] [--tsv romains.tsv]
"""
import argparse
import re
import zipfile

VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
MULT = {"xx": 20, "c": 100, "m": 1000}
ORD = ("e", "me", "es", "er", "re", "ème")
R = r"[IVXLCDM]+"
P = r"(?:\x00\d+\x00)*"           # balise mise à l'abri (appel de variante, ancre de page, marque)
# liaison entre deux groupes d'un même nombre : « CCC. IIII », « IIII^xx et VIII », « mil CCC »
JOIN = r"(?:%s\.?%s\s+%s(?:et\s+%s)?)" % (P, P, P, P)
COMPOUND = re.compile(r"(?<![\w&;])(?:(mil|M\.)\s+%s(et\s+)?)?(%s(?:<sup>(?:xx|c|m)</sup>)?(?:%s%s(?:<sup>(?:xx|c|m)</sup>)?)*)"
                      r"(?:<sup>(e|me|es|er|re|ème)</sup>)?(?![\w'’<])" % (P, R, JOIN, R))
# devant le nombre : titre ou nom propre (Charles VI) ; dans le corps d'une phrase seulement
TITRES = {"roi", "roy", "pape", "duc", "conte", "comte", "tome", "chapitre", "livre", "chap", "t", "p",
          "pp", "art", "page", "pages", "partie"}
# nombres en lettres qui achèvent un nombre en chiffres (« mil CCC. IIII^xx et dix », « mil CCC
# quatre-vings et huit »)
MOTS = {"un": 1, "ung": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
        "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
        "quinze": 15, "seize": 16, "vingt": 20, "vint": 20, "vingts": 20, "trente": 30, "quarante": 40,
        "cinquante": 50, "soixante": 60}
MOT = r"(?:quatre[- ]?vin(?:g?t?s?)|%s)" % "|".join(sorted(MOTS, key=len, reverse=True))
TAIL = re.compile(r"(\s+(?:et\s+)?)(%s(?:(?:[- ]|\s+et\s+)%s)*)(?![\w'’])" % (MOT, MOT))


def words_value(s):
    n = 0
    for w in re.findall(MOT, s):
        n += 80 if w.startswith("quatre") and "vin" in w else MOTS[w]
    return n


def roman(s):
    """valeur d'un nombre romain (formes anciennes : IIII, VIIII) ; None s'il n'est pas bien formé."""
    if not re.fullmatch(r"M{0,4}(?:CM|CD|D?C{0,4})(?:XC|XL|L?X{0,4})(?:IX|IV|V?I{0,5})", s) or not s:
        return None
    n = 0
    for a, b in zip(s, s[1:] + " "):
        v = VAL[a]
        n += -v if b != " " and VAL.get(b, 0) > v else v
    return n


def groups_value(core):
    """« CCC. IIII<sup>xx</sup> et VIII » → (388, nombre de groupes, plus petit groupe) ; None si la
    suite n'est pas décroissante (« XII et XIII » : deux nombres)."""
    total, last, k = 0, None, 0
    for m in re.finditer(r"(%s)(?:<sup>(xx|c|m)</sup>)?" % R, core):
        v = roman(m.group(1))
        if v is None:
            return None
        v *= MULT.get(m.group(2) or "", 1)
        if last is not None and v >= last:
            return None
        total += v
        last, k = v, k + 1
    return total, k, last


def fmt(n, date):
    s = str(n)
    if date or n < 1000:
        return s
    out = ""
    while len(s) > 3:
        out, s = " " + s[-3:] + out, s[:-3]
    return s + out


def convert_text(t, keep, log, where):
    """t : texte d'un paragraphe dont les balises (sauf exposants des nombres) sont des repères
    \x00k\x00 renvoyant à keep."""
    def plain(s):
        return re.sub(r"<[^>]+>", "", re.sub(r"\x00(\d+)\x00", lambda x: re.sub(r"<[^>]+>", "", keep[int(x.group(1))]), s))

    out, pos = [], 0
    for m in COMPOUND.finditer(t):
        if m.start() < pos:
            continue
        mil, mil_et, core, ordinal = m.group(1), m.group(2), m.group(3), m.group(4)
        marks = "".join(re.findall(r"\x00\d+\x00", m.group(0)))
        core = re.sub(r"\x00\d+\x00", "", core)
        plain_before = plain(t[max(0, m.start() - 60):m.start()])
        prev = re.search(r"([\w'’.]+)\s*$", plain_before)
        pw = prev.group(1) if prev else ""
        r = groups_value(core)
        if r is None:
            continue
        n, k, smallest = r
        end = m.end()
        tail = TAIL.match(t, end) if not ordinal else None
        if tail:
            w = words_value(tail.group(2))
            if w >= smallest:
                continue                                       # « XII et treize » : deux nombres
            n += w
            end = tail.end()
        elif re.match(r"\s+(?:et\s+)?(?:quatre|vin|trente|quarante|cinquante|soixante)", t[end:]):
            continue
        after = plain(t[end:end + 30])
        if mil:
            n += 1000
        simple = k == 1 and not mil and "<sup>" not in core
        if simple and not ordinal and len(core) == 1:
            continue                                           # lettre seule
        if not mil and pw.rstrip(".").lower() in TITRES:
            continue                                           # tome XIII, le pape Urbain VI
        if not mil and pw[:1].isupper() and "<sup>" not in core:      # (XXII<sup>c</sup> : jamais un rang)
            if re.search(r"[^\s.!?:«»—–-]", plain_before.rstrip()[:-len(pw)][-3:] or "."):
                continue                                       # Charles VI, Richard II
        if re.match(r"\s*[A-ZÀ-Ý]{2,}", after) and not ordinal:
            continue                                           # titre en capitales
        if ordinal:
            e = "er" if n == 1 and ordinal in ("er", "re") else ("re" if n == 1 else "e")
            new = "%d<sup>%s</sup>" % (n, e)
        else:
            new = fmt(n, bool(mil) and not mil_et)          # « mil et V^c frans » : 1 500, pas une date
        log.append((where, plain(t[m.start():end]).replace("\n", " "), re.sub(r"<[^>]+>", "", new),
                    (plain_before[-30:] + " [] " + after[:20]).replace("\n", " ")))
        out.append(t[pos:m.start()] + new + marks)
        pos = end
    out.append(t[pos:])
    return "".join(out)


def convert_doc(t, name, log, stop_id, stopped):
    """paragraphes du corps (hors titres, apparat, après stop_id) ; renvoie (texte, arrêté ?)."""
    if stopped:
        return t, True
    end = len(t)
    if stop_id:
        i = t.find('id="%s"' % stop_id)
        if i >= 0:
            end = t.rfind("<", 0, i)
            stopped = True
    head, body, tail = t[:t.find("<body")], t[t.find("<body"):end], t[end:]

    def para(m):
        if 'class="variantes' in m.group(1):
            return m.group(0)
        keep = []

        def shelter(x):
            keep.append(x.group(0))
            return "\x00%d\x00" % (len(keep) - 1)
        # appels de variante et balises mis à l'abri ; restent les exposants des nombres (<sup>xx</sup>)
        inner = re.sub(r'<sup class="[^"]*">.*?</sup>', shelter, m.group(2))
        inner = re.sub(r"<(?!/?sup>)[^>]+>", shelter, inner)
        inner = convert_text(inner, keep, log, name)
        while "\x00" in inner:
            inner = re.sub(r"\x00(\d+)\x00", lambda x: keep[int(x.group(1))], inner)
        return m.group(1) + inner + "</p>"
    body = re.sub(r"(<p(?:\s[^>]*)?>)(.*?)</p>", para, body, flags=re.S)
    return head + body + tail, stopped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--jusqua", metavar="ID", help="ne rien changer à partir de cet élément (ex. titre-4)")
    ap.add_argument("--tsv", help="liste des conversions")
    a = ap.parse_args()
    zin = zipfile.ZipFile(a.epub)
    opf_name = next(n for n in zin.namelist() if n.endswith(".opf"))
    opf = zin.read(opf_name).decode("utf-8")
    base = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
    items = dict(re.findall(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf))
    items.update({i: h for h, i in re.findall(r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', opf)})
    spine = [base + items[i] for i in re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf) if i in items]
    out, log, stopped = {}, [], False
    for name in spine:
        t = zin.read(name).decode("utf-8")
        nt, stopped = convert_doc(t, name, log, a.jusqua, stopped)
        if nt != t:
            out[name] = nt
    with zipfile.ZipFile(a.output, "w") as zo:
        for info in sorted(zin.infolist(), key=lambda i: i.filename != "mimetype"):
            d = out[info.filename].encode("utf-8") if info.filename in out else zin.read(info)
            zo.writestr(info, d, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    if a.tsv:
        with open(a.tsv, "w", encoding="utf-8") as f:
            f.write("fichier\tavant\taprès\tcontexte\n")
            for r in log:
                f.write("\t".join(r) + "\n")
    print("%d nombres convertis" % len(log))


if __name__ == "__main__":
    main()
