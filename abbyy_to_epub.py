#!/usr/bin/env python3
"""XML ABBYY d'Internet Archive (<livre>_abbyy.gz) → EPUB brut pour Prescel, pour la prose savante :
paragraphes, notes de bas de page reliées à leurs appels, italique, citations en vers, titres.

Le PDF « texte » d'Internet Archive place chaque mot à part (justification) et se lit mal ; le XML ABBYY
garde les paragraphes, les lignes, la taille et le style de chaque caractère et sa position :
  - titre courant (première ligne, en haut de page) : retiré ; ancre « page-N » posée à sa place ;
  - notes : paragraphes en corps plus petit que le texte, en bas de page, « 1. … » ; une note sans
    numéro en haut de la zone des notes continue la dernière note de la page précédente ;
  - appels de note : caractères surélevés collés à la fin d'un mot (ABBYY les lit souvent « < », « ^ »,
    « * ») ; le n-ième appel de la page renvoie à la n-ième note ; un écart est repéré a-verifier ;
  - citations en vers : lignes courtes nettement en retrait ; numéro de vers en tête → numvers ;
  - titres : paragraphe court sans minuscules (« II. JEAN D'ERLÉE. ») ;
  - paragraphe coupé par la page (pas de retrait de première ligne) : recollé ; mots coupés en fin de
    ligne : recollés (le trait d'union est gardé si la forme avec trait d'union est la plus fréquente).

Un fichier .djvu est lu par sa couche texte (djvused : lignes et mots avec leurs coordonnées, sans
styles) : corps des notes d'après l'interligne, plus serré (coupure d'Otsu page par page, contrôlée
par l'interligne du texte des pages voisines) ; appels = chiffres collés à un mot ou surélevés ;
titre courant, taches et signatures d'imprimerie écartés ; plusieurs notes lues sur une même ligne
séparées. Drapeaux de partie : sans-notes, index (table en retrait suspendu, deux colonnes coupées à
la gouttière), tableau (chronologie sur deux colonnes : colonne de gauche puis de droite, une ligne
par case).

  python3 abbyy_to_epub.py livre_abbyy.gz -o livre.epub --titre "…" --auteur "…" \\
      --pagination 16=1,320=i,441=cxlii --parties "12-14:Titre,320-443:Introduction,16-284:Traduction"
"""
import argparse
import collections
import gzip
import html
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml}"


# ---------------------------------------------------------------- lecture du XML
def lire(path):
    pages = []
    for ev, el in ET.iterparse(gzip.open(path, "rb"), events=("end",)):
        if el.tag != NS + "page":
            continue
        pg = {"w": int(el.get("width")), "h": int(el.get("height")), "pars": []}
        for b in el.findall(NS + "block"):
            if b.get("blockType") != "Text":
                continue
            for par in b.iter(NS + "par"):
                p = {"attr": dict(par.attrib), "lines": []}
                for line in par.findall(NS + "line"):
                    chars = []
                    for fm in line.findall(NS + "formatting"):
                        fs = float(fm.get("fs", "0").rstrip(".") or 0)
                        it, bd = fm.get("italic") == "true", fm.get("bold") == "true"
                        for c in fm.findall(NS + "charParams"):
                            chars.append((c.text or " ", int(c.get("l")), int(c.get("t")), int(c.get("r")),
                                          int(c.get("b")), fs, it, bd))
                    if chars:
                        p["lines"].append({"box": tuple(int(line.get(k)) for k in "ltrb"),
                                           "base": int(line.get("baseline")), "chars": chars})
                if p["lines"]:
                    pg["pars"].append(p)
        pages.append(pg)
        el.clear()
    return pages


