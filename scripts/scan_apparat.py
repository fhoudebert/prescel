#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_apparat.py — Lecture d'une numérisation (PDF d'images) d'une édition à apparat (Kervyn de
Lettenhove) : pour chaque page imprimée, les mots du corps, les appels de variantes en exposant
(après quel mot) et l'apparat du bas de page (entrées et étiquettes « 1·2 », « 3 »).

Les appels sont trop petits pour Tesseract : ils sont repérés sur l'image. Pour chaque ligne lue
par Tesseract, la ligne de base et la hauteur d'x sont estimées sur les lettres ; un signe « en
l'air » (bas au-dessus de la ligne de base), assez haut, sans lettre dessous (point d'i, accent),
hors d'un mot et qui ne suit pas un nombre romain (XII^c, IIII^xx, VI^e : exposants, pas appels)
est un appel. Le numéro n'est pas lu : sur une page, les appels vont de 1 à N dans l'ordre.

Le résultat (JSON) sert à epub_apparat_scan.py, qui place les appels dans l'EPUB et refait les
blocs d'apparat. Les planches (--planches-apparat, --planche-appels) aident à relire l'apparat et
à contrôler les appels page par page sur l'image.

Usage :
  python3 scripts/scan_apparat.py numerisation.pdf --decalage 7 --de 1 --a 319 \\
          --cache travail-scan -o scan.json                    # Tesseract (fra) sur chaque page
  python3 scripts/scan_apparat.py numerisation.pdf --decalage 7 --cache travail-scan \\
          --planches-apparat 1 30 -o apparat-1-30.png          # bas de page, pour relire l'apparat
  python3 scripts/scan_apparat.py numerisation.pdf --decalage 7 --cache travail-scan \\
          --planche-appels 102 -o p102.png                     # appels repérés sur une page

