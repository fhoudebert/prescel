#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_appels.py — Contrôle page par page des appels de variantes d'une édition à apparat
(Kervyn de Lettenhove : appels « mot⁵ » numérotés par page imprimée, apparat « 5-6 Chose. » en
bas de page, <p class="variantes" title="p. N">) et restitution des appels que l'OCR a mal lus.

Le numéro d'un appel se déduit de ses voisins : sur une page, les appels vont de 1 à N dans
l'ordre, et l'apparat de la page dit jusqu'où (« … — 7-8 Prochains. » : N = 8). Entre l'appel 4
et l'appel 6, un seul signe suspect (« dire' », « pour Il aler », « traittié3l'escuier »,
« doubte '° », « 1S doubte ») est l'appel 5. Un appel au numéro faux entre deux appels justes
(« 4 … 1 … 6 ») est renuméroté. Rien n'est changé quand le compte ne tombe pas juste : la page
va au rapport.

Corrections du texte (option --texte), faites sur le modèle des relectures déjà faites :
- mot coupé en fin de ligne avec un mot de l'apparat glissé entre les deux moitiés
  (« sei-Et gneurs », « déli-De vrance ») : mot recollé si le livre le connaît ailleurs, le mot
  glissé est rappelé dans la marque pour être remis dans l'apparat s'il y manque ;
- lettres mal lues dans un mot rare (« Picrrc », « Cliastel », « Ilarleston », « eflraé »,
  « grànt », « laquèlle ») quand une seule forme voisine est courante dans le livre
  (confusions c/e, li/h, Il/H, fl/ff, rn/m, cl/d, accent grave au milieu du mot).

Chaque changement est entouré d'une marque <span class="a-verifier" title="…"> comme celles
d'epub_review.py (retirées par epub_review.py --unmark) ; la marque est dans l'exposant pour
un appel. Le rapport HTML liste, page par page, ce qui reste incohérent (appel manquant,
numéro en trop, apparat sans numéro), avec un lien vers la page de la numérisation.

Usage :
  python3 epub_appels.py livre.epub --rapport appels.html                 # contrôle seul
  python3 epub_appels.py livre.epub -o livre-appels.epub --texte --rapport appels.html
  python3 epub_appels.py livre.epub -o … --texte --depuis-page 217        # texte : pages non relues
