#!/usr/bin/env python3
"""Contrôle et réparation d'un poème numéroté (pdf_vers.py, relu ou non) d'après le PDF Google Livres de la
même édition, avant les folios et la sortie Gutenberg :
  vers perdus   vers passés en tête d'une note de variantes (dernier vers de la page) : rendus au poème,
                après le vers qui les précède dans Google ;
  numéros       numéros de vers (tous les quatre vers) reposés d'après Google, recomptés entre deux
                repères quand le compte des vers s'accorde (« 14680 » mal lu pour 14620, numéro posé une
                ligne trop bas) ; les segments où le compte ne s'accorde pas (vers perdu, morceau de note
                parmi les vers) sont listés ;
  crochets      vers aux crochets de restitution abîmés (« [l'javez », « nejl] ») : texte de Google ;
  signes        vers terminés par deux signes (« le col. ; », « terre,, ») : signe final de Google ;
  dates         dates de manchette coupées (« (20 <manchette>oct. 1204)</manchette> ») ou restées dans le
                vers (« … torna, (29 octobre) ») : une manchette ;
  variantes     « ms. » mal lu (« MM. », « nM. », « w. ») ; note sans page (« title ») : page des voisines ;
  balisage      paragraphes vides, saut de ligne en fin de paragraphe, deux vers séparés par une ligne
                vide, marques de relecture restées.

  python3 epub_vers_controle.py t2.epub google-t2.pdf -o t2-c.epub --premier 10153 --dernier 19214
"""
import argparse
import bisect
import difflib
import html
import re
import zipfile

from epub_vers_reference import squelette

MOIS = r"(?:janv|févr|mars|avril|mai|juin|juil|août|sept|oct|nov|déc)[a-zé]*\.?"


def souple(a):
    """Motif exact ; une espace avant ; : ! ? » ou après « peut être insécable."""
    out = []
    for k, c in enumerate(a):
        prec = a[k - 1] if k else ""
        suiv = a[k + 1] if k + 1 < len(a) else ""
        if c in "  " and (prec == "«" or suiv in "»;:!?"):
            out.append("[  ]")
        else:
            out.append(re.escape(c))
    return "".join(out)


def vers_lignes(docs, ordre):
    """[(fichier, début, fin de la ligne dans le texte)] de tous les vers du poème, dans l'ordre."""
    out = []
    for n in ordre:
        t = docs[n]
        for m in re.finditer(r'<p class="vers[^"]*"[^>]*>(.*?)</p>', t, re.S):
            pos = m.start(1)
            for l in re.split(r"(<br\s*/>)", m.group(1)):
                if not l.startswith("<br"):
                    txt = html.unescape(re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>|<[^>]+>', "", l))
                    if txt.strip():
                        out.append((n, pos, pos + len(l), l))
                pos += len(l)
    return out


_CACHE = {}


def pages_google(pdf):
    """Lignes de chaque page du PDF (lues une fois)."""
    if pdf not in _CACHE:
        import pymupdf
        _CACHE[pdf] = [p.get_text().split("\n") for p in pymupdf.open(pdf)]
    return _CACHE[pdf]


def numeros_google(pdf, premier, dernier):
    """[(numéro, texte du vers)] : vers numérotés de la couche texte du PDF Google (pas les notes)."""
    import pymupdf
    out = []
    for p in pymupdf.open(pdf):
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                m = re.match(r"^(\d{1,5})\s+(\S.*)$", t)
                if m and premier <= int(m.group(1)) <= dernier and int(m.group(1)) % 4 == 0 \
                        and not re.search(r"\d|\bms\b|corr\.|Ibid|leçon| - ", m.group(2)):
                    out.append((int(m.group(1)), m.group(2)))
    # plus longue suite croissante : les numéros mal lus tombent
    best, prev = [], {}
    tails, idx = [], []
    for k, (v, _) in enumerate(out):
        j = bisect.bisect_left(tails, v)
        if j == len(tails):
            tails.append(v)
            idx.append(k)
        else:
            tails[j] = v
            idx[j] = k
        prev[k] = idx[j - 1] if j else None
    k = idx[-1] if idx else None
    while k is not None:
        best.append(out[k])
        k = prev[k]
    return best[::-1]


def lignes_google(pdf):
    """{squelette du vers : signe final} d'après toutes les lignes du PDF Google."""
    out = {}
    for lignes in pages_google(pdf):
        for line in lignes:
            t = re.sub(r"^\d{1,5}\s+", "", line.strip())
            m = re.search(r"([,;:.!?»]+)\s*$", t.replace(" ", ""))
            sq = squelette(t)
            if len(sq) >= 10:
                out.setdefault(sq, m.group(1) if m else "")
    return out


def texte_google(t):
    """Vers du PDF Google mis aux usages de l'EPUB (guillemets, espaces avant la ponctuation)."""
    t = re.sub(r"^\d{1,5}\s+", "", t.strip())
    t = re.sub(r"^(?:<<<?|«|<|c)\s*(?=[A-ZÀ-Ý&])", "« ", t)
    t = re.sub(r"\s*>>?\s*$", " »", t)
    t = re.sub(r"\s+([,.])", r"\1", t)
    t = re.sub(r"\s*([;:!?»])", "\u00a0\\1", t)
    t = re.sub(r"«\s*", "«\u00a0", t)
    t = re.sub(r"\[\s+", "[", re.sub(r"\s+\]", "]", t))
    t = re.sub(r"(\w) \[(\w{1,3})\](?=\w)", r"\1[\2]", t)             # « Pai [e]n » → « Pai[e]n »
    t = re.sub(r"(\w) \[([b-df-hj-np-tv-xz])\](?=[\s,.;:!?])", r"\1[\2]", t)   # « gran [t] peor »
    t = t.replace("[1]", "[l]")
    return re.sub(r"\s+", " ", t).strip()


def sans_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if not unicodedata.combining(c))


