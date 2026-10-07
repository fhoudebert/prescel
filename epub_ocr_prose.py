#!/usr/bin/env python3
"""Fautes d'OCR typiques d'ABBYY dans la prose française moderne (introductions, traductions, notes).

Jamais dans les citations en vers (<p class="vers">, ancien français) ; un mot n'est remplacé que si la
forme obtenue est française (liste de mots de Prescel ou mots du livre) et l'originale ne l'est pas :
  l'          « TAngleterre » → « l'Angleterre », « Fun » → « l'un », « Vhistoire » → « l'histoire »
  apostrophe  « j*ai », « qu^il », « s*est » → « j'ai », « qu'il », « s'est »
  Il          « 11 » ou « H » devant un verbe en tête de phrase → « Il »
  ligatures   « Tafifaire » → « l'affaire » ; « fl », « fi » lus « fll », « fii »…

  python3 epub_ocr_prose.py livre.epub -o livre-2.epub [--report r.tsv]
"""
import argparse
import collections
import re
import zipfile

from epub_longs import load_wordlist

ELIDES = {"j", "l", "d", "n", "s", "t", "m", "c", "qu", "jusqu", "lorsqu", "puisqu", "quoiqu", "presqu"}


class Nettoyeur:
    def __init__(self, mots, livre):
        self.mots = mots
        self.livre = livre
        self.log = []

    def fr(self, w):
        w2 = w.lower()
        return w2 in self.mots or self.livre.get(w2, 0) >= 3

    def texte(self, s, ctx):
        def l_apos(m):
            lettre, mot = m.group(1), m.group(2)
            if self.fr(lettre + mot) or not self.fr(mot):
                return m.group(0)
            r = "l'" + mot if lettre != "V" or mot[0].islower() else "l'" + mot
            self.log.append((ctx, "l'", m.group(0), r))
            return r
        s = re.sub(r"(?<![\w'’])([TFV])([aeiouyhéèêâîôûœAEIOUYHÉÈÊÂÎÔÛŒ][a-zà-ÿœ]+)\b", l_apos, s)

        def apos(m):
            a, b = m.group(1), m.group(2)
            if a.lower() not in ELIDES:
                return m.group(0)
            r = a + "'" + b
            self.log.append((ctx, "apostrophe", m.group(0), r))
            return r
        s = re.sub(r"(?<![\w])([A-Za-z]{1,7})[*^]([a-zà-ÿ]{1,})", apos, s)

        def il(m):
            r = m.group(1) + "Il" + m.group(3)
            self.log.append((ctx, "Il", m.group(2), "Il"))
            return r
        s = re.sub(r"((?:^|[.!?»]\s+|\(\s*))(11|H)(\s+(?:y|a|est|était|fut|faut|ne|n'|se|s'|le|la|les|lui|en|avait|"
                   r"eut|fit|dit|vint|alla|mourut|semble|paraît|serait|s'agit))\b", il, s)

        def lig(m):
            w = m.group(0)
            for a, b in (("fif", "ff"), ("flf", "ff"), ("fll", "fl"), ("fii", "fi"), ("ffl", "ff")):
                if a in w:
                    r = w.replace(a, b, 1)
                    if self.fr(r) and not self.fr(w):
                        self.log.append((ctx, "ligature", w, r))
                        return r
            return w
        s = re.sub(r"\b[a-zà-ÿ]*(?:fif|flf|fll|fii|ffl)[a-zà-ÿ]*\b", lig, s)
        return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--wordlist", default="auto")
    ap.add_argument("--report")
    opts = ap.parse_args()
    mots = load_wordlist(opts.wordlist) or set()
    zin = zipfile.ZipFile(opts.epub)
    livre = collections.Counter()
    for n in zin.namelist():
        if n.endswith(".xhtml"):
            for w in re.findall(r"[a-zà-ÿœ]{2,}", re.sub(r"<[^>]+>", " ", zin.read(n).decode("utf-8")).lower()):
                livre[w] += 1
    N = Nettoyeur(mots, livre)
    zout = zipfile.ZipFile(opts.output, "w")
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith(".xhtml"):
            t = data.decode("utf-8")

            def para(m):
                if re.search(r'class="[^"]*\bvers\b', m.group(1)):
                    return m.group(0)
                # le texte seulement, pas les balises
                parts = re.split(r"(<[^>]+>)", m.group(2))
                ctx = re.sub(r"<[^>]+>", "", m.group(2))[:60]
                for k in range(0, len(parts), 2):
                    parts[k] = N.texte(parts[k], ctx)
                return m.group(1) + "".join(parts) + m.group(3)
            t = re.sub(r"(<(?:p|h1|h2|h3)\b[^>]*>)(.*?)(</(?:p|h1|h2|h3)>)", para, t, flags=re.S)
            data = t.encode("utf-8")
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    c = collections.Counter(r for _, r, _, _ in N.log)
    print("%d corrections : %s" % (len(N.log), ", ".join("%s %d" % kv for kv in c.most_common())))
    if opts.report:
        with open(opts.report, "w", encoding="utf-8") as f:
            f.write("règle\tavant\taprès\tcontexte\n")
            for ctx, r, a, b in N.log:
                f.write("%s\t%s\t%s\t%s\n" % (r, a, b, ctx))


if __name__ == "__main__":
    main()