def lire_djvu(path):
    """Couche texte d'un DjVu (lignes et mots avec leurs coordonnées) → même structure que le XML ABBYY.
    Pas de styles ni de tailles : la taille se déduit de la hauteur des mots de la ligne (texte 10, notes
    plus petites) ; les chiffres collés à la fin d'un mot (« Winchester1. ») sont des appels de note et
    sont placés en exposant."""
    import subprocess
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp:                # djvused n'aime pas les noms accentués
        lien = os.path.join(tmp, "livre.djvu")
        os.symlink(os.path.abspath(path), lien)
        lisp = subprocess.run(["djvused", "-u", "-e", "print-txt", lien], capture_output=True,
                              check=True).stdout.decode("utf-8", "replace")
    pages = []
    hauteurs = []
    brut = []
    for bloc in re.split(r"^\(page ", lisp, flags=re.M)[1:]:
        dims = [int(x) for x in bloc.split(None, 4)[:4]]
        H, W = dims[3], dims[2]
        lignes = []
        for m in re.finditer(r"\(line (\d+) (\d+) (\d+) (\d+)((?:\s*\(word [^\n]*)+)", bloc):
            ws = [(int(a), H - int(d), int(c), H - int(b), w.encode("latin-1", "backslashreplace").decode("unicode_escape")
                   if "\\" in w else w)
                  for a, b, c, d, w in re.findall(r'\(word (\d+) (\d+) (\d+) (\d+) "((?:[^"\\]|\\.)*)"\)', m.group(5))]
            if not ws:
                continue
            h = sorted(w[3] - w[1] for w in ws)[len(ws) // 2]
            hauteurs.append(h)
            lignes.append((ws, h))
        # mots d'une même rangée (titre courant en trois morceaux, colonnes d'un tableau) : une seule ligne
        # les lignes minuscules (« l », « ' », « y » descendus, numéro de page) sont rattachées ensuite à la
        # rangée qu'elles recouvrent le plus, sans en élargir l'emprise (sinon deux lignes se fondent)
        rangs = []                                          # [mots, hauteur, haut, bas]
        grandes = [x for x in lignes if sum(len(w[4]) for w in x[0]) > 3]
        petites_l = [x for x in lignes if sum(len(w[4]) for w in x[0]) <= 3]
        for ws, h in sorted(grandes, key=lambda x: min(w[1] for w in x[0])):
            t0, b0 = min(w[1] for w in ws), max(w[3] for w in ws)
            if rangs:
                rt, rb = rangs[-1][2], rangs[-1][3]
                if min(b0, rb) - max(t0, rt) > 0.4 * min(b0 - t0, rb - rt):
                    rangs[-1] = [rangs[-1][0] + ws, max(h, rangs[-1][1]), min(t0, rt), max(b0, rb)]
                    continue
            rangs.append([list(ws), h, t0, b0])
        for ws, h in petites_l:
            t0, b0 = min(w[1] for w in ws), max(w[3] for w in ws)
            best = max(rangs, key=lambda r: min(b0, r[3]) - max(t0, r[2]), default=None)
            if best and min(b0, best[3]) - max(t0, best[2]) > -0.3 * (best[3] - best[2]):
                best[0] += ws
            else:
                rangs.append([list(ws), h, t0, b0])
        rangs = [(sorted(r[0]), r[1]) for r in sorted(rangs, key=lambda r: r[2])]
        # taches au-dessus du titre courant (« I », « . ») : écartées
        while len(rangs) > 1 and len("".join(w[4] for w in rangs[0][0])) <= 2 \
                and not re.fullmatch(r"\d+", "".join(w[4] for w in rangs[0][0])):
            rangs.pop(0)
        # signature d'imprimerie au pied de la page (« m3 », « m /i ») : écartée
        while len(rangs) > 1:
            t = "".join(w[4] for w in rangs[-1][0])
            if len(t) <= 5 and not re.search(r"[A-Za-zÀ-ÿ]{3}", t) and min(w[1] for w in rangs[-1][0]) > 0.85 * H:
                rangs.pop()
            else:
                break
        brut.append((W, H, rangs))
    # interligne du texte courant, page par page : 85e centile des écarts entre lignes, lissé sur 7 pages
    # (l'introduction est imprimée plus gros que la traduction ; une page de notes n'a guère de texte).
    # Les notes, en plus petit corps, ont un interligne plus serré : c'est l'indice le plus stable.
    def ecarts(lignes):
        """Écart entre la ligne de base d'une ligne et celle de la suivante (de la précédente pour la
        dernière) ; la ligne de base (bas des mots, médiane) varie moins que le haut des mots."""
        bases = [sorted(w[3] for w in ws)[len(ws) // 2] for ws, h in lignes]
        out = []
        for k in range(len(bases)):
            e = None
            for j in (k + 1, k - 1):
                if 0 <= j < len(bases) and 15 < abs(bases[j] - bases[k]) < 150:
                    e = abs(bases[j] - bases[k])
                    break
            out.append(e)
        return out
    def seuil(es):
        """Coupure la plus nette entre écarts serrés (notes) et larges (texte), ou None."""
        es = sorted(x for x in es if x)
        if len(es) < 5:
            return None
        med = es[len(es) // 2]
        es = [x for x in es if 0.6 * med <= x <= 1.45 * med]         # ni grands blancs ni lignes collées
        best = None                                         # méthode d'Otsu : séparation maximale des deux groupes
        for i in range(2, len(es) - 1):
            lo, hi = es[:i], es[i:]
            ml, mh = sum(lo) / len(lo), sum(hi) / len(hi)
            score = len(lo) * len(hi) * (mh - ml) ** 2
            if best is None or score > best[0]:
                best = (score, (es[i - 1] + es[i]) / 2, ml / mh, es[i] - es[i - 1])
        return (best[1], best[2] * 1.0) if best and best[2] < 0.87 and best[3] >= 2 else None
    # interligne du texte de la région (90e centile des médianes des pages, sur ±6 pages) : une
    # coupure dont le groupe serré n'est pas nettement plus serré que le texte sépare deux sortes de lignes
    # de texte, pas le texte et les notes (page sans notes, ou entièrement en notes)
    def centile(es, q):
        es = sorted(x for x in es if x)
        return es[int(len(es) * q)] if es else None
    meds = [centile(ecarts(lignes), 0.5) for W, H, lignes in brut]
    ref = []
    for k in range(len(brut)):
        v = sorted(x for x in meds[max(0, k - 6):k + 7] if x)
        ref.append(v[int(len(v) * 0.9)] if v else 0)
    propres = []
    for k, (W, H, lignes) in enumerate(brut):
        r = seuil(ecarts(lignes))
        if r and ref[k]:
            lo = [x for x in ecarts(lignes) if x and x < r[0]]
            if lo and sum(lo) / len(lo) > 0.88 * ref[k]:
                r = None
        propres.append(r[0] if r else None)
    seuils = []
    for k in range(len(brut)):
        if propres[k]:
            seuils.append(propres[k])
        elif ref[k] and sum(1 for x in ecarts(brut[k][2]) if x and x < 0.85 * ref[k]) <= 2:
            seuils.append(0)                                   # page de texte sans notes
        else:
            voisins = sorted(x for x in propres[max(0, k - 4):k + 5] if x)
            seuils.append(voisins[len(voisins) // 2] if voisins else 0)
    qh = []
    for W, H, lignes in brut:
        hs = sorted(h for ws, h in lignes if len(ws) >= 5)
        qh.append(hs[int(len(hs) * 0.85)] if hs else 25)
    for (W, H, lignes), thr, href in zip(brut, seuils, qh):
        ec = ecarts(lignes)
        pg = {"w": W, "h": H, "pars": []}
        # une ligne d'un ou deux mots (« [12828]. ») a une ligne de base peu sûre : elle ne vote pas
        brutes = [None if e is None or len(ws) < 3 else (e < thr) for e, (ws, h) in zip(ec, lignes)]
        petites = []
        for k in range(len(brutes)):                               # lissage : majorité sur 5 lignes
            v = [x for x in brutes[max(0, k - 2):k + 3] if x is not None]
            petites.append(sum(v) > len(v) / 2 if v else False)
            if thr and ec[k] and ec[k] > 1.6 * thr and k + 1 < len(lignes):
                petites[-1] = False                                # suivie d'un grand blanc : fin du texte
        for (ws, h), e, pt in zip(lignes, ec, petites):
            if h > 1.35 * href:
                fs = 14.0                                          # titre
            elif e is not None:                                    # notes : interligne serré
                fs = 8.5 if pt else 10.0
            else:
                fs = 8.5 if h < 0.9 * href else 10.0
            base = sorted(w[3] for w in ws)[len(ws) // 2]
            chars = []
            for k, (l, t, r, b, w) in enumerate(ws):
                if k:
                    chars.append((" ", chars[-1][3], t, l, b, fs, False, False))
                m = re.match(r"^(.*[A-Za-zÀ-ÿ\])»])(\d{1,2})([.,;:!?»)\]]*)$", w)
                appel = m and (not re.fullmatch(r"[\d\W]*", m.group(1)) or m.group(1)[-1] in ")]»") \
                    and int(m.group(2)) <= 20
                seul = re.match(r"^()(\d{1,2})([.,;:!?»)]*)$", w)        # « Ludgershall 1. » : chiffre surélevé à part
                if not appel and seul and k and re.search(r"[A-Za-zÀ-ÿ\])»]$", ws[k - 1][4]) \
                        and (b < base - 0.2 * h or (len(seul.group(2)) == 1 and seul.group(3)[:1] in ".,;:")) \
                        and not re.fullmatch(r"le|la|les|du|au|aux|de|des|et|ou|à|en|sur|vers|depuis|jusqu'au",
                                             ws[k - 1][4]) \
                        and not re.fullmatch(r"(?i)(p|t|v|vv|n|no|n°|ch|chap|col|fol|f|l|liv|an|en|note|notes|ligne|"
                                             r"lignes|vers|page|pages|art|§|livre|tome|chant|ms|mss|janv|févr|fév|mars|avril|mai|juin|juill|juil|"
                                             r"août|sept|oct|nov|déc|—|-)\.?,?", ws[k - 1][4]) \
                        and int(seul.group(2)) <= 20:
                    m, appel = seul, True
                    if chars and chars[-1][0] == " ":
                        chars.pop()                               # l'appel se colle au mot qui le précède
                corps = m.group(1) + m.group(3) if appel else w
                pas = (r - l) / max(1, len(w))
                x = l
                for c in (m.group(1) if appel else w):            # hauteur de la ligne : pas de faux exposant
                    chars.append((c, int(x), int(base - h), int(x + pas), base, fs, False, False))
                    x += pas
                if appel:
                    for c in m.group(2):
                        chars.append((c, int(x), int(base - h), int(x + pas), int(base - 0.6 * h), fs, False, False))
                        x += pas
                    for c in m.group(3):
                        chars.append((c, int(x), int(base - h), int(x + pas), base, fs, False, False))
                        x += pas
                del corps
            box = (min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws))
            if not pg["pars"]:
                pg["pars"].append({"attr": {}, "lines": []})
            pg["pars"][0]["lines"].append({"box": box, "base": base, "chars": chars, "djvu": True})
        pages.append(pg)
    return pages


# ---------------------------------------------------------------- pagination
ROM = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
       (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]


def romain(n):
    out = ""
    for v, s in ROM:
        while n >= v:
            out += s
            n -= v
    return out


def de_romain(s):
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    n, prev = 0, 0
    for ch in reversed(s.lower()):
        v = vals[ch]
        n += -v if v < prev else v
        prev = max(prev, v)
    return n


def etiquettes(spec, n):
    """« 16=1,320=i » → {vue: étiquette} ; on compte à partir de chaque point de départ."""
    lab = {}
    pts = []
    for item in filter(None, (spec or "").split(",")):
        v, e = item.split("=")
        pts.append((int(v), e))
    pts.sort()
    for k, (v, e) in enumerate(pts):
        fin = pts[k + 1][0] if k + 1 < len(pts) else n
        for i in range(v, fin):
            lab[i] = romain(de_romain(e) + i - v) if re.fullmatch(r"[ivxlcdm]+", e) else str(int(e) + i - v)
    return lab


# ---------------------------------------------------------------- analyse d'une page
def texte_ligne(line):
    return "".join(c[0] for c in line["chars"])


def fs_mode(par):
    c = collections.Counter()
    for l in par["lines"]:
        for ch in l["chars"]:
            if ch[0].strip():
                c[ch[5]] += 1
    return c.most_common(1)[0][0] if c else 0


ORDINAUX = {"e", "er", "re", "me", "es", "o", "°", "os", "a", "r", "s", "d", "t", "bis"}


def appels(line):
    """Indices [(début, fin)] des groupes de caractères surélevés qui sont des appels de note."""
    ch = line["chars"]
    base = line["base"]
    corps = [c for c in ch if c[0].isalpha() and c[0].islower() and c[0] not in "bdfhklt'’gjpqy"]
    if not corps:
        return []
    xh = sorted(c[4] - c[2] for c in corps)[len(corps) // 2]          # hauteur d'x médiane
    haut = [c[0].strip() and c[0] not in "-—–_.,:;" and c[4] < base - 0.45 * xh and (c[4] - c[2]) < 1.15 * xh
            for c in ch]
    # signes qu'ABBYY met à la place d'un chiffre en exposant, même peu surélevés : « osl^ », « Jean* »
    for k, c in enumerate(ch):
        if line.get("djvu"):                                   # DjVu : les appels sont déjà placés en exposant
            break
        if c[0] in "^*<»'’\"" and k and (ch[k - 1][0].isalpha() or ch[k - 1][0] == " " and k >= 2
                                           and ch[k - 2][0] in "])" and c[0] in "^*<") \
                and (k + 1 == len(ch) or not ch[k + 1][0].isalpha()) \
                and (c[0] not in "»" or c[4] < base - 0.3 * xh):
            haut[k] = True
    out, i = [], 0
    while i < len(ch):
        if not line.get("djvu") and ch[i][0] == "P" and i >= 2 and ch[i - 1][0] in "el" and ch[i - 2][0].isalpha() and ch[i - 2][0].islower() \
                and (i + 1 == len(ch) or not ch[i + 1][0].isalpha()):
            out.append((i, i + 1, "l"))                        # « WherwelP » : « l » + appel fondus
            i += 1
            continue
        if haut[i]:
            j = i
            while j + 1 < len(ch) and haut[j + 1]:
                j += 1
            grp = "".join(c[0] for c in ch[i:j + 1])
            avant = ch[i - 1][0] if i else " "
            if avant == " " and i >= 2 and ch[i - 2][0].strip() and (ch[i][1] - ch[i - 2][3] < 0.6 * xh
                                                                    or ch[i - 2][0] in "])"):
                avant = ch[i - 2][0]                           # espace étroite avant l'appel : « Winchester < »
            mot = re.search(r"(\S*)$", "".join(c[0] for c in ch[:i])).group(1)
            apres = ch[j + 1][0] if j + 1 < len(ch) else " "
            if avant.strip() and not apres.isalpha() \
                    and grp.lower() not in ORDINAUX and not (avant.isdigit() and grp.isalpha()) \
                    and not avant.isdigit() and not re.fullmatch(r"[ivxlcIVXLC]+", mot) and len(grp) <= 3:
                out.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return out


def rendre_ligne(line, calls):
    """Texte HTML de la ligne : italique, appels remplacés par \x00 (numérotés plus tard)."""
    ch = line["chars"]
    skip = set()
    pos = {}
    for c in calls:
        a, b = c[0], c[1]
        lu = html.escape("".join(x[0] for x in ch[a:b]), quote=False)
        pos[a] = (c[2] if len(c) > 2 else "") + "\x00" + lu + "\x03"
        skip.update(range(a, b))
    out, it = [], False
    for k, c in enumerate(ch):
        if k in pos:
            if it:
                out.append("</i>")
                it = False
            out.append(pos[k])
        if k in skip:
            continue
        if c[6] and c[0].strip() and not it:
            out.append("<i>")
            it = True
        elif not c[6] and c[0].strip() and it:
            out.append("</i>")
            it = False
        out.append(html.escape(c[0], quote=False))
    if it:
        out.append("</i>")
    s = "".join(out)
    return re.sub(r"</i>(\s*)<i>", r"\1", s)


class Livre:
    def __init__(self, pages, labels, opts):
        self.pages = pages
        self.labels = labels
        self.o = opts
        self.blocs = []           # {"type": p|vers|h1|h2|note, "html": …, "page": étiquette}
        self.notes_ouvertes = None
        self.stats = collections.Counter()
        self.mots = collections.Counter()

    @staticmethod
    def gouttiere(ls):
        """Abscisse (en dizaines de points) du bord gauche de la seconde colonne d'un tableau, ou None : là
        où commencent le plus de mots dans le milieu de la page (les renvois, alignés à droite, sont épars)."""
        if not ls:
            return None
        x0 = min(l["box"][0] for l in ls)
        x1 = max(l["box"][2] for l in ls)
        debuts = collections.Counter()
        for l in ls:
            for k, c in enumerate(l["chars"]):
                if c[0].strip() and (k == 0 or not l["chars"][k - 1][0].strip()):
                    debuts[int(c[1]) // 10] += 1
        zone = [x for x in range(int(x0 + 0.35 * (x1 - x0)) // 10, int(x0 + 0.7 * (x1 - x0)) // 10)]
        if not zone:
            return None
        pic = max(zone, key=lambda x: debuts[x] + debuts[x + 1])
        if debuts[pic] + debuts[pic + 1] < 4:
            return None
        bord = min(x for x in range(pic - 6, pic + 1) if debuts[x] + debuts[x + 1] >= 0.4 * (debuts[pic] + debuts[pic + 1]))
        return bord - 1

    @classmethod
    def deux_colonnes(cls, ls, g):
        """Vrai si la plupart des lignes longues ont un blanc de gouttière (≥ 45 points ; entre deux mots justifiés, 35 au plus) près de g."""
        if g is None:
            return False
        longues = [l for l in ls if l["box"][2] > g * 10 + 60 and l["box"][0] < g * 10 - 160]
        if len(longues) < 5:
            return False
        ok = 0
        for l in longues:
            k = cls.couper(l, g)
            ch = l["chars"]
            if 0 < k < len(ch):
                fin = max((c[3] for c in ch[:k] if c[0].strip()), default=0)
                ok += ch[k][1] - fin >= 45
        return ok >= 0.6 * len(longues)

    @staticmethod
    def couper(l, g):
        """Index du premier caractère de la colonne de droite dans la ligne l : le plus grand blanc entre
        deux mots près de la gouttière g (un peu à gauche : mois et jour précèdent le bord repéré)."""
        ch = l["chars"]
        mots = []
        for k, c in enumerate(ch):
            if c[0].strip() and (k == 0 or not ch[k - 1][0].strip()):
                mots.append(k)
        best = None
        if max((c[3] for c in ch if c[0].strip()), default=0) < g * 10 + 60:
            return len(ch)                                  # rien dans la colonne de droite
        for a, b in zip(mots, mots[1:]):
            fin = max(c[3] for c in ch[a:b] if c[0].strip())
            debut = ch[b][1]
            if debut >= g * 10 - 160 and fin <= g * 10 + 40:
                if best is None or debut - fin > best[0]:
                    best = (debut - fin, b)
        if best:
            return best[1]
        return next((k for k in mots if (ch[k][1] + ch[k][3]) / 2 >= g * 10), len(ch))

    def gauche(self, pg, pars):
        xs = sorted(l["box"][0] for p in pars for l in p["lines"])
        return xs[len(xs) // 10] if xs else 0

    def page(self, i):
        pg = self.pages[i]
        pars = list(pg["pars"])
        lab = self.labels.get(i, str(i))
        if not pars:
            return
        # titre courant : une ligne en haut de page (même si ABBYY ne la met pas en premier)
        tops = sorted(l["box"][1] for p in pars for l in p["lines"])
        ecarts = sorted(b - a for a, b in zip(tops, tops[1:]) if b - a > 5)
        pas = ecarts[len(ecarts) // 2] if ecarts else 0
        l0 = pars[0]["lines"][0]
        t0 = texte_ligne(l0).strip()
        suivant = next((y for y in tops if y > l0["box"][1] + 5), None)
        lettres = re.sub(r"[^A-Za-zÀ-ÿ]", "", re.sub(r"(?:^|\s)[ivxlcm]+\.?(?=\s|$)", " ", t0))   # sans le folio
        capitales = lettres and sum(c.isupper() for c in lettres) > 0.6 * len(lettres)
        numero = re.search(r"^(?:\d{1,3}\]?|[IVXLCivxlcmJl1]{1,7}\.?)\s|\s(?:\[?\d{1,4}(?:-\d)?|[IVXLCivxlcmJl1]{1,7})$", t0)
        if len(t0) < 90 and (l0["box"][1] < (0.155 if l0.get("djvu") else 0.12) * pg["h"]
                             or (suivant and pas and suivant - l0["box"][1] > 1.3 * pas
                                 and re.search(r"^\S{1,8}\s|\s\S{1,8}$", t0))
                             or (capitales and numero)):
            if len(pars[0]["lines"]) == 1:
                pars = pars[1:]
            else:
                pars = [{"attr": pars[0]["attr"], "lines": pars[0]["lines"][1:]}] + pars[1:]
            self.stats["titres courants"] += 1
        if not pars:
            return
        # corps du texte de la page : la plus grande taille qui fait au moins 3 % des caractères (le texte est
        # plus gros que les notes) ; ABBYY n'annonce pas la même taille d'une page à l'autre
        fsc = collections.Counter()
        for p in pars:
            for l in p["lines"]:
                for c in l["chars"]:
                    if c[0].strip():
                        fsc[c[5]] += 1
        tot = sum(fsc.values())
        grands = [f for f, n in fsc.items() if n >= 0.03 * tot and f < 14]
        corps = max(grands) if grands else self.corps
        left = self.gauche(pg, pars)
        larg = max(l["box"][2] for p in pars for l in p["lines"]) - left
        notes, corps_pars = [], []
        # début de la zone des notes : première ligne « 1. » de la moitié basse précédée d'un blanc, ou
        # première ligne en petit corps de la moitié basse ; tout ce qui suit sur la page est note
        toutes = [(k, l) for k, p in enumerate(pars) for l in p["lines"]]
        pas = sorted(b[1]["box"][1] - a[1]["box"][1] for a, b in zip(toutes, toutes[1:])
                     if 0 < b[1]["box"][1] - a[1]["box"][1] < 200)
        pas = pas[len(pas) // 2] if pas else 90
        debut = None
        for n, (k, l) in enumerate([] if getattr(self, "sans_notes", False) else toutes):
            if l["box"][1] < 0.15 * pg["h"]:
                continue
            t = texte_ligne(l).strip()
            fsl = collections.Counter(c[5] for c in l["chars"] if c[0].strip()).most_common(1)
            petit = fsl and fsl[0][0] < corps - 0.5
            blanc = n and l["box"][1] - toutes[n - 1][1]["box"][1] > 1.2 * pas
            xs = [x[1]["box"] for x in toutes]
            gauche_p = sorted(bx[0] for bx in xs)[len(xs) // 10]
            droite_p = sorted(bx[2] for bx in xs)[int(len(xs) * 0.97)]
            centree = abs((l["box"][0] + l["box"][2]) / 2 - (gauche_p + droite_p) / 2) < 0.05 * (droite_p - gauche_p) \
                and l["box"][0] - gauche_p > 60 and droite_p - l["box"][2] > 60
            petites = [collections.Counter(c[5] for c in x[1]["chars"] if c[0].strip()).most_common(1)[0][0]
                       < corps - 0.5 for x in toutes[n:n + 4] if x[1]["chars"] and x[1]["chars"][0][0].strip() != ""]
            suite_petite = petites and sum(petites) >= 0.66 * len(petites)
            blanc_fort = n and l["box"][1] - toutes[n - 1][1]["box"][1] > 1.5 * pas
            if l.get("djvu") and not re.match(r"^(?:[\dlIS]{1,2}|[iï])\s*[.,]", t) and l["box"][1] < 0.6 * pg["h"] \
                    and not any(re.match(r"^(?:[\dlIS]{1,2}|[iï])\s*[.,]\s*\S", texte_ligne(x[1]).strip())
                                for x in toutes[n + 1:]):
                continue                    # DjVu : liste en petit corps dans le texte, pas une suite de note
            if not centree and ((blanc_fort and suite_petite and len(t) > 20 and l["box"][1] > 0.2 * pg["h"])
                                or (re.match(r"^[1lI]\s*[.,]\s", t) and (blanc or petit)
                                 and (l["box"][1] > 0.4 * pg["h"] or (petit and suite_petite)))
                                or (petit and suite_petite and (blanc or re.match(r"^\d{1,2}\s*[.,]\s", t)))):
                debut = n
                break
        if getattr(self, "tableau", False):
            # tableau : les notes commencent à la première ligne de la moitié basse qui franchit la gouttière
            g = self.gouttiere([l for k, l in toutes if l["box"][1] > 0.15 * pg["h"]])
            debut = None
            if g is not None:
                for n, (k, l) in enumerate(toutes):
                    if l["box"][1] > 0.3 * pg["h"] and any(c[0].strip() and c[1] < g * 10 < c[3] for c in l["chars"]) \
                            and re.match(r"^\d{1,2}\s*[.,]\s", texte_ligne(l).strip()):
                        debut = n
                        break
        gauche_notes = min((l["box"][0] for n, (k, l) in enumerate(toutes) if debut is not None and n >= debut),
                           default=0)
        for n, (k, l) in enumerate(toutes):
            t = texte_ligne(l).strip()
            if debut is not None and n >= debut:
                # nouvelle note : ligne en retrait (première ligne de note) qui commence par « 3. »
                if not notes or ((re.match(r"^(?:[\dlIS]{1,2}|[iï])\s*[.,]\s+\S", t) or re.match(r"^\d{1,2}\.[A-ZÀ-Ý]", t))
                                 and l["box"][0] - gauche_notes > 25):
                    notes.append({"attr": {}, "lines": []})
                notes[-1]["lines"].append(l)
            else:
                if not corps_pars or corps_pars[-1]["k"] != k:
                    corps_pars.append({"attr": pars[k]["attr"], "lines": [], "k": k})
                corps_pars[-1]["lines"].append(l)
        # appels de note du corps de page, dans l'ordre
        anchor = '<a id="page-%s"></a>' % lab
        premiere = True
        n_appels = 0
        if getattr(self, "tableau", False) and corps_pars:
            # tableau sur deux colonnes (chronologie) : la colonne de gauche, puis celle de droite, ligne à ligne
            ls = [l for p in corps_pars for l in p["lines"]]
            titre = []
            while ls and re.fullmatch(r"[^a-zà-ÿ]*[A-ZÀ-Ý]{2,}[^a-zà-ÿ]*", texte_ligne(ls[0]).strip()):
                titre.append(texte_ligne(ls.pop(0)).strip())    # titre au-dessus du tableau (titre courant ensuite)
            if titre and not any(b["type"] == "tableau" for b in self.blocs):
                t = re.sub(r"(?<=[A-ZÉ])(\d)$", lambda m: "\x00" + m.group(1) + "\x03", " ".join(titre))     # appel de note du titre
                self.ajoute("h1", html.escape(t, quote=False), lab, anchor if premiere else "")
                n_appels += t.count("\x00")
                premiere = False
            if not ls:
                corps_pars = []
            g = self.gouttiere(ls)
            cols = [[], []]
            for l in ls:
                cut = len(l["chars"]) if g is None else self.couper(l, g)
                for side in (0, 1):
                    chs = l["chars"][:cut] if side == 0 else l["chars"][cut:]
                    while chs and not chs[0][0].strip():
                        chs.pop(0)
                    while chs and not chs[-1][0].strip():
                        chs.pop()
                    if chs:
                        sub = dict(l, chars=chs, box=(chs[0][1], l["box"][1], chs[-1][3], l["box"][3]))
                        cols[side].append(rendre_ligne(sub, appels(sub)).strip())
            rows = []
            for r in cols[0] + cols[1]:                     # suite d'une case (minuscule en tête) : recollée
                if rows and (re.match(r"(?:<[^>]+>)*[a-zà-ÿ]", r) or rows[-1][-1].endswith("-")):
                    rows[-1].append(r)
                else:
                    rows.append([r])
            rows = [self.joindre(r) for r in rows]
            n_appels += sum(h.count("\x00") for h in rows)
            if rows:
                self.ajoute("tableau", "<br />".join(rows), lab, anchor if premiere else "")
                premiere = False
            corps_pars = []
        # redécoupage ligne à ligne : retrait de première ligne, lignes centrées, lignes de vers
        droite = sorted(l["box"][2] for p in corps_pars for l in p["lines"])
        droite = droite[int(len(droite) * 0.97)] if droite else left + larg
        milieu = (left + droite) / 2
        larg = droite - left

        def genre(l):
            g, d = l["box"][0] - left, droite - l["box"][2]
            t = texte_ligne(l).strip()
            if re.fullmatch(r"[IVX]{1,4}\. [A-ZÉ].{5,80}\.", t) and d > 30 \
                    and abs((l["box"][0] + l["box"][2]) / 2 - milieu) < 0.06 * larg:
                return "centre"                                # « V. Examen du poème… » : titre de section
            if g > 60 and abs((l["box"][0] + l["box"][2]) / 2 - milieu) < 0.05 * larg and d > 60 \
                    and (re.match(r"(?:[IVXL]+|§\s*\d+)\s*[.,]\s", t) or not re.search(r"[a-zà-ÿ]{3,}", t)):
                return "centre"
            if d > 0.12 * larg and (g > 85 or (re.match(r"^[\d>\-^]{3,6}\s", t) and g > 20)):
                return "vers"
            return "normal"
        segs = []
        if getattr(self, "index", False):
            # table à retrait inversé, en colonnes : une entrée commence au bord gauche de sa colonne
            ls = [l for p in corps_pars for l in p["lines"]]
            mid = pg["w"] / 2
            g = self.gouttiere(ls) if ls and ls[0].get("djvu") else None
            if g is not None and self.deux_colonnes(ls, g):
                # DjVu : les deux colonnes sont sur la même ligne ; coupées à la gouttière, gauche puis droite
                cols = [[], []]
                for l in ls:
                    cut = len(l["chars"]) if g is None else self.couper(l, g)
                    for side, chs in ((0, l["chars"][:cut]), (1, l["chars"][cut:])):
                        chs = list(chs)
                        while chs and not chs[0][0].strip():
                            chs.pop(0)
                        while chs and not chs[-1][0].strip():
                            chs.pop()
                        if chs:
                            cols[side].append(dict(l, chars=chs, box=(chs[0][1], l["box"][1], chs[-1][3], l["box"][3])))
                ls = cols[0] + cols[1]
                if g is not None:
                    mid = g * 10 - 20
            bords = {}
            for col in (0, 1):
                xs = sorted(l["box"][0] for l in ls if (l["box"][0] >= mid) == bool(col))
                if xs:
                    bords[col] = xs[len(xs) // 20]
            cur = None
            for l in ls:
                col = int(l["box"][0] >= mid)
                if cur is None or l["box"][0] - bords.get(col, 0) < 18:
                    cur = {"attr": {"startIndent": "60"}, "lines": [], "genre": "normal"}
                    segs.append(cur)
                cur["lines"].append(l)
            corps_pars = []
        for p in corps_pars:
            cur = None
            for k, l in enumerate(p["lines"]):
                g = genre(l)
                g2 = g
                nouveau = cur is None or g2 != cur["genre"] or (
                    g2 == "normal" and 40 <= l["box"][0] - left <= 150 and cur["lines"]
                    and droite - cur["lines"][-1]["box"][2] > 0.05 * larg)
                if nouveau:
                    cur = {"attr": p["attr"] if k == 0 else {}, "lines": [], "genre": g2}
                    segs.append(cur)
                cur["lines"].append(l)
        for p in segs:
            lignes = p["lines"]
            t = " ".join(texte_ligne(l) for l in lignes).strip()
            if not t:
                continue
            indent = [l["box"][0] - left for l in lignes]
            centre = p["genre"] == "centre" and not re.match(r"\d{3}", t)
            vers = p["genre"] in ("vers", "centre") and not (centre and re.match(r"(?:[IVXL]+|§)", t))
            haut = [rendre_ligne(l, [] if getattr(self, "sans_notes", False) else appels(l)) for l in lignes]
            n_appels += sum(h.count("\x00") for h in haut)
            sans_min = not re.search(r"[a-zà-ÿ]{3,}", re.sub(r"<[^>]+>", "", " ".join(haut)))
            if sans_min and len(t) < 120 and len(lignes) <= 3 and re.search(r"[A-ZÀ-Ý]{3,}", t):
                niveau = "h1" if re.fullmatch(r"\W*(INTRODUCTION|TABLE\W*|CHRONOLOGIE.*|ADDITIONS.*)\W*", t) else "h2"
                self.ajoute(niveau, " ".join(h.strip() for h in haut), lab, anchor if premiere else "")
            elif centre and re.match(r"(?:[IVXL]+|[ivxl]+|§\s*\d+)\s*[.,]\s", t):   # « III. Examen du poème… »
                self.ajoute("h2", " ".join(h.strip() for h in haut), lab, anchor if premiere else "")
            elif vers:
                rows = []
                for h in haut:
                    h = h.strip()
                    m = re.match(r"^(\d(?:\s?\d){2,5})\s+(.*)$", h)
                    rows.append('%s <span class="numvers">%s</span>' % (m.group(2), m.group(1).replace(" ", ""))
                                if m else h)
                self.ajoute("vers", "<br />".join(rows), lab, anchor if premiere else "")
            else:
                texte = self.joindre(haut)
                debut_par = (int(p["attr"].get("startIndent", "0") or 0) >= 30 or indent[0] >= 40) \
                    and not re.match(r"(?:<[^>]+>)*[a-zà-ÿ]", texte)
                self.ajoute("p", texte, lab, anchor if premiere else "", suite=not debut_par)
            premiere = False
        # notes de la page
        n_notes = 0
        for p in notes:
            haut = [rendre_ligne(l, []) for l in p["lines"]]
            texte = self.joindre(haut)
            m = re.match(r"^\s*([\dlIS]{1,2}|[iï])\s*[.,]\s+(.*)$", texte, re.S) or \
                re.match(r"^\s*(\d{1,2})\.([A-ZÀ-Ý].*)$", texte, re.S)
            if m and (p is not notes[0] or n_notes == 0):
                reste = m.group(2)
                suivant = n_notes + 1
                while True:                     # plusieurs notes courtes sur une ligne : « … n. 5. 2. Voir … »
                    n_notes = suivant
                    coupe = next((c for c in re.finditer(r"(?<=[.)»\]?!]) ?(\d{1,2}|[ïî]) ?\. ?(?=[A-ZÀ-Ý«(])", reste)
                                  if n_notes < (n_notes + 1 if c.group(1) in "ïî" else int(c.group(1))) <= n_notes + 3), None)  # une note perdue au plus deux
                    self.blocs.append({"type": "note", "html": reste[:coupe.start()] if coupe else reste,
                                       "page": lab, "num": n_notes, "id": "note-%s-%d" % (lab, n_notes)})
                    self.notes_ouvertes = self.blocs[-1]
                    if not coupe:
                        break
                    self.stats["notes séparées"] += 1
                    suivant = n_notes + 1 if coupe.group(1) in "ïî" else int(coupe.group(1))
                    reste = reste[coupe.end():]
            elif self.notes_ouvertes is not None:
                self.notes_ouvertes["html"] += (" " if not self.notes_ouvertes["html"].endswith("-") else "") + texte
                self.notes_ouvertes["html"] = re.sub(r"(\w)- (?=[a-zà-ÿ])", r"\1", self.notes_ouvertes["html"])
        self.stats["notes"] += n_notes
        self.stats["appels"] += n_appels
        if n_appels != n_notes:
            self.stats["pages où appels ≠ notes"] += 1
        self.page_info[lab] = (n_appels, n_notes)

    def joindre(self, lignes):
        out = ""
        for h in lignes:
            h = h.strip()
            if not out:
                out = h
            elif re.search(r"\w-$", out) and re.match(r"[a-zà-ÿ]", h):
                out = out + "\x01" + h                     # coupure : décidée plus tard (mots fréquents)
            elif re.search(r"[a-zà-ÿ]$", out) and re.match(r"[a-zà-ÿ]", h):
                out = out + "\x02" + h                     # coupure dont le trait d'union s'est perdu ?
            else:
                out += " " + h
        return out

    def ajoute(self, typ, texte, lab, anchor, suite=False):
        dernier = next((b for b in reversed(self.blocs) if b["type"] != "note"), None)   # les notes de la page
        if typ == "p" and suite and dernier is not None and dernier["type"] == "p" \
                and (not re.search(r"[.!?»:)\]]\s*$", re.sub(r"<[^>]+>|\x00[^\x03]*\x03", "", dernier["html"]))
                     or re.match(r"(?:<[^>]+>)*[a-zà-ÿ]", texte)):
            prev = dernier
            sep = "\x01" if re.search(r"\w-$", prev["html"]) and re.match(r"[a-zà-ÿ]", texte) else \
                ("\x02" if re.search(r"[a-zà-ÿ]$", prev["html"]) and re.match(r"[a-zà-ÿ]", texte) else " ")
            prev["html"] += sep + anchor + texte
            self.stats["paragraphes recollés"] += 1
            return
        if typ == "vers" and self.blocs and self.blocs[-1]["type"] == "vers" and not anchor:
            self.blocs[-1]["html"] += "<br />" + texte
            return
        self.blocs.append({"type": typ, "html": anchor + texte, "page": lab})

    def renvois(self):
        """Renvois aux vers entre crochets lus de travers : « [>I66] » → « [166] », « H398] » → « [398] »."""
        tr = str.maketrans({"I": "1", "l": "1", "i": "1", "O": "0", "o": "0", "S": "5", "B": "8", ">": "", "<": "",
                            "J": "1", "H": "[", "t": "1"})

        def fix(m):
            x = m.group(1).translate(tr).replace("[", "")
            return "[%s]" % x if re.fullmatch(r"\d{2,5}(?:-\d{1,5})?", x) else m.group(0)
        for b in self.blocs:
            if b["type"] != "note":
                avant = b["html"]
                b["html"] = re.sub(r"\[([>\dIlOoSBJt-]{2,7})\]", fix, b["html"])
                b["html"] = re.sub(r"(?<=\s)H(\d{2,5})\]", r"[\1]", b["html"])
                self.stats["renvois réparés"] += avant != b["html"]

    def titres(self):
        """Un seul h1 par partie : les suivants identiques (titre courant manqué) sont retirés."""
        vus = set()
        garde = []
        for b in self.blocs:
            if b["type"] == "h1":
                cle = re.sub(r"\W|\d", "", re.sub(r"<[^>]+>", "", b["html"])).upper()
                if cle in vus:
                    self.stats["titres répétés retirés"] += 1
                    anc = re.findall(r'<a id="[^"]+"></a>', b["html"])
                    if anc and garde:
                        garde.append({"type": "p", "html": "".join(anc), "page": b["page"]})
                    continue
                vus.add(cle)
            garde.append(b)
        self.blocs = garde

    def coupures(self):
        """« guer-\x01re » → « guerre » ou « Sainte-\x01Jamme » : la forme la plus fréquente ailleurs."""
        for b in self.blocs:
            for w in re.findall(r"[A-Za-zÀ-ÿ]{2,}", re.sub(r"<[^>]+>", "", b["html"].replace("\x01", " ").replace("\x02", " "))):
                self.mots[w.lower()] += 1

        def choix(m):
            a, b = m.group(1), m.group(2)
            if self.mots[(a + b).lower()] >= self.mots[(a + "-" + b).lower()] or not re.match(r"[A-ZÀ-Ý]", b):
                return a + b
            return a + "-" + b
        if not hasattr(Livre, "dico"):
            try:
                from epub_longs import load_wordlist
                Livre.dico = load_wordlist("auto") or set()
            except Exception:
                Livre.dico = set()

        def sans_tiret(m):                                  # « mar\x02chait » → « marchait »
            a, b = m.group(1), m.group(2)
            ab = (a + b).lower()
            connu = ab in Livre.dico or self.mots[ab] >= 2
            deux_mots = a.lower() in Livre.dico and b.lower() in Livre.dico \
                and not re.fullmatch(r"(?:ment|ments|tion|tions|sion|sions|ble|bles|que|ques|ture|tures|rent|ront|lement)", b)
            if connu and not deux_mots:
                self.stats["coupures sans trait d'union recollées"] += 1
                return a + b
            return a + " " + b
        for b in self.blocs:
            b["html"] = re.sub(r"([A-Za-zÀ-ÿ]+)-\x01((?:<[^>]+>)*[A-Za-zÀ-ÿ]+)", choix, b["html"])
            b["html"] = re.sub(r"([A-Za-zÀ-ÿ]+)\x02(<a id=\"page-[^\"]+\"></a>)([a-zà-ÿ]+)",
                               lambda m: (lambda r: r.replace(" ", m.group(2) + " ", 1) if " " in r else r + m.group(2))(
                                   sans_tiret(type("M", (), {"group": lambda self, i: (m.group(1), m.group(3))[i - 1]})())),
                               b["html"])
            b["html"] = re.sub(r"([A-Za-zÀ-ÿ]+)\x02([a-zà-ÿ]+)", sans_tiret, b["html"])
            b["html"] = b["html"].replace("\x01", " ").replace("\x02", " ")

    def relier_notes(self):
        """Appels → notes de la même page : un appel lu comme un chiffre va à la note de ce numéro ; les
        autres, dans l'ordre, aux notes restantes situées entre ces repères."""
        par_page = collections.defaultdict(list)
        for b in self.blocs:
            if b["type"] == "note":
                par_page[b["page"]].append(b)
        appels = collections.defaultdict(list)            # page → [(bloc, position)]
        for bi, b in enumerate(self.blocs):
            if b["type"] == "note":
                continue
            for m in re.finditer("\x00([^\x03]*)\x03", b["html"]):
                pages = re.findall(r'<a id="page-([^"]+)"></a>', b["html"][:m.start()])
                lab = pages[-1] if pages else b["page"]
                appels[lab].append([bi, m.start(), m.group(1), None])
        for lab, cs in appels.items():
            notes = {x["num"]: x for x in par_page.get(lab, [])}   # numéros des notes (une peut manquer)
            nums = sorted(notes)
            pris = set()
            for c in cs:                                    # repères : chiffre bien lu
                if c[2].isdigit() and int(c[2]) in notes and int(c[2]) not in pris:
                    c[3] = int(c[2])
                    pris.add(c[3])
            for k, c in enumerate(cs):                      # les autres, entre les repères
                if c[3] is not None:
                    continue
                bas = max([x[3] for x in cs[:k] if x[3]] or [0])
                haut = min([x[3] for x in cs[k + 1:] if x[3]] or [10 ** 6])
                libres = [j for j in nums if bas < j < haut and j not in pris]
                if libres:
                    c[3] = libres[0]
                    pris.add(c[3])
            # restes : appels et notes encore seuls sur la page, appariés dans l'ordre
            seuls_a = [c for c in cs if c[3] is None]
            seuls_n = [j for j in nums if j not in pris]
            for c, j in zip(seuls_a, seuls_n):
                c[3] = j
                c.append("apparié")
                pris.add(j)
            for c in cs:
                if c[3] is not None:
                    notes[c[3]]["appel"] = "appel-%s-%d" % (lab, c[3])
        # réécriture des blocs
        for bi, b in enumerate(self.blocs):
            if b["type"] == "note" or "\x00" not in b["html"]:
                continue
            refs = {}
            for lab, cs in appels.items():
                for c in cs:
                    if c[0] == bi:
                        refs[c[1]] = (lab, c[3])

            def rep(m, refs=refs):
                lab, k = refs.get(m.start(), (None, None))
                if k:
                    return '<sup><a href="#note-%s-%d" id="appel-%s-%d">%d</a></sup>' % (lab, k, lab, k, k)
                self.stats["appels sans note"] += 1
                return '<span class="a-verifier" title="Appel de note sans note (lu « %s »)">*</span>' % html.escape(html.unescape(m.group(1)), quote=True)
            b["html"] = re.sub("\x00([^\x03]*)\x03", rep, b["html"])
        for lab, notes in par_page.items():
            for n in notes:
                if "appel" not in n:
                    self.stats["notes sans appel"] += 1
                    n["html"] = ('<span class="a-verifier" title="Note sans appel retrouvé p. %s">%s</span>'
                                 % (lab, "&#160;")) + n["html"]

    def run(self, vues):
        self.page_info = {}
        fsc = collections.Counter()                      # corps du texte : le plus fréquent de la partie
        for i in vues:
            for p in self.pages[i]["pars"]:
                for l in p["lines"]:
                    for c in l["chars"]:
                        if c[0].strip():
                            fsc[c[5]] += 1
        self.corps = fsc.most_common(1)[0][0] if fsc else 10
        for i in vues:
            self.page(i)


# ---------------------------------------------------------------- EPUB
CSS = """body { font-family: serif; margin: 0 5%; }
h1 { text-align: center; font-size: 1.4em; margin: 2em 0 1em; }
h2 { text-align: center; font-size: 1.1em; margin: 1.5em 0 0.8em; }
p { text-indent: 1.5em; margin: 0; text-align: justify; }
p.vers { text-indent: 0; margin: 0.6em 0 0.6em 3em; }
span.numvers { float: left; margin-left: -3em; font-size: 0.8em; color: #666; }
p.note { text-indent: 0; font-size: 0.85em; margin: 0.3em 0 0.3em 1em; }
p.centre { text-align: center; text-indent: 0; }
p.tableau { text-indent: 0; margin: 0.6em 0; text-align: left; }
span.a-verifier { background: #ffef99; }
"""


def xhtml(titre, corps):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
            '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head>\n  <title>%s</title>\n  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />\n'
            '</head>\n<body>\n%s\n</body>\n</html>\n' % (html.escape(titre), corps))


def rendu(b):
    h = b["html"].strip()
    if b["type"] in ("h1", "h2"):
        return "<%s>%s</%s>" % (b["type"], h, b["type"])
    if b["type"] == "vers":
        return '<p class="vers">%s</p>' % h
    if b["type"] == "centre":
        return '<p class="centre">%s</p>' % h
    if b["type"] == "tableau":
        return '<p class="tableau">%s</p>' % h
    if b["type"] == "note":
        retour = '<a href="#%s">%d</a>' % (b["appel"], b["num"]) if b.get("appel") else str(b["num"])
        return '<p class="note" id="%s">%s. %s</p>' % (b["id"], retour, h)
    return "<p>%s</p>" % h


def ecrire(path, parties, meta):
    bid = "urn:uuid:" + str(uuid.uuid4())
    files, nav = [], []
    for k, (nom, blocs) in enumerate(parties):
        fn = "partie-%02d.xhtml" % (k + 1)
        corps, notes = [], []
        for b in blocs:
            if b["type"] == "note":
                notes.append(rendu(b))
                continue
            if b["type"] in ("h1", "h2") and notes:          # notes avant le titre suivant
                corps += notes
                notes = []
            corps.append(rendu(b))
            if b["type"] in ("h1", "h2"):
                nid = "t%d" % (len(nav) + 1)
                corps[-1] = corps[-1].replace("<%s>" % b["type"], '<%s id="%s">' % (b["type"], nid), 1)
                nav.append((b["type"], re.sub(r"<[^>]+>", "", b["html"]).strip(), fn, nid))
        corps += notes
        if not any(b["type"] == "h1" for b in blocs):
            nav.insert(len(nav) - sum(1 for x in nav if x[2] == fn), ("h1", nom, fn, ""))
        files.append((fn, xhtml(nom, "\n".join(corps))))
    z = zipfile.ZipFile(path, "w")
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml", '<?xml version="1.0"?>\n<container version="1.0" '
               'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n<rootfiles><rootfile '
               'full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n</container>\n',
               compress_type=zipfile.ZIP_DEFLATED)
    z.writestr("OEBPS/Styles/livre.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
    for fn, data in files:
        z.writestr("OEBPS/Text/" + fn, data, compress_type=zipfile.ZIP_DEFLATED)
    man = "\n".join('    <item id="x%d" href="Text/%s" media-type="application/xhtml+xml"/>' % (k, fn)
                    for k, (fn, _) in enumerate(files))
    spine = "\n".join('    <itemref idref="x%d"/>' % k for k in range(len(files)))
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" '
           'unique-identifier="bookid" version="2.0">\n  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
           'xmlns:opf="http://www.idpf.org/2007/opf">\n    <dc:title>%s</dc:title>\n    <dc:creator '
           'opf:role="aut">%s</dc:creator>\n    <dc:language>fr</dc:language>\n    <dc:identifier '
           'id="bookid">%s</dc:identifier>\n    <dc:source>%s</dc:source>\n  </metadata>\n  <manifest>\n'
           '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n    <item id="css" '
           'href="Styles/livre.css" media-type="text/css"/>\n%s\n  </manifest>\n  <spine toc="ncx">\n%s\n'
           '  </spine>\n</package>\n' % (html.escape(meta["titre"]), html.escape(meta["auteur"]), bid,
                                         html.escape(meta.get("source", "")), man, spine))
    z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
    pts, ordre, ouvert = [], 0, False
    for niv, titre, fn, nid in nav:
        ordre += 1
        src = "Text/%s%s" % (fn, "#" + nid if nid else "")
        pt = '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/>' % (
            ordre, ordre, html.escape(titre[:120]), src)
        if niv == "h1":
            if ouvert:
                pts.append("</navPoint>")
            pts.append(pt)
            ouvert = True
        else:
            pts.append(pt + "</navPoint>")
    if ouvert:
        pts.append("</navPoint>")
    ncx = ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" '
           'version="2005-1">\n<head><meta name="dtb:uid" content="%s"/><meta name="dtb:depth" content="2"/>'
           '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>\n'
           '<docTitle><text>%s</text></docTitle>\n<navMap>\n%s\n</navMap>\n</ncx>\n'
           % (bid, html.escape(meta["titre"]), "\n".join(pts)))
    z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
    z.close()


def plage(spec):
    a, b = spec.split("-") if "-" in spec else (spec, spec)
    return list(range(int(a), int(b) + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("abbyy", help="<livre>_abbyy.gz d'Internet Archive, ou un DjVu à couche texte")
    ap.add_argument("-o", "--output")
    ap.add_argument("--titre", default="Livre")
    ap.add_argument("--auteur", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--pagination", default="", help="vue=étiquette de départ, par ex. 16=1,320=i")
    ap.add_argument("--parties", help="vues:nom, par ex. « 320-443:Introduction,16-284:Traduction »")
    ap.add_argument("--texte", help="écrire seulement le texte brut, ligne à ligne (référence pour "
                                    "epub_reference.py ; remplace le _djvu.txt d'Internet Archive)")
    opts = ap.parse_args()
    pages = lire_djvu(opts.abbyy) if opts.abbyy.lower().endswith(".djvu") else lire(opts.abbyy)
    if opts.texte:
        with open(opts.texte, "w", encoding="utf-8") as f:
            for pg in pages:
                for p in pg["pars"]:
                    for l in p["lines"]:
                        f.write("".join(c[0] for c in l["chars"]).strip() + "\n")
                    f.write("\n")
        print("Texte écrit : %s" % opts.texte)
        return
    if not opts.parties or not opts.output:
        ap.error("--parties et -o sont nécessaires pour écrire l'EPUB")
    labels = etiquettes(opts.pagination, len(pages))
    parties = []
    stats = collections.Counter()
    for item in opts.parties.split(","):
        vues, nom = item.split(":", 1)
        drapeaux = set(nom.split(":")[1:])
        nom = nom.split(":")[0]
        L = Livre(pages, labels, opts)
        L.sans_notes = "sans-notes" in drapeaux or "index" in drapeaux
        L.index = "index" in drapeaux
        L.tableau = "tableau" in drapeaux
        L.run(plage(vues))
        L.titres()
        L.coupures()
        L.renvois()
        L.relier_notes()
        parties.append((nom, L.blocs))
        stats.update(L.stats)
        mauvais = [lab for lab, (a, n) in L.page_info.items() if a != n]
        if mauvais:
            print("  %s : appels ≠ notes p. %s" % (nom, ", ".join(mauvais[:40]) + (" …" if len(mauvais) > 40 else "")))
    ecrire(opts.output, parties, {"titre": opts.titre, "auteur": opts.auteur, "source": opts.source})
    print(", ".join("%s : %d" % kv for kv in sorted(stats.items())))
    print("EPUB écrit : %s" % opts.output)


if __name__ == "__main__":
    main()