def crochets_locaux(t):
    """Crochets de restitution lus de travers, réparés sur place : « [l'javez » → « [l']avez »,
    « ffu] » → « [fu] », « Peitfi]ers » → « Peit[i]ers », « Se[ilnt » → « Se[i]nt », « [i|er » → « [i]er »."""
    t = re.sub(r"\[([^\[\]\s]{1,6}?)[jJ|](?=[\w'’ ,.;:!?]|$)", r"[\1]", t)
    t = re.sub(r"\[([^\[\]\s]{1,3}?)l(?=nt\b)", r"[\1]", t)
    t = re.sub(r"(?<![\w\[])f(f?[a-zé']{1,8})\](?!\])", r"[\1]", t)
    t = re.sub(r"(\w)f([a-zé]{1,3})\]", r"\1[\2]", t)
    return t


def crochets(docs, ordre, google):
    """Vers aux crochets de restitution abîmés : réparés sur place quand Google lit les mêmes lettres ; sinon
    texte de Google s'il est proche et garde les accents et le tiret de dialogue de l'EPUB ; sinon signalés."""
    gl = {}
    for lignes in pages_google(google):
        for line in lignes:
            t = texte_google(line)
            if len(squelette(t)) >= 8 and t.count("[") == t.count("]") and "[" in t:
                gl.setdefault(squelette(t), t)
    cles = list(gl)
    lettres = lambda t: sans_accents(re.sub(r"[^\w\[\]]", "", t.lower()))
    faits, restes = [], []
    for n, a, b, l in reversed(vers_lignes(docs, ordre)):
        spans = "".join(re.findall(r'\s*<span class="(?:numvers|manchette)">[^<]*</span>', l))
        ancre = "".join(re.findall(r'<a id="[^"]+"\s*/>', l))
        t = html.unescape(re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>|<[^>]+>', "", l)).strip()
        if t.count("[") == t.count("]") and not re.search(r"\[[^\]]*\[|\][^\[]*\]|\[\w*j\b|\wj\]", t):
            continue
        prop = difflib.get_close_matches(squelette(t), cles, n=1, cutoff=0.85)
        g = gl[prop[0]] if prop else None
        loc = crochets_locaux(t)
        if g and loc.count("[") == loc.count("]") and lettres(loc) == lettres(g):
            neuf = loc
        elif g and difflib.SequenceMatcher(None, squelette(t), prop[0]).ratio() >= 0.9 \
                and sum(1 for c in g if ord(c) > 127 and c.isalpha()) >= sum(1 for c in t if ord(c) > 127 and c.isalpha()):
            neuf = ("— " + g.lstrip("-— ") if t.startswith("—") else g)
        else:
            restes.append((t, g or ""))
            continue
        debut = re.match(r"^\s*", l).group(0)
        docs[n] = docs[n][:a] + debut + ancre + html.escape(neuf, quote=False) + spans + docs[n][b:]
        faits.append((t, neuf))
    return faits, restes


def doubles_signes(docs, ordre, google):
    """Vers terminés par deux signes (« le col. ; », « terre,, ») : le signe final du PDF Google ; « Mar. ; »
    (abréviation suivie d'un signe) est juste."""
    ref = lignes_google(google)
    n_ok = 0
    for i, (n, a, b, l) in reversed(list(enumerate(vers_lignes(docs, ordre)))):
        m = re.search(r"(?<!\bMar)(?<!\bRic)(?<!\bWill)(?<!\bJoh)([,;:.!?]) ?[\u00a0 ]?([,;:.!?])((?:\s*<span class=\"(?:numvers|manchette)\">[^<]*</span>)*\s*)$", l)
        if not m or m.group(1) + m.group(2) in ("?!", "!?"):
            continue
        txt = html.unescape(re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>|<[^>]+>', "", l))
        g = ref.get(squelette(txt))
        if g is None:                                   # vers absent de Google : le premier signe
            g = m.group(1)
        g = g[-1:] if g and g[-1] in ",;:.!?" else ""
        fin = ("\u00a0" + g if g in ";:!?" else g) if g else ""
        l2 = l[:m.start()] + fin + m.group(3)
        docs[n] = docs[n][:a] + l2 + docs[n][b:]
        n_ok += 1
    return n_ok


def numeros(docs, ordre, google, premier, dernier):
    """Numéros de vers reposés d'après le PDF Google : chaque vers numéroté de Google est retrouvé dans
    l'EPUB (dans l'ordre, par ressemblance des lettres) et reçoit son numéro ; les autres numéros sont
    retirés puis recomptés entre deux repères quand le compte des vers s'accorde. Renvoie les segments
    où le compte des vers ne s'accorde pas avec les numéros (vers perdu ou en trop)."""
    lignes = vers_lignes(docs, ordre)
    sq = [squelette(html.unescape(re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>|<[^>]+>', " ", l[3])))
          for l in lignes]
    reperes = {}                                        # n° de ligne → numéro imprimé
    pos = 0
    for v, t in numeros_google(google, premier, dernier):
        s0 = squelette(t)
        best, bi = 0, None
        for i in range(pos, min(len(lignes), pos + 400)):
            if abs(len(sq[i]) - len(s0)) > max(6, len(s0) // 3):
                continue
            r = difflib.SequenceMatcher(None, s0, sq[i], autojunk=False).ratio()
            if r > best:
                best, bi = r, i
                if r > 0.95:
                    break
        if bi is not None and best >= 0.8:
            reperes[bi] = v
            pos = bi + 1
    # numéros de l'EPUB gardés comme repères là où Google n'en donne pas, s'ils s'accordent au compte
    for i, l in enumerate(lignes):
        m = re.search(r'<span class="numvers">(\d+)</span>', l[3])
        if m and i not in reperes:
            reperes.setdefault(i, -int(m.group(1)))     # négatif : repère faible
    cles = sorted(reperes)
    forts = [(i, reperes[i]) for i in cles if reperes[i] > 0]
    nouveaux, ecarts = {}, []
    for (i0, v0), (i1, v1) in zip([(-1, premier - 1)] + forts, forts + [(len(lignes), None)]):
        if v1 is None:
            v1 = v0 + (i1 - i0)
        if v1 - v0 == i1 - i0:
            for k in range(i0 + 1, i1 + 1):
                if k < len(lignes) and (v0 + k - i0) % 4 == 0:
                    nouveaux[k] = v0 + k - i0
        else:
            if i0 >= 0:
                nouveaux[i0] = v0
            if i1 < len(lignes):
                nouveaux[i1] = v1
            for k in range(i0 + 1, i1):                 # numéros faibles de l'EPUB gardés tels quels
                if reperes.get(k, 0) < 0:
                    nouveaux[k] = -reperes[k]
            t = html.unescape(re.sub(r"<[^>]+>", "", lignes[i0 + 1][3] if i0 + 1 < len(lignes) else "")).strip()
            ecarts.append((v0, v1, i1 - i0, t[:50]))
    change = 0
    for i in range(len(lignes) - 1, -1, -1):
        n, a, b, l = lignes[i]
        l2 = re.sub(r'\s*<span class="numvers">\d+</span>', "", l)
        if i in nouveaux:
            l2 = l2.rstrip() + ' <span class="numvers">%d</span>' % nouveaux[i]
        if l2 != l:
            change += 1
            docs[n] = docs[n][:a] + l2 + docs[n][b:]
    return change, len([1 for v in reperes.values() if v > 0]), ecarts


def balisage(docs, poeme):
    """Marques de relecture restées, paragraphes vides, saut de ligne en fin de paragraphe, deux vers
    séparés par une ligne vide au lieu d'un <br />."""
    for n in docs:
        docs[n] = re.sub(r'<span title="[^"]*">(.*?)</span>', r"\1", docs[n], flags=re.S)
        docs[n] = re.sub(r"\s*<p>\s*</p>|\s*<p\s*/>", "", docs[n])
        docs[n] = re.sub(r"(?:<br\s*/>\s*)+(</p>)", r"\1", docs[n])
    for n in poeme:
        docs[n] = re.sub(r'(<p class="vers[^"]*"[^>]*>)(.*?)(</p>)',
                         lambda m: m.group(1) + re.sub(r"\s*\n\s*\n\s*", "<br />", m.group(2)) + m.group(3),
                         docs[n], flags=re.S)


def vers_des_variantes(docs, poeme, google):
    """Vers passés en tête d'une note de variantes (« Tant que Franceis s'en ennui[é]rent, (f 75 c) 11315
    rein. … ») : retrouvé dans Google, remis dans le poème après le vers qui le précède dans Google (ou
    seulement ôté de la note s'il est déjà dans le poème). Renvoie [(vers, état)]."""
    lignes_g = [texte_google(l) for page in pages_google(google) for l in page]
    sq_g = [squelette(l) for l in lignes_g]
    out = []
    for n in poeme:
        for m in reversed(list(re.finditer(r'(<p class="variantes"[^>]*>)(.*?)(</p>)', docs[n], re.S))):
            corps = m.group(2)
            d = re.match(r"\s*(?:a |« ?)?([A-ZÀ-Ý«][^<]*?)\s*(\((?:f\b|\d)[^)]*\)\s*)?(?=f?\d{3,5}\b)", corps) or \
                re.match(r"\s*\d{3,5}\s+([A-ZÀ-Ý«][^<\d]*?)\s*(\(f\b[^)]*\)\s*)(?=\d{3,5}\b)", corps)   # « 3616 Kar quant … (f. 24 d) »
            if not d or not re.search(r"[a-zà-ÿ]{3}", d.group(1)) or len(squelette(d.group(1))) < 10:
                continue
            vers = d.group(1).strip()
            man = (d.group(2) or "").strip()
            if re.search(r"\d|\bms\.|[Cc]orr\.|Ibid|leçon|lettre|écrit", vers) or len(vers) > 48:
                continue                                    # suite de note de la page précédente
            sv = squelette(vers)
            if any(squelette(html.unescape(re.sub(r"<[^>]+>", "", l[3]))).startswith(sv) for l in vers_lignes(docs, poeme)):
                etat = "déjà dans le poème"
            else:
                cand = [i for i, x in enumerate(sq_g) if x and abs(len(x) - len(sv)) < 8
                        and difflib.SequenceMatcher(None, sv, x).ratio() >= 0.85 and not re.search(r"\bms\b|\d{3}", lignes_g[i])]
                if len(cand) != 1:
                    out.append((vers, "introuvable dans Google"))
                    continue
                j = cand[0] - 1
                while j > 0 and (len(sq_g[j]) < 8 or lignes_g[j].isupper()):
                    j -= 1
                prec = sq_g[j]
                lv = vers_lignes(docs, poeme)
                ok = [x for x in lv if difflib.SequenceMatcher(
                    None, prec, squelette(html.unescape(re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>|<[^>]+>', "", x[3])))).ratio() >= 0.85]
                if len(ok) > 1:                                 # formule répétée : la plus proche avant la note
                    pos_note = m.start()
                    avant = [x for x in ok if x[0] == n and x[2] <= pos_note]
                    ok = [max(avant, key=lambda x: x[2])] if avant else ok
                if len(ok) != 1:
                    out.append((vers, "vers précédent introuvable"))
                    continue
                nn, a, b, l = ok[0]
                date = man if man and not re.match(r"\(f\b", man) and re.search(MOIS + r"|\d{4}", man) else ""
                ajout = "<br />" + html.escape(vers, quote=False) + (' <span class="manchette">%s</span>' % date if date else "")
                docs[nn] = docs[nn][:b] + ajout + docs[nn][b:]
                etat = "rendu au poème"
            t = docs[n]
            m2 = next(x for x in re.finditer(r'(<p class="variantes"[^>]*>)(.*?)(</p>)', t, re.S) if x.group(2) == corps)
            t = t[:m2.start(2)] + corps[d.end():] + t[m2.end(2):]
            docs[n] = t
            out.append((vers, etat))
    return out


def intrus(docs, poeme):
    """Lignes qui ne sont pas des vers parmi les vers : titre courant (« TOURNOI A EU. ») ôté ; morceau de
    note de variantes (numéro de vers, « ms. », « corr. », ligne trop longue) remis en tête de la note de
    variantes qui suit. Renvoie [(ligne, sort)]."""
    out = []
    for n in poeme:
        attente = []

        def para(m):
            if m.group(2) == "variantes":
                if attente:
                    x = m.group(1) + " ".join(attente) + " " + m.group(3) + m.group(4)
                    attente.clear()
                    return x
                return m.group(0)
            garde = []
            ancres = ""
            for l in re.split(r"<br\s*/>", m.group(3)):
                t = html.unescape(re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>|<[^>]+>', "", l)).strip()
                t2 = re.sub(r"^\d{1,5}\s*", "", t)                                   # numéro de vers resté
                t2 = re.sub(r"\([^()]*\)?|[\[{]\s*(?:f|if)\b[^\]]*\]?", "", t2)      # folio, date
                if re.fullmatch(r"[A-ZÀ-Ý' .,-]{6,}", t) and len(re.sub(r"\W", "", t)) >= 5:
                    out.append((t, "titre courant ôté"))
                    ancres += "".join(re.findall(r'<a id="[^"]+"\s*/>', l))
                    continue
                if re.search(r"(?<![\d(])\d{3,5}(?![\d)])|\bms\.|\bcorr\.|\bIbid\b|\bprem\. leçon|surcharg|grattage|"
                             r"douteu|\bécrit|corrig|\b[Ll]acune|\bpeut-être|résultat d'une|il est possible|"
                             r"enlumineur|capitale pour", t2) or len(t2) > 72:
                    out.append((t, "morceau de note remis dans les variantes"))
                    attente.append(re.sub(r'<span class="(?:numvers|manchette)">([^<]*)</span>', r"\1", l).strip())
                    continue
                garde.append(ancres + l if ancres else l)
                ancres = ""
            if ancres:
                garde.append(ancres) if not garde else None
            return m.group(1) + "<br />".join(garde) + m.group(4)
        docs[n] = re.sub(r'(<p class="(vers|variantes)[^"]*"[^>]*>)(.*?)(</p>)', para, docs[n], flags=re.S)
        if attente:
            out.append((" / ".join(attente), "morceau de note sans note qui suive : laissé"))
    return out


def dates(docs, poeme):
    """Dates de manchette coupées ou restées dans le vers : une manchette."""
    k = 0
    for n in poeme:
        docs[n], j = re.subn(r'\(([^()<>]{1,12}?)[\s\u00a0]*((?:<span class="numvers">\d+</span>[\s\u00a0]*)?)'
                             r'<span class="manchette">([^<()]*\))</span>',
                             lambda m: m.group(2) + '<span class="manchette">(%s %s</span>'
                             % (m.group(1).strip(), m.group(3).strip()), docs[n])
        k += j
        docs[n], j = re.subn(r'(\S)[\s\u00a0]+\(((?:\d{1,2}[\s\u00a0]?)?' + MOIS + r'(?:[\s\u00a0,]+\d{4})?[\s\u00a0]?\??|\d{4}'
                             r'(?:,[\s\u00a0]?(?:\d{1,2} )?' + MOIS + r')?)\)(?=\s*(?:<span class="numvers">\d+</span>)?\s*(?:<br\s*/>|</p>))',
                             lambda m: m.group(1) + ' <span class="manchette">(%s)</span>' % m.group(2), docs[n])
        k += j
    return k


def variantes(docs, poeme):
    """Notes de variantes : « ms. » mal lu ; note sans page (« title ») : page d'après les notes voisines
    (celle qui manque entre les deux, sinon celle de la note précédente). Renvoie (ms. rétablis, pages)."""
    ms_lus = sans_titre = 0
    for n in poeme:
        def var(m):
            nonlocal ms_lus
            x, k = re.subn(r"(?<=, )(?:MM|HM|nM|wM|WM|w|ws|tms|nas|nu|M|m|m<)\.(?= \S)", "ms.", m.group(2))
            ms_lus += k
            return m.group(1) + x + m.group(3)
        docs[n] = re.sub(r'(<p class="variantes"[^>]*>)(.*?)(</p>)', var, docs[n], flags=re.S)
        t = docs[n]
        ms = list(re.finditer(r'<p class="variantes"(?: title="p\. (\d+)")?>(.*?)</p>', t, re.S))
        for k in range(len(ms) - 1, -1, -1):
            m = ms[k]
            if m.group(1):
                continue
            prec = next((int(x.group(1)) for x in reversed(ms[:k]) if x.group(1)), None)
            suiv = next((int(x.group(1)) for x in ms[k + 1:] if x.group(1)), None)
            if prec is None and suiv is None:
                continue
            if prec is not None and suiv is not None and suiv == prec + 2:
                page = prec + 1
            else:
                page = prec if prec is not None else suiv
            t = t[:m.start()] + '<p class="variantes" title="p. %d">' % page + t[m.start() + len('<p class="variantes">'):]
            sans_titre += 1
        docs[n] = t
    return ms_lus, sans_titre


def lire_epub(path):
    zin = zipfile.ZipFile(path)
    opf = next(n for n in zin.namelist() if n.endswith(".opf"))
    o = zin.read(opf).decode("utf-8")
    base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
    hrefs = dict(re.findall(r'<item\b[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', o))
    hrefs.update({i: h for h, i in re.findall(r'<item\b[^>]*?href="([^"]+)"[^>]*?id="([^"]+)"', o)})
    ordre = [base + hrefs[i] for i in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', o) if i in hrefs]
    docs = {n: zin.read(n).decode("utf-8").replace("&#160;", "\u00a0") for n in ordre if n.endswith(".xhtml")}
    poeme = [n for n in ordre if n in docs and '<p class="vers' in docs[n] and "variantes" in docs[n]]
    return zin, docs, poeme


def ecrire_epub(zin, docs, path):
    zout = zipfile.ZipFile(path, "w")
    for item in zin.infolist():
        data = docs[item.filename].encode("utf-8") if item.filename in docs else zin.read(item.filename)
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()


def controle(docs, poeme, google, premier, dernier):
    """Toutes les réparations, dans l'ordre ; renvoie le compte rendu (lignes de texte)."""
    balisage(docs, poeme)
    rendus = vers_des_variantes(docs, poeme, google)
    hors = intrus(docs, poeme)
    nd = dates(docs, poeme)
    ms_lus, sans_titre = variantes(docs, poeme)
    faits, restes = crochets(docs, poeme, google)
    doubles = doubles_signes(docs, poeme, google)
    change, nrep, ecarts = numeros(docs, poeme, google, premier, dernier)
    out = ["Vers des notes de variantes : %d" % len(rendus)]
    out += ["  %s : %s" % (e, v) for v, e in rendus]
    out.append("Lignes étrangères parmi les vers : %d" % len(hors))
    out += ["  %s : %s" % (e, v) for v, e in hors]
    out.append("Dates en manchette : %d ; « ms. » rétablis : %d ; notes datées d'une page : %d ; doubles signes en "
               "fin de vers : %d" % (nd, ms_lus, sans_titre, doubles))
    out.append("Crochets de restitution réparés d'après Google : %d ; restés à voir : %d" % (len(faits), len(restes)))
    out += ["  %s  →  %s" % (a, b) for a, b in faits]
    out += ["  à voir : %s%s" % (a, "  (Google : %s)" % g if g else "") for a, g in restes]
    out.append("Numéros de vers : %d repères Google, %d lignes changées" % (nrep, change))
    out.append("Segments où le compte des vers ne s'accorde pas aux numéros : %d" % len(ecarts))
    out += ["  %d → %d : %d lignes au lieu de %d (%s…)" % (v0, v1, n, v1 - v0, t) for v0, v1, n, t in ecarts]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("google", help="PDF Google Livres (couche texte) de la même édition")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--premier", type=int, default=1, help="numéro du premier vers")
    ap.add_argument("--dernier", type=int, default=99999, help="numéro du dernier vers")
    opts = ap.parse_args()
    zin, docs, poeme = lire_epub(opts.epub)
    print("\n".join(controle(docs, poeme, opts.google, opts.premier, opts.dernier)))
    ecrire_epub(zin, docs, opts.output)


if __name__ == "__main__":
    main()
