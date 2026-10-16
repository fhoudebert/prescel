"""Apparat du tome 13 : blocs <p class="variantes"> refaits page par page.

Numéros d'après l'apparat relu sur la numérisation (apparat_lu.txt) ; texte des entrées repris du
maître (bloc de la page, ou texte égaré au début d'un paragraphe du corps), mots corrigés d'après
la lecture Tesseract de la numérisation quand le maître donne une forme inconnue."""
import collections, difflib, html, re, unicodedata
from epub_temoins import align, skel
from . import conf, texte as master, jetons as mtokens, lecture as truth

LET = re.compile(r"[^\W\d_]+", re.U)
MARK = '<span class="a-verifier" title="%s">%s</span>'


def fold(s):
    s = unicodedata.normalize("NFD", s.lower().replace("’", "'"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def plain(s):
    s = re.sub(r'<sup class="var">.*?</sup>', " ", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def sim(a, b):
    return difflib.SequenceMatcher(None, fold(a), fold(b)).ratio()


LABEL_JUNK = r"[\s—–\-_.,:;'’‘`°*\"“”0-9]"


def clean_entry(t):
    t = re.sub(r"\s+", " ", t).strip()
    # étiquette de l'entrée suivante restée en fin (« — 5-6 », « 1-' », « U », « '° »)
    t = re.sub(r"(?:\s(?:[—–-]+|U|[0-9'’‘`°*\"“”._:-]{1,6}))+\s*$", "", t)
    t = re.sub(r"\s*[—–]+\s*$", "", t)
    t = re.sub(r"(?<=[.,;!?])\s+[A-Za-z°'’]{1,2}[,.]?$", "", t)       # « Tenir. e », « Tanison. I, »
    # étiquette restée en tête
    t = re.sub(r"^(?:(?:[0-9'’‘`°*\"“”._:-]{1,6}|U|[—–-]+)\s)+", "", t)
    return t.strip()


def cand_scores(words, firsts_list):
    """score[i] : vraisemblance qu'une entrée commence au mot i."""
    sc = [0.0] * len(words)
    for firsts in firsts_list:
        if not firsts:
            continue
        for i in range(len(words)):
            s1 = sim(words[i][2], firsts[0])
            if len(firsts) > 1 and i + 1 < len(words):
                s = (2 * s1 + sim(words[i + 1][2], firsts[1])) / 3
            else:
                s = s1 if len(firsts[0]) >= 3 or s1 == 1 else s1 * 0.9
            # premier mot perdu : l'entrée commence au deuxième
            if len(firsts) > 1:
                s = max(s, 0.85 * sim(words[i][2], firsts[1]))
            sc[i] = max(sc[i], s)
    return sc


def segment(text, ents, alt=None):
    """découpe text en entrées (ordre imposé, meilleur total) ; [texte ou None]."""
    words = [(m.start(), m.end(), m.group(0)) for m in LET.finditer(text)]
    n, K = len(words), len(ents)
    scores = []
    for k, e in enumerate(ents):
        fl = [LET.findall(e["words"])]
        if alt and len(alt) == K:
            fl.append(LET.findall(alt[k])[:2])
        scores.append(cand_scores(words, fl))
    # programmation dynamique : best[k][i] = meilleur total avec l'entrée k au mot i (ou absente)
    NEG = -1e9
    best = [[NEG] * (n + 1) for _ in range(K + 1)]     # i = n : « pas encore placé » (dernier mot utilisé)
    back = [[None] * (n + 1) for _ in range(K + 1)]
    # état : position du dernier mot utilisé + 1 (pos), on code par j = premier mot libre
    best[0][0] = 0.0
    for k in range(K):
        for j in range(n + 1):
            if best[k][j] == NEG:
                continue
            # entrée k absente
            if best[k][j] - 0.3 > best[k + 1][j]:
                best[k + 1][j], back[k + 1][j] = best[k][j] - 0.3, (j, None)
            for i in range(j, n):
                s = scores[k][i]
                if s < 0.62:
                    continue
                v = best[k][j] + s
                if v > best[k + 1][i + 1]:
                    best[k + 1][i + 1], back[k + 1][i + 1] = v, (j, i)
    j = max(range(n + 1), key=lambda x: best[K][x])
    starts = [None] * K
    for k in range(K, 0, -1):
        pj, i = back[k][j]
        starts[k - 1] = i
        j = pj
    out = []
    first = next((i for i in starts if i is not None), None)
    for k, i in enumerate(starts):
        if i is None:
            # texte avant la première entrée trouvée : c'est l'entrée 1 dont les premiers mots sont perdus
            if k == 0 and first is not None and first > 0 and words[first][0] > 0:
                lead = clean_entry(text[:words[first][0]])
                if LET.search(lead):
                    out.append(lead)
                    continue
            out.append(None)
            continue
        nxt = next((starts[j] for j in range(k + 1, K) if starts[j] is not None), None)
        end = words[nxt][0] if nxt is not None else len(text)
        out.append(clean_entry(text[words[i][0]:end]))
    return out


def label(e):
    return "%d" % e["a"] if e["a"] == e["b"] else "%d-%d" % (e["a"], e["b"])


# ---------------------------------------------------------------------------------------------
def known_words(raws):
    c = collections.Counter()
    for t in raws.values():
        for w in LET.findall(plain(t)):
            c[fold(w)] += 1
    return c


_GOOGLE = None


def google_foot_words(pp):
    """mots de l'apparat de la page dans l'EPUB Google (même édition, autre OCR)."""
    global _GOOGLE
    if _GOOGLE is None:
        try:
            _GOOGLE = conf.GOOGLE or {}
        except Exception:
            _GOOGLE = {}
    g = _GOOGLE.get(str(pp), {})
    paras = list(g.get("fn", []))
    if not paras and g.get("body"):
        last = g["body"][-1]
        if " — " in last or re.match(r"\W*\d", last) or len(last) < 120:
            paras = [last]
    return {fold(w) for t in paras for w in LET.findall(t)}


def correct_words(text, alt, book, gwords=frozenset()):
    """mots du maître remplacés par ceux de la lecture Tesseract (même entrée) quand le maître
    donne une forme inconnue et la lecture une forme connue de même longueur à peu près."""
    if not alt:
        return text, []
    mw = [(m.start(), m.end(), m.group(0)) for m in LET.finditer(text)]
    aw = LET.findall(alt)
    sm = difflib.SequenceMatcher(None, [fold(w[2]) for w in mw], [fold(w) for w in aw], autojunk=False)
    reps = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace" or i2 - i1 != j2 - j1:
            continue
        for k in range(i2 - i1):
            m, a = mw[i1 + k][2], aw[j1 + k]
            if re.fullmatch(r"[IVXLCDM]+[a-z]{0,2}", m) or re.fullmatch(r"[IVXLCDM]+[a-z]{0,2}", a):
                continue                       # nombres romains : affaire des exposants, pas des mots
            fm, fa = fold(m), fold(a)
            known_m = fm in conf.WORDS or book[fm] >= 3
            known_a = fa in conf.WORDS or book[fa] >= 2
            # deux lectures de la numérisation (Tesseract, Google) d'accord contre le maître
            agree = fa in gwords and fm not in gwords
            if ((not known_m and known_a) or agree) and sim(m, a) >= 0.5:
                if m[0].isupper() and not a[0].isupper():
                    a = a[0].upper() + a[1:]
                reps.append((mw[i1 + k][0], mw[i1 + k][1], a, m))
    out = text
    for s, e, a, m in sorted(reps, reverse=True):
        out = out[:s] + a + out[e:]
    res = [(m, a) for s, e, a, m in reps]
    # mots perdus par l'OCR en tête ou en fin d'entrée (« pensa » / « Si pensa »)
    ops = sm.get_opcodes()
    if ops and len(mw) >= 1:
        t0, i1, i2, j1, j2 = ops[0]
        if t0 == "insert" and i1 == 0 and 0 < j2 - j1 <= 2 and all(fold(w) in gwords or fold(w) in conf.WORDS for w in aw[j1:j2]):
            add = " ".join(aw[j1:j2])
            first = out[:1]
            out = add[:1].upper() + add[1:] + " " + (first.lower() if first.isupper() and not re.match(r"[IVXLC]+\b", out) else first) + out[1:]
            res.append(("", add))
        t0, i1, i2, j1, j2 = ops[-1]
        if t0 == "insert" and i1 == len(mw) and 0 < j2 - j1 <= 2 and all(fold(w) in gwords for w in aw[j1:j2]):
            add = " ".join(aw[j1:j2])
            out = re.sub(r"[\s.,;]*$", "", out) + (", " if out.rstrip().endswith(",") else " ") + add + "."
            res.append(("", add))
    return out, res


def esc(t):
    return html.escape(t, quote=False)


def build_block(p, ents, texts, alts, book, report):
    parts = []
    for k, (e, t) in enumerate(zip(ents, texts)):
        lab = label(e)
        alt = alts[k] if alts and len(alts) == len(ents) else None
        if t is None or not LET.search(t):
            if alt and LET.search(alt):
                body = MARK % ("entrée reprise de la lecture de la numérisation (absente du texte OCR)", esc(alt))
                report.append((p, "entrée %s reprise de la numérisation : « %s »" % (lab, alt)))
            else:
                body = MARK % ("entrée introuvable : à recopier d'après la numérisation", esc(e["words"] + " …"))
                report.append((p, "entrée %s introuvable" % lab))
        else:
            t2, reps = correct_words(t, alt, book, google_foot_words(p))
            for m, a in reps:
                report.append((p, ("apparat : « %s » → « %s » (lecture de la numérisation)" % (m, a)) if m else
                               "apparat : « %s » ajouté d'après la numérisation" % a))
            body = esc(t2)
        if not e["sure"]:
            lab = MARK % ("numéro de l'apparat mal lisible sur la numérisation", lab)
        parts.append("%s %s" % (lab, body))
    return " — ".join(parts)


def align_with_foot(raws, P, S):
    """mots de tous les paragraphes alignés sur corps + apparat de la numérisation (dans l'ordre)."""
    M = mtokens.tokens(raws, P, lambda p: p["tag"] == "p")
    W = []
    for sc in sorted(S, key=int):
        for w in S[sc]["body"]:
            W.append(dict(t=w["t"], sc=int(sc), kind="body"))
        for w in S[sc]["foot"]:
            W.append(dict(t=w["t"], sc=int(sc), kind="foot"))
    ops = align([skel(t["t"]) for t in M], [skel(w["t"]) for w in W])
    m2w = [None] * len(M)
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                m2w[i1 + k] = j1 + k
    return M, W, m2w


TERMINAL = re.compile(r"[.!?»:;]\s*(?:<sup class=\"var\">\d+</sup>)?\s*$")


def stage(raws):
    P = master.paragraphs(raws)
    S = conf.SCAN
    T = truth.load()
    book = known_words(raws)
    M, W, m2w = align_with_foot(raws, P, S)
    edits, report = [], []
    blocks = collections.defaultdict(list)
    for k, p in enumerate(P):
        if "variantes" in p["cls"] and p["title"]:
            blocks[p["title"]].append(k)
    # texte égaré : paragraphes du corps qui commencent par des mots alignés sur l'apparat d'une page
    first_word = {}
    for i, t in enumerate(M):
        first_word.setdefault(t["para"], i)
    strays = collections.defaultdict(list)          # page imprimée → [(para, i_first, i_last)]
    para_words = collections.defaultdict(list)
    for i, t in enumerate(M):
        para_words[t["para"]].append(i)
    for pi, idx in para_words.items():
        if "variantes" in P[pi]["cls"]:
            continue
        run = []
        for i in idx:
            j = m2w[i]
            if j is not None and W[j]["kind"] == "foot":
                run.append(i)
            elif j is None and run:
                run.append(i)                      # mot illisible au milieu de l'apparat égaré
            else:
                break
        while run and m2w[run[-1]] is None:
            run.pop()
        if not run:
            continue
        sc = W[m2w[run[0]]]["sc"]
        pp = truth.SCAN2PRINT.get(sc, sc)
        if pp is None or pp not in T:
            continue
        firsts = {fold(LET.findall(e["words"])[0]) for e in T[pp] if LET.findall(e["words"])}
        if len(run) < 2 and fold(M[run[0]]["t"]) not in firsts:
            continue
        strays[pp].append((pi, run[0], run[-1]))
    for pp, ents in sorted(T.items()):
        ks = blocks.get(pp, [])
        sources = []
        for k in ks:
            p = P[k]
            sources.append(plain(raws[p["f"]][p["i0"]:p["i1"]]))
        stray_edits = []
        for pi, i0, i1 in strays.get(pp, []):
            p = P[pi]
            f, t = p["f"], raws[p["f"]]
            # fin : ancre de page qui suit, sinon premier mot aligné sur le corps
            end = None
            am = re.compile(r'<a id="page-\d+"\s*/>|<a id="page-\d+"></a>').search(t, M[i1]["e"], p["i1"])
            nxt = next((i for i in para_words[pi] if i > i1 and m2w[i] is not None and W[m2w[i]]["kind"] == "body"), None)
            between = len([i for i in para_words[pi] if i > i1 and am and M[i]["s"] < am.start()])
            if am and between <= 6:
                end = am.start()           # l'apparat égaré va jusqu'à l'ancre de la page suivante
            else:
                cands = [x for x in (am.start() if am else None, M[nxt]["s"] if nxt is not None else None) if x is not None]
                end = min(cands) if cands else p["i1"]
            span = t[p["i0"]:end]
            sources.append(plain(span))
            # paragraphe précédent sans ponctuation finale : on recolle
            prev = P[pi - 1] if pi > 0 else None
            rest = t[end:p["i1"]].strip()
            if prev and prev["f"] == f and "variantes" not in prev["cls"] and prev["tag"] == "p" \
                    and not TERMINAL.search(t[prev["i0"]:prev["i1"]]) and rest:
                stray_edits.append((f, prev["i1"], end, " " if not rest.startswith("<a") else "",
                                    "p. %d : apparat égaré retiré du corps, paragraphes recollés" % pp))
            elif not rest or not re.search(r"[^\W\d_]", re.sub(r"<[^>]+>", "", rest)):
                # paragraphe entier d'apparat : supprimé (ancres gardées)
                anchors = "".join(re.findall(r'<a id="page-\d+"\s*/>', t[p["i0"]:p["i1"]]))
                stray_edits.append((f, p["s"], p["e"], ("<p>%s</p>" % anchors) if anchors else "",
                                    "p. %d : paragraphe d'apparat sans classe remplacé" % pp))
            else:
                stray_edits.append((f, p["i0"], end, "", "p. %d : apparat égaré retiré du début du paragraphe" % pp))
        if not sources:
            report.append((pp, "apparat absent du texte"))
            sources = [""]
        text = " ".join(sources)
        sc = truth.scan_of(pp)
        alts = [" ".join(e["words"]) for e in S[str(sc)]["entries"]] if sc is not None and str(sc) in S else None
        if alts and len(alts) != len(ents):
            alts = None
        texts = segment(text, ents, alts)
        block = build_block(pp, ents, texts, alts, book, report)
        newp = '<p class="variantes" title="p. %d">%s</p>' % (pp, block)
        edits.extend(stray_edits)
        if ks:
            k0 = ks[0]
            edits.append((P[k0]["f"], P[k0]["s"], P[k0]["e"], newp, "p. %d : apparat renuméroté" % pp))
            for k in ks[1:]:
                edits.append((P[k]["f"], P[k]["s"], P[k]["e"], "", "p. %d : bloc d'apparat en double fondu" % pp))
        else:
            # après le paragraphe où commence la page suivante
            anc = 'id="page-%d"' % (pp + 1 + master.OFFSET)
            host = next((q for q in P if anc in raws[q["f"]][q["s"]:q["e"]]), None)
            if host is None:
                report.append((pp, "apparat refait mais sans place (ancre de la page suivante absente)"))
                continue
            edits.append((host["f"], host["e"], host["e"], "\n  " + newp, "p. %d : bloc d'apparat créé" % pp))
    # bloc créé en fin d'un paragraphe recollé au suivant : déplacé en fin du paragraphe recollé
    dels = [(f, s0, e0) for f, s0, e0, r, n in edits if e0 > s0]
    fixed = []
    for f, s0, e0, r, n in edits:
        if s0 == e0:
            for f2, a, b in dels:
                if f2 == f and a <= s0 < b:
                    q = next(q for q in P if q["f"] == f and q["s"] <= b < q["e"])
                    s0 = e0 = q["e"]
                    break
        fixed.append((f, s0, e0, r, n))
    return fixed, report


def fix_blocks(raws):
    """Blocs <p class="variantes"> qui sont en fait du corps (paragraphe entier) ou qui en contiennent
    la suite (texte du corps collé après l'apparat) : rendus au corps."""
    P = master.paragraphs(raws)
    S = conf.SCAN
    T = truth.load()
    M, W, m2w = align_with_foot(raws, P, S)
    pw = collections.defaultdict(list)
    for i, t in enumerate(M):
        pw[t["para"]].append(i)
    edits, log = [], []
    for pi, p in enumerate(P):
        if "variantes" not in p["cls"] or not p["title"]:
            continue
        f, t = p["f"], raws[p["f"]]
        inner = t[p["i0"]:p["i1"]]
        txt = plain(inner)
        if txt.lstrip().startswith("Var"):
            continue                                   # variante d'un passage entier : c'est de l'apparat
        idx = pw[pi]
        kinds = "".join("B" if m2w[i] is not None and W[m2w[i]]["kind"] == "body" else
                        ("F" if m2w[i] is not None else "-") for i in idx)
        whole = False
        if p["title"] not in T:
            whole = len(txt) > 120                     # page sans apparat sur la numérisation
        else:
            ents = T[p["title"]]
            segs = segment(txt, ents)
            if all(s is None for s in segs) and len(txt) > 150:
                whole = True
            elif kinds.startswith("BBBBB") and kinds.count("B") > 0.8 * len(kinds):
                whole = True
        prev = P[pi - 1] if pi > 0 else None
        if whole:
            anc = 'id="page-%d"' % (p["title"] + 1 + master.OFFSET)
            a = t.find(anc, prev["i0"], prev["i1"]) if prev and prev["f"] == f else -1
            if a > 0 and not TERMINAL.search(inner) and re.search(r"[^\W\d_]", t[a:prev["i1"]]):
                # fin de la page (sans ponctuation finale) : avant l'ancre de la page suivante
                a0 = t.rfind("<a ", prev["i0"], a)
                edits.append((f, a0, a0, "</p>\n  <p>%s " % inner.strip(), "bloc p. %d : fin de page remise avant la page suivante" % p["title"]))
                edits.append((f, p["s"], p["e"], "", "bloc p. %d : bloc retiré" % p["title"]))
                log.append((p["title"], "bloc d'apparat qui était la fin de la page, remis à sa place : « %s… »" % txt[:50]))
                continue
            edits.append((f, p["s"], p["e"], "<p>%s</p>" % inner, "bloc p. %d : c'est du corps, rendu au texte" % p["title"]))
            log.append((p["title"], "bloc d'apparat qui était du corps : « %s… »" % txt[:50]))
            continue
        k_pre = None
        if kinds.startswith("BBBBB") and "F" in kinds:
            k_pre = kinds.find("F")
        elif p["title"] in T:
            # premier mot de la première entrée loin dans le bloc : ce qui précède est du corps
            words = [m.group(0) for m in LET.finditer(txt)]
            fl = [LET.findall(T[p["title"]][0]["words"])]
            sc = cand_scores([(0, 0, w) for w in words], fl)
            first = next((i for i, v in enumerate(sc) if v >= 0.86), None)
            if first is not None and first >= 15 and len(idx) == len(words):
                head = txt[:[m.start() for m in LET.finditer(txt)][first]]
                if not re.search(r"—|(?<!\w)\d{1,2}\s?[-.]\s?\d{1,2}(?!\w)", head):
                    k_pre = first
        if k_pre:
            # corps en tête du bloc (fin de la page, sautée par l'OCR), apparat ensuite
            k = k_pre
            cut = M[idx[k]]["s"]
            pre = t[p["i0"]:cut]
            pre = re.sub(r"\s*$", "", pre)
            anc = 'id="page-%d"' % (p["title"] + 1 + master.OFFSET)
            a = t.find(anc, prev["i0"], prev["i1"]) if prev and prev["f"] == f else -1
            edits.append((f, p["i0"], cut, "", "bloc p. %d : début de corps retiré" % p["title"]))
            if a > 0:
                a0 = t.rfind("<a ", prev["i0"], a)
                edits.append((f, a0, a0, "</p>\n  <p>%s " % pre.strip(), "bloc p. %d : fin de page remise avant la page suivante" % p["title"]))
            else:
                edits.append((f, p["s"], p["s"], "<p>%s</p>\n  " % pre.strip(), "bloc p. %d : fin de page remise en paragraphe" % p["title"]))
            log.append((p["title"], "fin de page égarée dans l'apparat, rendue au corps : « %s… »" % plain(pre)[:50]))
            continue
        k = kinds.find("BBBBB")
        if k > 0 and "F" in kinds[:k]:
            i0 = idx[k]
            # ancre de page juste avant le premier mot du corps : elle part avec lui
            cut = M[i0]["s"]
            am = list(re.finditer(r'<a id="page-\d+"\s*/>', t[p["i0"]:cut]))
            if am and p["i0"] + am[-1].start() > M[idx[k - 1]]["e"]:
                cut = p["i0"] + am[-1].start()
            body = t[cut:p["i1"]].strip()
            edits.append((f, cut, p["i1"], "", "bloc p. %d : suite du corps retirée" % p["title"]))
            if prev and prev["f"] == f and "variantes" not in prev["cls"] and not TERMINAL.search(t[prev["i0"]:prev["i1"]]):
                edits.append((f, prev["i1"], prev["i1"], " " + body, "bloc p. %d : suite du corps recollée au paragraphe" % p["title"]))
            else:
                edits.append((f, p["e"], p["e"], "\n  <p>%s</p>" % body, "bloc p. %d : suite du corps en paragraphe" % p["title"]))
            log.append((p["title"], "texte du corps collé à l'apparat, rendu au corps : « %s… »" % plain(body)[:50]))
    return edits, log
