#!/usr/bin/env python3
"""Fusion de deux EPUB du même livre tirés de deux numérisations (abbyy_to_epub.py : XML ABBYY d'Internet
Archive, couche texte d'un DjVu…), qui partagent les ancres de page imprimée (« page-12 ») et la
numérotation des notes (« note-12-3 »). La base garde son texte ; on y reporte de la seconde, page par
page :
  italique  les passages en italique de la seconde (la couche texte d'un DjVu n'a pas de styles),
            retrouvés mot pour mot sur la même page ;
  appels    l'appel d'une note restée sans appel dans la base, placé après les deux mots qui le précèdent
            dans la seconde (retrouvés sur la même page de la base).

  python3 epub_fusion.py base.epub seconde.epub -o fusion.epub [--report r.tsv]
"""
import argparse
import collections
import html
import re
import unicodedata
import zipfile

ANCRE = re.compile(r'<a id="page-([^"]+)"\s*(?:/>|></a>)')


def squelette(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)))


def plain(h):
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def pages_de(textes):
    """{page: html de la page} : le texte entre une ancre de page et la suivante, dans l'ordre."""
    out = collections.defaultdict(str)
    for t in textes:
        cur = None
        pos = 0
        for m in ANCRE.finditer(t):
            if cur is not None:
                out[cur] += t[pos:m.start()]
            cur, pos = m.group(1), m.end()
        if cur is not None:
            out[cur] += t[pos:]
    return out


def lire(path):
    z = zipfile.ZipFile(path)
    opf = next(n for n in z.namelist() if n.endswith(".opf"))
    o = z.read(opf).decode("utf-8")
    base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
    hrefs = dict(re.findall(r'<item\b[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', o))
    ordre = [base + hrefs[i] for i in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', o) if i in hrefs]
    return z, ordre


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("seconde")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--report")
    opts = ap.parse_args()
    z2, ordre2 = lire(opts.seconde)
    p2 = pages_de([z2.read(n).decode("utf-8") for n in ordre2])
    notes2 = {}                                       # (page, k) → 2 mots avant l'appel dans la seconde
    for page, h in p2.items():
        for m in re.finditer(r'<sup><a href="#note-([^"]+)-(\d+)"', h):
            avant = plain(h[:m.start()]).split()[-2:]
            if len(avant) == 2:
                notes2[(m.group(1), int(m.group(2)))] = avant
    ital2 = collections.defaultdict(list)
    for page, h in p2.items():
        for m in re.finditer(r"<i>(.*?)</i>", h, re.S):
            t = plain(m.group(1)).strip(" ,;:.()")
            if len(re.sub(r"\W", "", t)) >= 3:
                ital2[page].append(t)

    z1, ordre1 = lire(opts.base)
    log = []
    stats = collections.Counter()
    nouveaux = {}
    for n in ordre1:
        if not n.endswith(".xhtml"):
            continue
        t = z1.read(n).decode("utf-8")
        morceaux = ANCRE.split(t)          # [avant, page, html, page, html, …]
        for k in range(1, len(morceaux), 2):
            page, h = morceaux[k], morceaux[k + 1]
            # 1. italique
            for it in ital2.get(page, []):
                mots = [re.escape(html.escape(w, quote=False)) for w in it.split()]
                motif = r"(?<![\w>])(" + r"\s+".join(mots) + r")(?![\w<])"
                m = re.search(motif, h)
                if m and "<" not in m.group(1) and not re.search(r"<i>[^<]*$", h[:m.start()]):
                    h = h[:m.start()] + "<i>" + m.group(1) + "</i>" + h[m.end():]
                    stats["italique"] += 1
            morceaux[k + 1] = h
        out = morceaux[0]
        for k in range(1, len(morceaux), 2):
            out += '<a id="page-%s"></a>' % morceaux[k] + morceaux[k + 1]
        # 2. appels des notes restées sans appel (les notes sont regroupées plus loin que leur page)
        for m in list(re.finditer(r'<p class="note" id="note-([^"]+)-(\d+)">\d+\. <span class="a-verifier" '
                                  r'title="Note sans appel', out)):
            page, kk = m.group(1), int(m.group(2))
            avant = notes2.get((page, kk))
            if not avant:
                stats["sans appel dans la seconde"] += 1
                continue
            a0 = out.find('<a id="page-%s"></a>' % page)
            if a0 < 0:
                continue
            a1 = ANCRE.search(out, a0 + 10)
            fin = min(x for x in (a1.start() if a1 else len(out), out.find('<p class="note"', a0)) if x >= 0)
            corps = out[a0:fin]
            sq = [squelette(w) for w in avant]
            trouve = None
            for mm in re.finditer(r"([^\s<>]+)(\s+)([^\s<>]+?)([.,;:!?»)\]]*)(?=[\s<])", corps):
                if squelette(mm.group(1)) == sq[0] and squelette(mm.group(3) + mm.group(4)) == sq[1] \
                        and not corps[mm.end(3):mm.end(3) + 6].startswith("<sup>"):
                    trouve = mm
                    break
            if not trouve:                                  # repli : le dernier mot seul, s'il est unique sur la page
                cands = [mm for mm in re.finditer(r"([^\s<>]+?)([.,;:!?»)\]*]*)(?=[\s<])", corps)
                         if squelette(mm.group(1)) and squelette(mm.group(1)) == sq[1]
                         and not corps[mm.end(1):mm.end(1) + 6].startswith("<sup>")]
                if len(cands) == 1:
                    class T:                                # même interface que le match à deux mots
                        def __init__(self, m):
                            self.m = m

                        def end(self, g):
                            return self.m.end(1)
                    trouve = T(cands[0])
            if not trouve:
                stats["appels non retrouvés"] += 1
                log.append(("non retrouvé", page, kk, " ".join(avant)))
                continue
            pos = a0 + trouve.end(3)
            appel = '<sup><a href="#note-%s-%d" id="appel-%s-%d">%d</a></sup>' % (page, kk, page, kk, kk)
            out = out[:pos] + appel + out[pos:]
            out = re.sub(r'(<p class="note" id="note-%s-%d">)%d\. <span class="a-verifier" title="Note sans appel[^"]*">'
                         r'(?:&#160;|\u00a0| )</span>' % (re.escape(page), kk, kk),
                         lambda x: x.group(1) + '<a href="#appel-%s-%d">%d</a>. ' % (page, kk, kk), out)
            stats["appels repris"] += 1
            log.append(("appel", page, kk, " ".join(avant)))
        nouveaux[n] = out
    zout = zipfile.ZipFile(opts.output, "w")
    for item in z1.infolist():
        data = nouveaux[item.filename].encode("utf-8") if item.filename in nouveaux else z1.read(item.filename)
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    print(", ".join("%s : %d" % kv for kv in sorted(stats.items())))
    if opts.report:
        with open(opts.report, "w", encoding="utf-8") as f:
            f.write("action\tpage\tnote\tmots avant l'appel\n")
            for a, b, c, d in log:
                f.write("%s\t%s\t%s\t%s\n" % (a, b, c, d))


if __name__ == "__main__":
    main()
