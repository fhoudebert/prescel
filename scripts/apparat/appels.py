"""Appels de variantes du tome 13 : positions lues sur la numérisation, numéros d'après l'apparat
relu ; corrections à faire dans le maître (liste d'éditions)."""
import bisect, collections, re
from epub_temoins import align, skel
from . import conf, texte as master, jetons as mtokens, lecture as truth

SUP = '<sup class="var">%d</sup>'
CALL_RE = re.compile(r'<sup class="var">(?:<span class="a-verifier"[^>]*>)?\s*(\d+)\s*(?:</span>)?</sup>')
MARK_RE = re.compile(r'<span class="a-verifier" title="([^"]*)">([^<]*)</span>')
# signes qui tiennent la place d'un appel mal lu, à la suite d'un mot
JUNK = re.compile(r"^(\s?)((?:['’`°*\"“”^]|\d{1,2})+)(?=[\s,.;:!?»)]|$|<)")


def build(raws=None):
    z, raws0 = master.load(conf.EPUB)
    raws = raws or raws0
    P = master.paragraphs(raws)
    M = mtokens.tokens(raws, P, lambda p: "variantes" not in p["cls"] and p["tag"] == "p")
    S = conf.SCAN
    W, base = [], {}
    for p in sorted(S, key=int):
        base[int(p)] = len(W)
        for i, w in enumerate(S[p]["body"]):
            W.append(dict(w, p=int(p), i=i))
    ops = align([skel(t["t"]) for t in M], [skel(w["t"]) for w in W])
    m2w = [None] * len(M)
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                m2w[i1 + k] = j1 + k
    w2m = {j: i for i, j in enumerate(m2w) if j is not None}
    # vues hors d'ordre (doublons, pages interverties) : alignement local sur la page imprimée
    for sc, b0 in base.items():
        n = len(S[str(sc)]["body"])
        if not n or sum(1 for i in range(n) if b0 + i in w2m) >= 0.5 * n:
            continue
        pp = truth.SCAN2PRINT.get(sc, sc)
        if pp is None:
            continue
        mi = [i for i, t in enumerate(M) if t["page"] is not None and pp - 1 <= t["page"] <= pp + 1]
        if not mi:
            continue
        lops = align([skel(M[i]["t"]) for i in mi], [skel(W[b0 + j]["t"]) for j in range(n)])
        for tag, i1, i2, j1, j2 in lops:
            if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
                for k in range(i2 - i1):
                    w2m[b0 + j1 + k] = mi[i1 + k]
    # compléments locaux : mots de la page restés sans correspondant (difflib, égalités seules)
    import difflib
    bypage = collections.defaultdict(list)
    for i, t in enumerate(M):
        if t["page"] is not None:
            bypage[t["page"]].append(i)
    for sc, b0 in base.items():
        n = len(S[str(sc)]["body"])
        pp = truth.SCAN2PRINT.get(sc, sc)
        if not n or pp is None:
            continue
        mi = bypage.get(pp - 1, []) + bypage.get(pp, []) + bypage.get(pp + 1, [])
        if not mi:
            continue
        sm = difflib.SequenceMatcher(None, [skel(M[i]["t"]) for i in mi], [skel(W[b0 + j]["t"]) for j in range(n)], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                continue
            for k in range(i2 - i1):
                g = b0 + j1 + k
                if g not in w2m:
                    w2m[g] = mi[i1 + k]
    return z, raws, P, M, S, W, base, m2w, w2m


def scan_pos(g, w2m):
    """Mot du maître après lequel se place un appel situé après le mot g de la numérisation."""
    for d in range(0, 4):
        if g - d in w2m:
            return w2m[g - d] + d, d
    return None, None


def master_calls(raws, M):
    starts = [(t["f"], t["s"]) for t in M]
    out = []
    for f in master.FILES:
        for m in CALL_RE.finditer(raws[f]):
            k = bisect.bisect_left(starts, (f, m.start())) - 1
            out.append(dict(k=k, n=int(m.group(1)), f=f, s=m.start(), e=m.end()))
    return out


def refine(i, g, M, W):
    """Position fine : le mot du maître (i-4..i+3) qui correspond au mot g de la numérisation ;
    un mot coupé en fin de ligne (« onc- ques ») est recollé avant comparaison."""
    t = W[g]["t"]
    if g > 0 and W[g - 1]["li"] != W[g]["li"] and W[g - 1]["raw"].rstrip().endswith(("-", "¬")):
        t = W[g - 1]["t"] + t
    sg = skel(t)
    best = None
    for j in range(max(0, i - 4), min(len(M), i + 4)):
        if skel(M[j]["t"]) == sg:
            if best is None or abs(j - i) < abs(best - i):
                best = j
    return best


def gap(raws, M, i, P=None):
    """(f, début, fin) du texte brut entre le mot i et le mot suivant, sans sortir du paragraphe."""
    t = M[i]
    end = M[i + 1]["s"] if i + 1 < len(M) and M[i + 1]["f"] == t["f"] and M[i + 1]["para"] == t["para"] else None
    if end is None:
        end = P[t["para"]]["i1"] if P else t["e"] + 80
    return t["f"], t["e"], end


JUNK_SPAN = re.compile(r'<span class="a-verifier" title="([^"]*)">\s*((?:\d{1,2}|[\'’`°*"“”^]{1,3}|[A-Za-zû]{1,2}))\s*</span>')
JUNK_CH = re.compile(r"['’`°*\"“”^]{1,3}(?=[\s,.;:!?»)<]|$)|(?<![\w>])(?<!\d )\d{1,2}(?![\w.,]\d)(?=[\s,.;:!?»)<]|$)")


def find_existing(raws, f, s, e):
    m = CALL_RE.search(raws[f], s, e)
    return m


def junk_in(raws, f, s, e, glued_only=False):
    """Signe mal lu à la place d'un appel entre s et e : (début, fin) ou None."""
    seg = raws[f][s:e]
    g = re.match(r"\d{1,2}(?=[\s,.;:!?»)]|<|$)", seg)
    if g:
        return s, s + g.end()               # chiffre collé au mot : « accord6 »
    m = JUNK_SPAN.search(seg)
    if m and not glued_only:
        return s + m.start(), s + m.end()
    # caractères hors balises
    pos = 0
    for part in re.split(r"(<[^>]+>)", seg):
        if part.startswith("<"):
            pos += len(part)
            continue
        for jm in JUNK_CH.finditer(part):
            if glued_only and jm.start() != 0:
                continue
            # pas une apostrophe d'élision (suivie d'une lettre) ni un chiffre de date (« 1388 »)
            return s + pos + jm.start(), s + pos + jm.end()
        pos += len(part)
    return None


def find_pair(M, lo, hi, prev, nxt, nth=1):
    """nième mot du maître « prev » suivi de « nxt » dans [lo, hi] (comparaison sur le squelette)."""
    sp_, sn = skel(prev), skel(nxt) if nxt else None
    for i in range(max(0, lo), min(len(M) - 1, hi) + 1):
        if skel(M[i]["t"]) == sp_ and (sn is None or skel(M[i + 1]["t"]) == sn):
            nth -= 1
            if not nth:
                return i
    return None


def order(t):
    """rang d'un appel : mot, avant le mot (tête de paragraphe), second appel au même blanc."""
    return t["i"] - (0.5 if t.get("before") else 0) + (0.25 if t.get("twin") else 0)


def page_targets(p, N, sp, base, M, W, w2m, MC):
    manual = conf.CORR
    pp = truth.SCAN2PRINT.get(p, p)
    drop = set(manual.DROP.get(pp, []))
    if drop:
        sp = dict(sp, calls=[c for k, c in enumerate(sp["calls"], 1) if k not in drop])
    idx = [w2m[base[p] + i] for i in range(len(sp["body"])) if base[p] + i in w2m]
    if not idx:
        return None, "page non alignée", []
    lo, hi = min(idx) - 1, max(idx) + 1
    mine = [c for c in MC if lo <= c["k"] <= hi]
    core = [c for c in mine if min(idx) <= c["k"] < max(idx)]
    scan = []
    for c in sp["calls"]:
        g = base[p] + c["after"] if c["after"] >= 0 else base[p] - 1
        if c.get("linestart") and g + 1 in w2m:
            # appel en début de ligne : avant le mot qui suit (« ¹ Le roy là estant »)
            scan.append(dict(i=w2m[g + 1], sure=True, src="scan", before=True))
            continue
        if g < 0:
            continue
        i, d = scan_pos(g, w2m)
        sure = d == 0
        if i is not None and d:
            j = refine(i, g, M, W)
            if j is not None:
                i, sure = j, True
        if i is not None:
            scan.append(dict(i=i, sure=sure, src="scan"))
    for prev, nxt, *nth in manual.ADD.get(pp, []):
        # (mot avant, mot après[, rang de l'occurrence sur la page])
        j = find_pair(M, lo, hi, prev, nxt, *nth)
        if j is None:
            j = find_pair(M, lo - 40, hi + 40, prev, nxt, *nth)
        if j is not None and all(t["i"] != j or t.get("before") for t in scan):
            scan.append(dict(i=j, sure=True, src="relu"))
    for t in scan:
        # « avant le mot j », sauf en tête de paragraphe, c'est « après le mot j-1 »
        if t.get("before") and t["i"] > 0 and M[t["i"] - 1]["para"] == M[t["i"]]["para"]:
            t["i"] -= 1
            t["before"] = False
            # deux appels au même blanc : « aaisier⁴ | ⁵ euls » (fin de ligne, début de la suivante)
            t["twin"] = any(u is not t and u["i"] == t["i"] and not u.get("twin") for u in scan)
    scan.sort(key=order)
    if len(scan) == N:
        targets, status = scan, "numérisation"
    else:
        un = list(scan)
        for c in core:
            if all(abs(c["k"] - t["i"]) > 1 for t in scan):
                un.append(dict(i=c["k"], sure=True, src="maître"))
        un.sort(key=order)
        if len(un) == N:
            targets, status = un, "numérisation + maître"
        elif len(core) == N:
            targets, status = [dict(i=c["k"], sure=True, src="maître") for c in core], "maître"
        else:
            return None, "appels : apparat %d, numérisation %d, maître %d — page laissée" % (N, len(scan), len(mine)), mine
    if any(order(a) >= order(b) for a, b in zip(targets, targets[1:])):
        return None, "appels dans le désordre — page laissée", mine
    return targets, status, mine


def solve(only=None, manual=None, raws=None):
    z, raws, P, M, S, W, base, m2w, w2m = build(raws)
    T = truth.load()
    MC = master_calls(raws, M)
    edits, report = [], []
    plan = {}
    for p, ents in sorted(T.items()):
        if only and p not in only:
            continue
        N = ents[-1]["b"]
        sc = truth.scan_of(p)
        sp = S.get(str(sc)) if sc is not None else None
        if not sp:
            report.append((p, "page absente de la numérisation"))
            continue
        partial = getattr(conf.CORR, "PARTIAL", {}).get(p)
        targets, status, mine = page_targets(sc, partial[0] if partial else N, sp, base, M, W, w2m, MC)
        if partial and targets:
            targets[-1]["note"] = partial[1]
        if manual and p in manual:
            targets, status = manual[p](M, mine), "relu à la main"
        if targets is None:
            report.append((p, status))
            continue
        plan[p] = (targets, status, mine, sc)
    claimed = set()
    for p, (targets, status, mine, sc) in plan.items():
        for k, t in enumerate(targets, 1):
            i = t["i"]
            if t.get("before"):
                # en tête de paragraphe : entre le début du paragraphe et le mot
                f = M[i]["f"]
                s, e = P[M[i]["para"]]["i0"], M[i]["s"]
                seg = raws[f][s:e]
                ex = CALL_RE.search(raws[f], s, e)
                sup = SUP % k
                if ex:
                    claimed.add((f, ex.start()))
                    if int(ex.group(1)) != k:
                        edits.append((f, ex.start(), ex.end(), SUP % k, "p. %d : appel %s renuméroté %d" % (p, ex.group(1), k)))
                    continue
                jk = junk_in(raws, f, s, e)
                if jk:
                    edits.append((f, jk[0], jk[1], sup, "p. %d : signe « %s » → appel %d" % (p, raws[f][jk[0]:jk[1]][:60], k)))
                else:
                    # après les ancres de page en tête de paragraphe
                    pos = s + len(re.match(r"(?:\s|<a [^>]*/>|<a [^>]*></a>)*", seg).group(0))
                    edits.append((f, pos, pos, sup + " ", "p. %d : appel %d ajouté en tête de paragraphe" % (p, k)))
                continue
            f, s, e = gap(raws, M, i, P)
            if t.get("twin"):
                s = last          # après l'appel précédent, au même blanc
            ex = CALL_RE.search(raws[f], s, e)
            if ex and not re.search(r"[^\W\d_]", re.sub(r"<[^>]+>", "", raws[f][s:ex.start()])):
                claimed.add((f, ex.start()))
                if int(ex.group(1)) != k:
                    edits.append((f, ex.start(), ex.end(), SUP % k, "p. %d : appel %s renuméroté %d" % (p, ex.group(1), k)))
                last = ex.end()
                continue
            last = s
            if t.get("note"):
                t["sure"] = False
            sup = SUP % k if t["sure"] else '<sup class="var"><span class="a-verifier" title="%s">%d</span></sup>' % (t.get("note") or "appel placé d\'après la numérisation (position approchée)", k)
            jk = junk_in(raws, f, s, e)
            if jk and jk[0] == s:
                edits.append((f, jk[0], jk[1], sup, "p. %d : signe « %s » → appel %d" % (p, raws[f][jk[0]:jk[1]][:60], k)))
                last = jk[1]
            elif jk:
                edits.append((f, s, s, sup, "p. %d : appel %d ajouté" % (p, k)))
                edits.append((f, jk[0], jk[1], "", "p. %d : signe « %s » (appel %d mal lu) retiré" % (p, raws[f][jk[0]:jk[1]][:60], k)))
            else:
                edits.append((f, s, s, sup, "p. %d : appel %d ajouté" % (p, k)))
        report.append((p, "appels %d (%s)" % (len(targets), status)))
    for p, (targets, status, mine, sc) in plan.items():
        sp = S[str(sc)]
        idx = [w2m[base[sc] + i] for i in range(len(sp["body"])) if base[sc] + i in w2m]
        for c in mine:
            if not (min(idx) <= c["k"] < max(idx)):
                continue            # appel en lisière de page : peut-être celui de la page voisine
            if (c["f"], c["s"]) not in claimed:
                claimed.add((c["f"], c["s"]))
                edits.append((c["f"], c["s"], c["e"], "", "p. %d : appel %d du maître hors place, retiré" % (p, c["n"])))
    # appels restés sans place : sur une page relue (avec ou sans apparat), hors des pages absentes
    # de la numérisation ; ce sont des signes pris pour des appels par une passe précédente
    missing = {p for p in range(1, max(T) + 2) if truth.scan_of(p) is None}
    for c in MC:
        if (c["f"], c["s"]) in claimed or c["k"] < 0:
            continue
        pg = M[c["k"]]["page"]
        if pg is None or not (1 <= pg <= 319) or pg in missing or (pg + 1) in missing:
            continue
        if pg in T and pg not in plan:
            continue                      # page laissée : on ne touche à rien
        claimed.add((c["f"], c["s"]))
        edits.append((c["f"], c["s"], c["e"], "", "p. %d : appel %d sans place sur la numérisation, retiré" % (pg, c["n"])))
    return raws, edits, report


def apply(raws, edits):
    out = dict(raws)
    by = collections.defaultdict(list)
    for f, s, e, r, note in edits:
        by[f].append((s, e, r, note))
    conflicts = []
    for f, L in by.items():
        L.sort(key=lambda x: (x[0], x[1]))
        t = raws[f]
        res, pos = [], 0
        for s, e, r, note in L:
            if s < pos:
                conflicts.append((f, s, note))
                continue
            res.append(t[pos:s]); res.append(r); pos = e
        res.append(t[pos:])
        out[f] = "".join(res)
    return out, conflicts