"""
import argparse
import collections
import html
import re
import unicodedata
import zipfile

MARK = '<span class="a-verifier" title="%s">%s</span>'
L = r"A-Za-zÀ-ÖØ-öø-ÿŒœÆæ"
WORD = re.compile(r"[%s]+" % L)
TAG = re.compile(r"(<[^>]+>)")
VARCALL = re.compile(r'<sup class="var">(?:<span class="a-verifier"[^>]*>)?(\d+)(?:</span>)?</sup>')

# signes où l'OCR a laissé un appel : collé en fin de mot, au début d'un mot, ou isolé
SIGNE = r"(?:['’`°*\"]+[0-9S°]{0,2}|1S|[0-9]{1,2})"
CANDS = [
    re.compile(r"(?<=[%s)])(%s)(?=[\s.,;:!?)»]|$)" % (L, SIGNE)),         # dire'  word6  dirés'°  dittes)2
    re.compile(r"(?<=[%s])([0-9]{1,2})(?=[a-zà-ÿ'])" % L),               # traittié3l'escuier
    re.compile(r"(?:(?<=\s)|^)([0-9]{1,2}|[\"°])(?=[a-zà-ÿ]{2,})"),         # 6word  "les
    re.compile(r"(?:(?<=\s)|^)(%s|U)(?=\s|[.,;:]|$)" % SIGNE),             # isolé : 1S  '°  6  U
    re.compile(r"(?<=[a-zà-ÿ,] )(Il)(?= [a-zà-ÿ])"),                        # pour Il aler
]


def reading(tok):
    t = tok.replace("’", "'")
    if t.isdigit():
        return int(t)
    return {"1S": 15, "'S": 15, "'8": 18, "'°": 10, "Il": 11, "'5": 15, "'6": 16, "'7": 17, "'9": 19}.get(t)


def var_numbers(t):
    """Numéros cités par l'apparat d'une page (intervalles développés)."""
    nums = []
    for m in re.finditer(r"(?:^|(?<=[\s.—]))(\d{1,2})(?:\s?[-–]\s?(\d{1,2}))?(?=[\s.,]|$)", t.strip()):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else None
        if b and a <= b <= a + 3:
            nums += list(range(a, b + 1))
        elif not b:
            nums.append(a)
    return nums


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def attr(s):
    return html.escape(s, quote=False).replace('"', "&quot;")


class Livre:
    def __init__(self, path):
        self.zin = zipfile.ZipFile(path)
        self.files = {n: self.zin.read(n) for n in self.zin.namelist()}
        self.textes = sorted(n for n in self.files if re.search(r"texte[^/]*\.x?html$", n))
        opf = next((self.files[n].decode("utf-8") for n in self.files if n.endswith(".opf")), "")
        m = re.search(r"<dc:source>(https?://gallica[^<]+)</dc:source>", opf)
        self.scan = (m.group(1).strip() + "/f%s.item") if m else None
        self.vocab = collections.Counter()
        for n in self.textes:
            for w in WORD.findall(strip(self.files[n].decode("utf-8"))):
                self.vocab[w] += 1
        self.offset = self.find_offset()
        self.mots = set()
        try:
            from epub_longs import load_wordlist
            self.mots = load_wordlist("auto") or set()       # « cris », « antre » : vrais mots, laissés
        except Exception:
            pass

    def find_offset(self):
        """Écart entre le numéro de l'ancre (vue de la numérisation) et la page imprimée."""
        c = collections.Counter()
        for n in self.textes:
            s = self.files[n].decode("utf-8")
            last = None
            for m in re.finditer(r'id="page-(\d+)"|<p class="variantes" title="p\. (\d+)"', s):
                if m.group(1):
                    last = int(m.group(1))
                elif last is not None:
                    c[last - int(m.group(2))] += 1
        # l'apparat suit le paragraphe où finit la page, qui a le plus souvent déjà ouvert la suivante :
        # l'écart le plus fréquent est d'une page de trop quand l'écart inférieur se voit aussi
        if not c:
            return 0
        mode = c.most_common(1)[0][0]
        return mode - 1 if c[mode - 1] * 20 >= c[mode] else mode

    def save(self, dst):
        zout = zipfile.ZipFile(dst, "w")
        for item in self.zin.infolist():
            zi = zipfile.ZipInfo(item.filename, item.date_time)
            zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zout.writestr(zi, self.files[item.filename])
        zout.close()


def segments(s):
    """Découpe en (index, texte, page imprimée brute, dans_apparat, modifiable) les nœuds texte."""
    parts = TAG.split(s)
    state = {"var": False, "sup": 0, "mark": 0, "page": None}
    info = []
    for i, p in enumerate(parts):
        if i % 2:
            m = re.search(r'id="page-(\d+)"', p)
            if m:
                state["page"] = int(m.group(1))
            if p.startswith('<p class="variantes"'):
                state["var"] = True
            elif p.startswith("</p") and state["var"]:
                state["var"] = False
            elif p.startswith("<sup"):
                state["sup"] += 1
            elif p.startswith("</sup"):
                state["sup"] -= 1
            elif p.startswith('<span class="a-verifier"'):
                state["mark"] += 1
            elif p.startswith("</span") and state["mark"]:
                state["mark"] -= 1
            info.append(None)
        else:
            info.append((state["page"], state["var"], state["sup"] == 0 and state["mark"] == 0))
    return parts, info


# --------------------------------------------------------------------------
# Corrections du texte
# --------------------------------------------------------------------------

CONFUSIONS = [("c", "e"), ("e", "c"), ("li", "h"), ("Il", "H"), ("fl", "ff"), ("rn", "m"), ("cl", "d"),
              ("ii", "ü"), ("n", "u"), ("u", "n"), ("b", "h"), ("ri", "n"), ("in", "m")]


def variantes_de(w):
    out = set()
    for a, b in CONFUSIONS:
        for m in re.finditer(re.escape(a), w):
            v = w[:m.start()] + b + w[m.end():]
            out.add(v)
            for a2, b2 in CONFUSIONS:                     # deux confusions (« Picrrc » → « Pierre »)
                for m2 in re.finditer(re.escape(a2), v):
                    if m2.start() >= m.start() + len(b) or m2.end() <= m.start():
                        out.add(v[:m2.start()] + b2 + v[m2.end():])
    out.discard(w)
    return out


