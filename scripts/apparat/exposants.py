"""Exposants des nombres romains : IIII<sup>xx</sup> (80), V<sup>c</sup> (500), IIII<sup>m</sup> (4000),
XIX<sup>e</sup> (ordinal) ; dates « mil CCC. IIII… et VIII » (1380-1399)."""
import re
from . import conf, texte as master, lecture as truth

MARK = '<span class="a-verifier" title="%s">%s</span>'
R = r"[IVXLC]+"
NOT_NUM = {"Le", "Ce", "De", "Me", "Ie", "Les", "Ces", "Des", "Mes", "Ic", "Lc", "Dc", "Cc", "Im", "Lm", "Dm", "Ier"}



def sup(num, e):
    return "%s<sup>%s</sup>" % (num, e.lower())


def text_nodes(t, fn):
    """applique fn aux nœuds texte du corps (hors balises, hors exposants existants)."""
    i = t.find("<body")
    parts = re.split(r"(<[^>]+>)", t[i:])
    out, insup = [], 0
    for p in parts:
        if p.startswith("<"):
            if p.startswith("<sup"):
                insup += 1
            elif p.startswith("</sup"):
                insup = max(0, insup - 1)
            out.append(p)
        else:
            out.append(p if insup else fn(p))
    return t[:i] + "".join(out)


def glued(s, log):
    """XIXe, XVIIIE, XXVIIIme, Ier → exposant ; Vc, VC, XVIIIc ; IIIIm ; IIIIxx, IIIIXX."""
    def rep(m):
        num, e = m.group(1), m.group(2)
        w = m.group(0)
        if w in NOT_NUM or (len(num) == 1 and num in "LCDM" and e.lower() in ("e", "es")):
            return w
        if num == "I" and e.lower() not in ("er", "re"):
            return w
        if e in ("er", "re") and num != "I":
            return w
        if e == "XX" and not num.endswith("I"):
            return w                       # « XXX », « LXX » : nombres ordinaires
        if e == "E" and len(num) < 2:
            return w
        if e == "C" and num != "V":
            return w                       # « CCC » ; seul « VC lances » (500) est un exposant
        log.append((w, sup(num, e)))
        return sup(num, e)
    return re.sub(r"(?<![\w&#;])(%s)(xx|XX|es|me|er|re|e|E|c|C|m)(?![\w])" % R, rep, s)


def stage(raws):
    out = dict(raws)
    log = []
    # 1. exposants déjà balisés comme appels de variante : <sup class="var">XX</sup>, <sup class="var">C</sup>
    for f, t in out.items():
        t2 = re.sub(r'(?<=[IVXLC])<sup class="var">\s*(XX|xx|C|c|M|m|e|E|es|me)\s*</sup>',
                    lambda m: (log.append(("var:" + m.group(1), "<sup>%s</sup>" % m.group(1).lower())) or
                               "<sup>%s</sup>" % m.group(1).lower()), t)
        out[f] = t2
    # 2. dates : « mil CCC. IIII » suivi d'un reste d'exposant puis « et » → IIII^xx (1380-1399)
    junk = r"(?:\s*(?:<span class=\"a-verifier\"[^>]*>[^<]*</span>|[,'’\"”°*xX]{1,3}|xx|XX))*"
    for f, t in out.items():
        def date(m):
            log.append(("date:" + re.sub(r"<[^>]+>", "", m.group(0)), m.group(1) + sup("IIII", "xx") + " et"))
            return m.group(1) + sup("IIII", "xx") + " et"
        t = re.sub(r"((?:mil|M\.?|M°)\s+CCC[.,°]?\s*)IIII(?!<sup)%s\s+et(?=\s)" % junk, date, t)
        out[f] = t
    # 3. formes collées
    for f, t in out.items():
        out[f] = text_nodes(t, lambda s: glued(s, log))
    return out, log


def from_scan(raws, log, report):
    out = dict(raws)
    junk = r"(?:<span class=\"a-verifier\"[^>]*>[^<]*</span>|[°\"”'’*©®xX]{1,3}|,\s?x)?"
    for sc, num, e, nxt in getattr(conf.CORR, "EXPOSANTS", []):
        pp = truth.SCAN2PRINT.get(sc, sc)
        hit, already = None, False
        for f, t in out.items():
            a = t.find('id="page-%d"' % (pp + master.OFFSET))
            b = t.find('id="page-%d"' % (pp + 1 + master.OFFSET))
            if a < 0:
                continue
            b = b if b > 0 else len(t)
            pe = t.find("</p>", b)
            r0, r1 = a, (pe if pe > 0 else b)
            alts = re.escape(num) + (("|" + re.escape(num[:-1]) + "[PFO]") if len(num) > 1 else "")
            follow = (r"(?=(?:\s|<sup class=\"var\">[^<]*</sup>|<[^>]+>)*%s(?![\w]))" % re.escape(nxt)) if nxt \
                else r"(?=(?:<[^>]+>)*[,.;:])"
            for m in re.finditer(r"(?<![\w])(%s)(?![\w])((?:</span>)?)(%s)%s" % (alts, junk, follow), t[r0:r1]):
                pos = r0 + m.start()
                if t.rfind("<", 0, pos) > t.rfind(">", 0, pos):
                    continue                    # dans une balise (titre d'une marque)
                hit = (f, pos, r0 + m.end(), m.group(2))
                break
            if hit is None and re.search(r"(?<!\w)%s(?:</span>)?<sup>%s</sup>" % (re.escape(num), e), t[r0:r1]):
                already = True
            break
        if already:
            continue
        if not hit:
            report.append((pp, "exposant %s%s vu sur la numérisation : forme introuvable dans le texte" % (num, e)))
            continue
        f, s0, e0, close = hit
        t = out[f]
        if re.match(r"(?:</span>)?<sup>", t[e0:]):
            continue
        log.append(("scan:%s" % t[s0:e0], sup(num, e) + "  | " + re.sub(r"<[^>]+>", "", t[s0 - 50:e0 + 30]).replace("\n", " ")))
        out[f] = t[:s0] + sup(num, e) + close + t[e0:]
    return out
