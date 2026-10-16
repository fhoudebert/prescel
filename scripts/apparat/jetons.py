"""Mots du maître (suites de lettres) avec leur position dans le XHTML, hors exposants."""
import re
from . import texte as master

LETTERS = re.compile(r"[^\W\d_]+", re.U)


def tokens(raws, P, want):
    """want(paragraph) → True pour garder le paragraphe. Mots : dict(f, s, e, t, para, page)."""
    out = []
    for pi, p in enumerate(P):
        if not want(p):
            continue
        t = raws[p["f"]]
        page = p["page"]
        sup = 0
        for m in re.finditer(r"<[^>]+>|[^<]+", t[p["i0"]:p["i1"]]):
            seg = m.group(0)
            off = p["i0"] + m.start()
            if seg.startswith("<"):
                pg = re.search(r'id="page-(\d+)"', seg)
                if pg:
                    page = int(pg.group(1)) - master.OFFSET
                if seg.startswith("<sup"):
                    sup += 1
                elif seg.startswith("</sup"):
                    sup = max(0, sup - 1)
                continue
            if sup:
                continue
            # entités : masquées (« &amp; » n'est pas un mot), longueur conservée
            masked = re.sub(r"&#?\w+;", lambda e: " " * len(e.group(0)), seg)
            for wm in LETTERS.finditer(masked):
                out.append(dict(f=p["f"], s=off + wm.start(), e=off + wm.end(), t=wm.group(0), para=pi, page=page))
    return out