def accent_interne(w):
    """Accent grave au milieu du mot (« grànt », « laquèlle ») : forme sans l'accent."""
    if not re.search(r"[àèùìò](?=[%s]{2})" % L, w) or re.search(r"[àèùìò]s?$", w):
        return None
    return re.sub(r"[àèùìò](?=[%s]{2})" % L, lambda m: unicodedata.normalize("NFD", m.group(0))[0], w)


def corrige_mot(livre, w):
    if len(w) < 4 or livre.vocab[w] > 2 or w.lower() in livre.mots:
        return None
    base = accent_interne(w)
    if base and livre.vocab[base] >= 3:
        return base
    best = [(livre.vocab[v], v) for v in variantes_de(w) if livre.vocab[v] >= 5]
    best.sort(reverse=True)
    if not best or (len(best) > 1 and best[1][0] * 4 > best[0][0]):
        return None
    if best[0][0] < 10 * max(1, livre.vocab[w]):
        return None
    return best[0][1]


# mot coupé en fin de page, un mot de l'apparat (bas de page) glissé avant l'ancre de la page suivante
JOIN = re.compile(r"(?<![%s'’-])([%s]{2,})-([A-ZÀ-Ý][^\s<]{0,15})\s*(<a id=\"page-(\d+)\" />)\s*([a-zà-ÿ][%s]*)"
                  % (L, L, L))


def texte(livre, depuis, journal):
    for n in livre.textes:
        s = livre.files[n].decode("utf-8")

        def join(m):
            a, ins, ancre, b = m.group(1), m.group(2), m.group(3), m.group(5)
            w = a + b
            page = int(m.group(4)) - livre.offset
            avant = s[:m.start()]
            if page < depuis or avant.rfind('<p class="variantes"') > avant.rfind("</p>") \
                    or livre.vocab[w] < 2 or livre.vocab[b] > 3 * livre.vocab[w]:
                return m.group(0)
            journal.append((page, "mot recollé", m.group(0).replace(ancre, " "), w))
            return ancre + MARK % (attr("Mot recollé, retiré : « %s » (à remettre dans l'apparat de la page "
                                        "précédente s'il y manque)" % html.unescape(ins)), w)
        s = JOIN.sub(join, s)
        parts, info = segments(s)
        for i, inf in enumerate(info):
            if not inf or not inf[2] or inf[1]:
                continue
            page = inf[0] - livre.offset if inf[0] is not None else 0
            if page < depuis:
                continue

            def lettre(m):
                w = m.group(0)
                c = corrige_mot(livre, w)
                if not c:
                    return w
                journal.append((page, "lettres", w, c))
                return MARK % (attr("Lu « %s »" % w), c)
            parts[i] = WORD.sub(lettre, parts[i])
        livre.files[n] = "".join(parts).encode("utf-8")


def collecte(livre):
    """Événements par page imprimée : appels connus et signes suspects, dans l'ordre."""
    ev = collections.defaultdict(list)
    var = collections.defaultdict(str)
    for n in livre.textes:
        s = livre.files[n].decode("utf-8")
        for m in re.finditer(r'<p class="variantes" title="p\. (\d+)">(.*?)</p>', s, re.S):
            var[int(m.group(1))] += " " + strip(m.group(2))
        parts, info = segments(s)
        for i, inf in enumerate(info):
            if inf is None:
                if parts[i] == '<sup class="var">':
                    k = i + 1
                    if not parts[k].strip() and k + 2 < len(parts) and parts[k + 1].startswith("<span"):
                        k += 2
                    pg = info[i + 1][0] if info[i + 1] else None
                    if parts[k].isdigit() and pg is not None:
                        ev[pg - livre.offset].append({"k": "appel", "v": int(parts[k]), "lu": parts[k], "f": n, "i": k})
                continue
            if inf[1] or not inf[2] or inf[0] is None:
                continue
            t = parts[i]
            found = []
            for rx in CANDS:
                for m in rx.finditer(t):
                    if not any(m.start(1) < e and s0 < m.end(1) for s0, e, _ in found):
                        found.append((m.start(1), m.end(1), m.group(1)))
            for s0, e, tok in sorted(found):
                ev[inf[0] - livre.offset].append({"k": "signe", "v": reading(tok), "tok": tok,
                                                  "f": n, "i": i, "s": s0, "e": e,
                                                  "ctx": html.unescape(t[max(0, s0 - 30):s0] + "⟦" + tok + "⟧" + t[e:e + 30])})
    return ev, var