Dépendances : tesseract (langue fra, --tessdata pour un dossier de modèles), pymupdf, opencv-python,
numpy.
"""
import argparse
import collections
import json
import os
import re
import statistics
import subprocess
import sys

LETTERS = re.compile(r"[^\W\d_]+", re.U)
WORDCH = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.U)


class Scan:
    def __init__(self, pdf, offset, cache, tessdata=None, dpi=470, lang="fra"):
        self.pdf, self.offset, self.cache, self.dpi, self.lang = pdf, offset, cache, dpi, lang
        self.env = dict(os.environ)
        if tessdata:
            self.env["TESSDATA_PREFIX"] = tessdata
        os.makedirs(cache, exist_ok=True)
        self._doc = None
        self._img = {}

    # -- pages -----------------------------------------------------------------------------
    def png(self, p):
        f = os.path.join(self.cache, "p%d.png" % p)
        if not os.path.exists(f):
            import pymupdf
            if self._doc is None:
                self._doc = pymupdf.open(self.pdf)
            self._doc[p + self.offset].get_pixmap(dpi=self.dpi).save(f)
        return f

    def tsv(self, p):
        png = self.png(p)
        base = png[:-4]
        if not os.path.exists(base + ".tsv"):
            subprocess.run(["tesseract", png, base, "-l", self.lang, "--psm", "4", "tsv"],
                           capture_output=True, env=self.env)
        return base + ".tsv"

    def lines_of(self, p):
        rows = [l.split("\t") for l in open(self.tsv(p), encoding="utf-8").read().splitlines()[1:]]
        lines = collections.OrderedDict()
        for f in rows:
            if len(f) == 12 and f[0] == "5" and f[11].strip():
                k = (int(f[2]), int(f[3]), int(f[4]))
                l, t, w, h = map(int, f[6:10])
                lines.setdefault(k, []).append({"l": l, "t": t, "r": l + w, "b": t + h, "text": f[11]})
        return list(lines.values())

    def image(self, p):
        import cv2
        if p not in self._img:
            self._img.clear()
            self._img[p] = cv2.imread(self.png(p), 0)
        return self._img[p]

    # -- exposants d'une ligne -------------------------------------------------------------
    def line_supers(self, p, words):
        import cv2
        import numpy as np
        im = self.image(p)
        L = max(0, min(w["l"] for w in words) - 30)
        T = max(0, min(w["t"] for w in words) - 25)
        R = max(w["r"] for w in words) + 30
        B = max(w["b"] for w in words) + 8
        tops = sorted(w["t"] for w in words)
        wtop = tops[len(tops) // 5]                   # haut des capitales et hampes
        sub = (im[T:B, L:R] < 140).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
        comps = [dict(x=int(s[0]), y=int(s[1]), w=int(s[2]), h=int(s[3]), a=int(s[4]), i=i)
                 for i, s in enumerate(st) if i and s[4] >= 6]
        if len([c for c in comps if c["h"] > 12]) < 5:
            return None
        wh = [w["b"] - w["t"] for w in words if any(ch.isalpha() for ch in w["text"])]
        xh = round(0.68 * statistics.median(wh)) if wh else 34
        # ligne de base : mode des bas des lettres (x et hampes y reposent, les jambages sont rares)
        cand = [c for c in comps if 0.6 * xh <= c["h"] <= 1.6 * xh]
        if len(cand) < 3:
            return None
        b0 = collections.Counter((c["y"] + c["h"]) // 4 for c in cand).most_common(1)[0][0]
        on = [c for c in cand if abs((c["y"] + c["h"]) // 4 - b0) <= 1]
        base = statistics.median(c["y"] + c["h"] for c in on)
        hx = collections.Counter(c["h"] // 3 for c in on if c["h"] <= 1.25 * xh)
        if hx:
            xh2 = hx.most_common(1)[0][0] * 3 + 1
            if 0.7 * xh <= xh2 <= 1.3 * xh:
                xh = xh2
        raised = []
        for c in comps:
            bottom = c["y"] + c["h"]
            if bottom > base - 0.35 * xh or c["a"] < 4:
                continue
            if c["y"] <= 1 or c["y"] < (wtop - T) - 0.35 * xh:
                continue                              # jambage de la ligne du dessus
            if any(d is not c and d["y"] >= bottom - 3 and d["y"] < base and
                   min(c["x"] + c["w"], d["x"] + d["w"]) - max(c["x"], d["x"]) > 0.3 * c["w"] for d in comps):
                continue                              # point d'i, accent : lettre dessous
            raised.append(c)
        raised.sort(key=lambda c: c["x"])
        glyphs = []                                   # morceaux d'un chiffre cassé : réunis
        for c in raised:
            g = glyphs[-1] if glyphs else None
            ov = (min(g["x"] + g["w"], c["x"] + c["w"]) - max(g["x"], c["x"])) if g else 0
            if g and ov > 0.5 * min(g["w"], c["w"]):
                x0, y0 = min(g["x"], c["x"]), min(g["y"], c["y"])
                x1, y1 = max(g["x"] + g["w"], c["x"] + c["w"]), max(g["y"] + g["h"], c["y"] + c["h"])
                g.update(x=x0, y=y0, w=x1 - x0, h=y1 - y0)
            else:
                glyphs.append(dict(c))
        out = []
        for g in glyphs:
            kind = "dig" if g["h"] >= 0.62 * xh else ("sep" if g["h"] < 0.4 * xh and g["w"] < 0.6 * xh else "small")
            out.append(dict(kind=kind, X=L + g["x"], Y=T + g["y"], w=g["w"], h=g["h"], xh=xh))
        return dict(xh=xh, base=T + base, supers=out, words=words)

    # -- modèle de page --------------------------------------------------------------------
    def page_model(self, p):
        L = []
        for ws in self.lines_of(p):
            r = self.line_supers(p, ws) or dict(words=ws, xh=None, supers=[])
            r["top"] = min(w["t"] for w in ws)
            L.append(r)
        L.sort(key=lambda r: r["top"])
        if not [r for r in L if r["xh"]]:
            return None
        if L:                                         # titre courant
            txt0 = " ".join(w["text"] for w in L[0]["words"])
            letters = [c for c in txt0 if c.isalpha()]
            if len(L[0]["words"]) <= 10 and (re.search(r"\d", txt0) or
                                              (letters and sum(c.isupper() for c in letters) > 0.8 * len(letters))):
                L[0]["kind"] = "header"
        for r in L:
            r.setdefault("kind", "body")
            wh = [w["b"] - w["t"] for w in r["words"] if any(ch.isalpha() for ch in w["text"])]
            r["wh"] = statistics.median(wh) if wh else 0
        body_wh = statistics.median([r["wh"] for r in L if r["wh"]] or [52])
        for r in L:
            if r["kind"] != "header" and (not r["wh"] or r["wh"] < 0.7 * body_wh):
                r["kind"] = "junk"                    # signature d'imprimeur, taches
        # apparat : après le dernier blanc franc du bas de page ; à défaut, lignes en petit corps
        tops = [(i, r["top"]) for i, r in enumerate(L) if r["kind"] != "junk"]
        H = max((max(w["b"] for w in L[i]["words"]) for i, _ in tops), default=0)
        sp = sorted(t2 - t for (i, t), (j, t2) in zip(tops, tops[1:]))
        msp = sp[len(sp) // 2] if sp else 90
        gaps = [j for (i, t), (j, t2) in zip(tops, tops[1:]) if t2 - t > 1.22 * msp and t2 > 0.55 * H]
        if gaps and (L[gaps[-1]]["wh"] < 0.93 * body_wh or sum(1 for r in L[gaps[-1]:] if r["kind"] != "junk") <= 6):
            for k in range(gaps[-1], len(L)):
                if L[k]["kind"] == "body":
                    L[k]["kind"] = "foot"
        else:
            k = len(L) - 1
            while k > 0 and (L[k]["kind"] == "junk" or (L[k]["kind"] == "body" and L[k]["wh"] < 0.9 * body_wh)):
                if L[k]["kind"] == "body":
                    L[k]["kind"] = "foot"
                k -= 1
        return dict(p=p, lines=L, body_wh=body_wh)

    def calls(self, model):
        out = []
        for li, r in enumerate(model["lines"]):
            if r["kind"] != "body":
                continue
            digs = [c for c in r["supers"] if c["kind"] == "dig" and c["w"] <= 0.95 * c["h"] and c["h"] <= 1.05 * r["xh"]]
            merged = []                               # « 10 », « 12 » : un seul appel
            for c in digs:
                if merged and c["X"] - (merged[-1]["X"] + merged[-1]["w"]) < 0.3 * r["xh"]:
                    merged[-1]["w"] = c["X"] + c["w"] - merged[-1]["X"]
                else:
                    merged.append(dict(X=c["X"], w=c["w"], h=c["h"], Y=c["Y"]))
            ws = sorted(r["words"], key=lambda w: w["l"])
            xh = r["xh"]
            for m in merged:
                cx = m["X"] + m["w"] / 2
                host = [w for w in ws if w["l"] <= cx <= w["r"]]
                if host and m["X"] > host[0]["l"] + 0.3 * xh and m["X"] + m["w"] < host[0]["r"] - 0.8 * xh:
                    continue                          # au milieu d'un mot (empattement d'un N…)
                left = [w for w in ws if w["r"] <= m["X"] + 0.4 * xh and w["l"] < m["X"]]
                near = host[0] if host and host[0]["l"] < m["X"] - 0.3 * xh else \
                    (left[-1] if left and m["X"] - left[-1]["r"] < 0.35 * xh else None)
                if near and re.fullmatch(r"[IVXLCM]+[cemxo]{0,2}", re.sub(r"[^\w]", "", near["text"])):
                    continue                          # exposant d'un nombre romain
                out.append(dict(li=li, **m))
        return out

    def foot_entries(self, model):
        seq = []
        for li, r in enumerate(model["lines"]):
            if r["kind"] != "foot":
                continue
            items = [("g", c["X"], c) for c in r["supers"] if c["kind"] in ("dig", "sep")]
            items += [("w", w["l"], w) for w in r["words"]]
            seq += [(k, li, o) for k, x, o in sorted(items, key=lambda t: t[1])]
        entries, cur, pending = [], None, []
        for kind, li, obj in seq:
            if kind == "g":
                pending.append(obj)
                continue
            w = obj["text"]
            if not WORDCH.search(w):
                if re.fullmatch(r"[—–-]{1,2}", w) and not pending and cur:
                    cur["dash"] = True
                continue
            if pending:
                digs = [g for g in pending if g["kind"] == "dig"]
                if digs:
                    groups, g0 = [], [digs[0]]
                    for a, b in zip(digs, digs[1:]):
                        if any(s["kind"] == "sep" and a["X"] < s["X"] < b["X"] for s in pending) or \
                                b["X"] - (a["X"] + a["w"]) > 0.35 * a["xh"]:
                            groups.append(g0)
                            g0 = [b]
                        else:
                            g0.append(b)
                    groups.append(g0)
                    cur = dict(label=[len(g) for g in groups], words=[], dash=False)
                    entries.append(cur)
                pending = []
            if cur is None:
                cur = dict(label=None, words=[], dash=False)
                entries.append(cur)
            cur["words"].append(w)
        return entries

    def page_data(self, p):
        m = self.page_model(p)
        if not m:
            return None
        body, foot, line_words = [], [], {}
        for li, r in enumerate(m["lines"]):
            if r["kind"] not in ("body", "foot"):
                continue
            dst = body if r["kind"] == "body" else foot
            for w in sorted(r["words"], key=lambda w: w["l"]):
                for t in LETTERS.findall(w["text"]):
                    line_words.setdefault(li, []).append((len(dst), w["l"]))
                    dst.append(dict(t=t, li=li, raw=w["text"]))
        calls = []
        for c in self.calls(m):
            li = c["li"]
            cands = [i for i, l in line_words.get(li, []) if l < c["X"] and body[i]["li"] == li]
            if cands:
                after = cands[-1]
            else:
                prev = [i for k, v in line_words.items() if k < li for i, _ in v if i < len(body) and body[i]["li"] == k]
                after = max(prev) if prev else -1
            calls.append(dict(after=after, li=li, X=c["X"], Y=c["Y"], w=c["w"], h=c["h"], linestart=not cands))
        return dict(p=p, body=body, foot=foot, calls=calls,
                    entries=[dict(label=e["label"], words=e["words"], dash=e["dash"]) for e in self.foot_entries(m)])

    # -- planches --------------------------------------------------------------------------
    def sheet_apparat(self, pages, out):
        import cv2
        import numpy as np
        rows = []
        for p in pages:
            m = self.page_model(p)
            if not m:
                continue
            im = self.image(p)
            fl = [r for r in m["lines"] if r["kind"] == "foot"]
            if fl:
                t = min(min(w["t"] for w in r["words"]) for r in fl) - 25
                b = max(max(w["b"] for w in r["words"]) for r in fl) + 8
                l = min(min(w["l"] for w in r["words"]) for r in fl) - 60
                rr = max(max(w["r"] for w in r["words"]) for r in fl) + 20
                crop = im[t:b, max(0, l):rr]
                mark = str(p)
            else:                                     # pas d'apparat repéré : bas de page entier
                bl = [r for r in m["lines"] if r["kind"] == "body"]
                if not bl:
                    continue
                t = max(max(w["b"] for w in r["words"]) for r in bl[-2:]) - 60
                crop = im[t:min(im.shape[0], t + 420), 500:2700]
                mark = "%d*" % p
            crop = cv2.resize(crop, (crop.shape[1] * 2 // 5, crop.shape[0] * 2 // 5), interpolation=cv2.INTER_AREA)
            lab = np.full((crop.shape[0], 70), 255, np.uint8)
            cv2.putText(lab, mark, (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
            rows.append(np.hstack([lab, crop]))
        w = max(r.shape[1] for r in rows)
        cv2.imwrite(out, np.vstack([cv2.copyMakeBorder(r, 3, 3, 0, w - r.shape[1], cv2.BORDER_CONSTANT, value=255)
                                    for r in rows]))

    def sheet_calls(self, p, out):
        import cv2
        d = self.page_data(p)
        im = cv2.cvtColor(self.image(p), cv2.COLOR_GRAY2BGR)
        for k, c in enumerate(d["calls"], 1):
            cv2.rectangle(im, (c["X"] - 6, c["Y"] - 6), (c["X"] + c["w"] + 6, c["Y"] + c["h"] + 6), (0, 0, 255), 4)
            cv2.putText(im, str(k), (c["X"] - 10, c["Y"] - 12), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)
        h = im.shape[0]
        crop = im[450:h - 250, 550:2800]
        cv2.imwrite(out, cv2.resize(crop, (crop.shape[1] * 2 // 5, crop.shape[0] * 2 // 5), interpolation=cv2.INTER_AREA))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--decalage", type=int, default=0, help="page du PDF = page imprimée + décalage")
    ap.add_argument("--de", type=int, default=1)
    ap.add_argument("--a", type=int, default=None)
    ap.add_argument("--cache", required=True, help="dossier des images et des lectures Tesseract")
    ap.add_argument("--tessdata", help="dossier des modèles Tesseract (fra.traineddata)")
    ap.add_argument("--planches-apparat", nargs=2, type=int, metavar=("DE", "A"))
    ap.add_argument("--planche-appels", type=int, metavar="PAGE")
    ap.add_argument("-o", "--output", required=True)
    o = ap.parse_args()
    s = Scan(o.pdf, o.decalage, o.cache, o.tessdata)
    if o.planches_apparat:
        s.sheet_apparat(range(o.planches_apparat[0], o.planches_apparat[1] + 1), o.output)
        return
    if o.planche_appels is not None:
        s.sheet_calls(o.planche_appels, o.output)
        return
    import pymupdf
    last = o.a if o.a is not None else pymupdf.open(o.pdf).page_count - 1 - o.decalage
    data = json.load(open(o.output)) if os.path.exists(o.output) else {}
    for p in range(o.de, last + 1):
        d = s.page_data(p)
        if d:
            data[str(p)] = d
        print("\rpage %d" % p, end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump(data, open(o.output, "w"), ensure_ascii=False)
    print("%s : %d pages, %d appels repérés" % (o.output, len(data), sum(len(d["calls"]) for d in data.values())))


if __name__ == "__main__":
    main()
