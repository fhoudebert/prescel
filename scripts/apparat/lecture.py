"""Apparat relu à vue et correspondance vues de la numérisation / pages imprimées."""
import re
SCAN2PRINT = {}      # vue de la numérisation → page imprimée (None : doublon) ; rempli par conf.configure
PRINT2SCAN = {}


def set_map(m):
    SCAN2PRINT.clear()
    SCAN2PRINT.update(m)
    PRINT2SCAN.clear()
    PRINT2SCAN.update({v: k for k, v in m.items() if v is not None})


def scan_of(p):
    """vue de la numérisation d'une page imprimée (None si absente)."""
    if p in PRINT2SCAN:
        return PRINT2SCAN[p]
    if p in SCAN2PRINT:          # page imprimée dont la vue « normale » est autre chose
        return None
    return p


def load(path=None):
    """apparat relu : « page: 1-2 Mots | 3 Mots » (page = vue de la numérisation ; « ? » : douteux)."""
    from . import conf
    path = path or conf.APPARAT
    T = {}
    for l in open(path, encoding="utf-8"):
        if l.startswith("#") or not l.strip():
            continue
        p, rest = l.split(":", 1)
        ents = []
        for e in rest.split("|"):
            e = e.strip()
            m = re.match(r"(\d+)(?:-(\d+))?(\?)?\s+(.*)", e)
            a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else a
            ents.append(dict(a=a, b=b, sure=not m.group(3), words=m.group(4)))
        sp = int(p)
        pp = SCAN2PRINT.get(sp, sp)
        if pp is not None:
            T[pp] = ents
    return T