def decide(evs, nvar):
    """Renvois (événement, numéro) à poser, et le diagnostic de la page."""
    actions = []
    appels = [e for e in evs if e["k"] == "appel"]
    # numéro faux entre deux justes, sans signe entre eux
    for j, e in enumerate(appels):
        prev = appels[j - 1]["v"] if j else 0
        nxt = appels[j + 1]["v"] if j + 1 < len(appels) else None
        if nxt is None or nxt != prev + 2 or e["v"] == prev + 1:
            continue
        a, b = evs.index(appels[j - 1]) if j else -1, evs.index(appels[j + 1])
        if any(x["k"] == "signe" for x in evs[a + 1:b]):
            continue
        actions.append((e, prev + 1, "renum"))
        e["v"] = prev + 1
    # trous entre appels connus
    bornes = [(-1, 0)] + [(evs.index(e), e["v"]) for e in appels]
    fin = max([nvar] + [e["v"] for e in appels]) if nvar else None
    if fin is not None:
        bornes.append((len(evs), fin + 1))
    for (ia, va), (ib, vb) in zip(bornes, bornes[1:]):
        if vb <= va:
            continue
        manque = list(range(va + 1, vb))
        signes = [x for x in evs[ia + 1:ib] if x["k"] == "signe"]
        if not manque or not signes:
            continue
        if len(signes) == len(manque) and all(x["v"] in (None, v) for x, v in zip(signes, manque)):
            actions += [(x, v, "signe") for x, v in zip(signes, manque)]
        else:
            lus = [x for x in signes if x["v"] in manque]
            vals = [x["v"] for x in lus]
            if lus and vals == sorted(set(vals)):
                actions += [(x, x["v"], "signe") for x in lus]
    # dernier trou quand l'apparat est muet : signes lus dans l'ordre à la suite
    if fin is None and appels:
        last = appels[-1]["v"]
        for x in evs[evs.index(appels[-1]) + 1:]:
            if x["k"] == "signe" and x["v"] == last + 1:
                actions.append((x, x["v"], "signe"))
                last += 1
    return actions


def appels(livre, journal):
    ev, var = collecte(livre)
    edits = collections.defaultdict(list)          # fichier → [(i, s, e, remplacement)]
    for page in sorted(ev):
        nv = var_numbers(var.get(page, ""))
        for e, v, why in decide(ev[page], max(nv) if nv else 0):
            if why == "renum":
                edits[e["f"]].append((e["i"], None, None, MARK % (attr("Appel renuméroté (lu « %s »)" % e["lu"]), v)))
                journal.append((page, "appel renuméroté", "", str(v)))
            else:
                rep = '<sup class="var">%s</sup>' % (MARK % (attr("Appel restitué (lu « %s »)" % e["tok"]), v))
                edits[e["f"]].append((e["i"], e["s"], e["e"], rep))
                journal.append((page, "appel restitué", e["ctx"], str(v)))
    for n, lst in edits.items():
        parts = TAG.split(livre.files[n].decode("utf-8"))
        for i, s0, e0, rep in sorted(lst, key=lambda x: (x[0], x[1] or 0), reverse=True):
            if s0 is None:
                parts[i] = rep
            else:
                t = parts[i]
                pre, post = t[:s0], t[e0:]
                # « 6word » → appel puis espace ; « word ' suite » : l'espace avant l'appel tombe
                if post[:1].isalpha():
                    post = " " + post
                if pre.endswith(" ") and not post[:1].isalpha():
                    pre = pre.rstrip(" ")
                parts[i] = pre + rep + post
        livre.files[n] = "".join(parts).encode("utf-8")


# --------------------------------------------------------------------------
# Apparat
# --------------------------------------------------------------------------

NUMV = re.compile(r"(?<![\w-])(\d{1,2})(?:\s?[-–]\s?(\d{1,2}))?(?![\w-])")
DEBUT = r"(?:^\s*|(?<=[.—)]\s))"
JUNK = re.compile(DEBUT + r"(U|H|[°'’`\"]{1,3}(?:[-–][°'’`\"\d]{1,2})?|\d[-–.]['’°`\"]|['’°`\".]\d{1,2}|\d[-–]\.?)"
                  r"(?=\s+[A-ZÀ-Ý])")
ESPACE = re.compile(DEBUT + r"(\d{1,2}) (\d{1,2})(?=\s+[A-ZÀ-Ý])")      # « 3 4 Des povres gens »


def apparat_bloc(t, appels_page, journal, page):
    """Numéros de l'apparat d'une page : séparateurs, numéros illisibles déduits des voisins."""
    def sep(m):
        b = m.group(2) or "11"
        if not 0 < int(b) - int(m.group(1)) <= 3:
            return m.group(0)
        rep = "%s-%s" % (m.group(1), b)
        journal.append((page, "apparat", m.group(0), rep))
        return MARK % (attr("Lu « %s »" % m.group(0)), rep)
    t = re.sub(r"(?<![\w-])(\d{1,2})(?:_(\d{1,2})|-1l)(?![\w-])", sep, t)

    def espace(m):
        a, b = int(m.group(1)), int(m.group(2))
        if b != a + 1:
            return m.group(0)
        journal.append((page, "apparat", m.group(0), "%d-%d" % (a, b)))
        return MARK % (attr("Lu « %s »" % m.group(0)), "%d-%d" % (a, b))
    t = ESPACE.sub(espace, t)
    # numéros illisibles
    toks = []
    for m in NUMV.finditer(t):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a <= b <= a + 3:
            toks.append((m.start(), m.end(), (a, b)))
    for m in JUNK.finditer(t):
        if not any(s0 <= m.start(1) < e0 for s0, e0, _ in toks):
            toks.append((m.start(1), m.end(1), None))
    toks.sort()
    if not any(v is None for _, _, v in toks):
        return t
    out, pos = [], 0
    for k, (s0, e0, v) in enumerate(toks):
        if v is not None:
            continue
        prev = next((toks[j][2][1] for j in range(k - 1, -1, -1) if toks[j][2]), 0)
        nxt = next((toks[j][2][0] for j in range(k + 1, len(toks)) if toks[j][2]), None)
        start = prev + 1
        if prev == 0 and re.search(r"\w", t[:s0]):
            continue                                  # du texte avant : bloc commencé sur l'autre page
        if nxt is None:                               # fin de bloc : intervalle, sauf si l'appel est le dernier
            nxt = start + 1 if appels_page and max(appels_page) == start else start + 2
        if nxt - start == 1:
            new = (start, start)
        elif nxt - start == 2:
            new = (start, start + 1)
        else:
            continue
        tok = t[s0:e0]
        d = re.match(r"\d+", tok)
        if d and int(d.group(0)) != start:
            continue
        toks[k] = (s0, e0, new)
        rep = str(new[0]) if new[0] == new[1] else "%d-%d" % new
        journal.append((page, "apparat", tok, rep))
        out.append(t[pos:s0])
        out.append(MARK % (attr("Numéro d'apparat restitué (lu « %s »)" % html.unescape(tok)), rep))
        pos = e0
    out.append(t[pos:])
    return "".join(out)


def apparat(livre, journal):
    ev, _ = collecte(livre)
    for n in livre.textes:
        s = livre.files[n].decode("utf-8")

        def blk(m):
            page = int(m.group(2))
            appels_page = {e["v"] for e in ev.get(page, []) if e["k"] == "appel"}
            parts = TAG.split(m.group(3))
            # le premier nœud texte seulement porte d'ordinaire tout l'apparat ; chacun est traité à part
            parts = [p if i % 2 else apparat_bloc(p, appels_page, journal, page) for i, p in enumerate(parts)]
            return m.group(1) + "".join(parts) + m.group(4)
        s = re.sub(r'(<p class="variantes" title="p\. (\d+)">)(.*?)(</p>)', blk, s, flags=re.S)
        livre.files[n] = s.encode("utf-8")


def diagnostic(livre):
    ev, var = collecte(livre)
    pages = sorted(set(ev) | set(var))
    rows = []
    for p in pages:
        c = [e["v"] for e in ev.get(p, []) if e["k"] == "appel"]
        sig = [e for e in ev.get(p, []) if e["k"] == "signe"]
        vt = var.get(p, "").strip()
        vn = sorted(set(var_numbers(vt)))
        pb = []
        if c != sorted(c) or len(set(c)) != len(c):
            pb.append("ordre")
        manque = sorted(set(range(1, max(c + vn + [0]) + 1)) - set(c))
        if manque:
            pb.append("appels manquants : " + ", ".join(map(str, manque)))
        trop = sorted(set(c) - set(vn))
        if trop and vt:
            pb.append("sans variante : " + ", ".join(map(str, trop)))
        if vt and not vn:
            pb.append("apparat sans numéro")
        elif vt and not re.match(r"\s*\d", vt):
            pb.append("début d'apparat sans numéro")
        if c and not vt:
            pb.append("apparat absent")
        if pb:
            rows.append((p, c, vn, pb, sig, vt))
    return pages, rows


def rapport(livre, path, journal, pages, rows):
    e = html.escape
    out = ['<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Appels de variantes</title>',
           "<style>body{font-family:serif;max-width:60em;margin:auto;padding:1em}td{vertical-align:top;"
           "padding:.2em .5em;border-bottom:1px solid #ccc}.v{font-size:90%;color:#444}.s{color:#a00}"
           "</style></head><body><h1>Appels de variantes</h1>",
           "<p>%d pages avec appels ou apparat ; %d à revoir. Écart ancre/page imprimée : %d.</p>"
           % (len(pages), len(rows), livre.offset)]
    if journal:
        c = collections.Counter(j[1] for j in journal)
        out.append("<p>Changements (marqués « a-verifier ») : %s.</p>"
                   % ", ".join("%s %d" % (k, v) for k, v in sorted(c.items())))
    tot, bad = collections.Counter(p // 50 for p in pages), collections.Counter(r[0] // 50 for r in rows)
    out.append("<p>Par tranche : %s.</p>" % " ; ".join("p. %d-%d : %d/%d" % (k * 50, k * 50 + 49, bad[k], tot[k])
                                                     for k in sorted(tot)))
    out.append("<p>Sur chaque page, les appels du texte doivent aller de 1 à N et l'apparat citer les mêmes "
               "numéros (« 1-2 » : appels 1 et 2). Le numéro de page mène à la vue de la numérisation. "
               "En rouge, les signes suspects restés dans le texte (appel probable que le compte n'a pas "
               "permis de numéroter).</p>")
    out.append("<table><tr><th>Page</th><th>Appels</th><th>Apparat</th><th>À voir</th></tr>")
    for p, c, vn, pb, sig, vt in rows:
        lien = e(str(p))
        if livre.scan:
            lien = '<a href="%s">%d</a>' % (e(livre.scan % (p + livre.offset)), p)
        s = "".join('<br><span class="s">signe « %s » : …%s…</span>' % (e(x["tok"]), e(x["ctx"])) for x in sig[:6])
        out.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s%s<br><span class="v">%s</span></td></tr>'
                   % (lien, " ".join(map(str, c)), " ".join(map(str, vn)), e(" ; ".join(pb)), s, e(vt[:300])))
    out.append("</table>")
    if journal:
        out.append("<h2>Changements</h2><table>")
        for p, k, a, b in journal:
            out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (p, e(k), e(a), e(b)))
        out.append("</table>")
    out.append("</body></html>")
    open(path, "w", encoding="utf-8").write("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description="Appels de variantes : contrôle par page et restitution.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB corrigé (sans -o : contrôle seul)")
    ap.add_argument("--rapport", help="rapport HTML")
    ap.add_argument("--texte", action="store_true", help="corrige aussi mots recollés et lettres mal lues")
    ap.add_argument("--depuis-page", type=int, default=0, help="--texte seulement à partir de cette page imprimée")
    ap.add_argument("--sans-appels", action="store_true", help="ne pas restituer les appels")
    o = ap.parse_args()
    livre = Livre(o.epub)
    journal = []
    if o.output:
        if o.texte:
            texte(livre, o.depuis_page, journal)
        if not o.sans_appels:
            appels(livre, journal)
            apparat(livre, journal)
        livre.save(o.output)
    pages, rows = diagnostic(livre)
    c = collections.Counter(j[1] for j in journal)
    print("Pages : %d, à revoir : %d%s" % (len(pages), len(rows),
          "".join(" ; %s : %d" % kv for kv in sorted(c.items()))))
    if o.rapport:
        rapport(livre, o.rapport, journal, pages, rows)


if __name__ == "__main__":
    main()
