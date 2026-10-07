#!/usr/bin/env python3
"""Autres lectures d'un poème édité vers par vers : compare chaque vers de l'EPUB (paragraphes « vers »
de pdf_vers.py) aux lignes correspondantes d'autres numérisations de la MÊME édition lues par d'autres
moteurs d'OCR, et corrige.

Références : texte brut (le _djvu.txt d'Internet Archive, lu par ABBYY ; un texte Tesseract) ou PDF à
couche texte (PDF Google Livres, lu par l'OCR de Google). La première est la référence principale, la
seconde (facultative) vote.

Appariement : les vers sont retrouvés un à un dans chaque référence, dans l'ordre, par ressemblance des
lettres (numéros de vers, titres courants et notes de la référence ne trouvent pas de partenaire).

Arbitrage, mot à mot, à l'intérieur d'un vers apparié :
  vote         les deux références lisent le même mot (ou signe) et l'EPUB un autre : on prend leur
               lecture, même si les deux mots existent (« tost » / « tot », accents) ;
  veto         la seconde référence lit comme l'EPUB : la correction de la première est écartée ;
  accent       (--accents-ref2) è / é : la seconde référence l'emporte seule (l'OCR Google lit fidèlement
               « pére », « maniére », « près », « aprés » ; ABBYY modernise en « père », « manière ») ;
  ponctuation  un signe (« » : ; , . ? !) d'une référence là où l'EPUB a un signe parasite, une lettre
               isolée lue pour un guillemet, ou rien (signes ajoutés, jamais retirés) ;
  mot          (une seule référence) le mot de l'EPUB est inconnu et celui de la référence connu, ou
               s'en déduit par une confusion typique de l'OCR Gallica (t, I, J, i lus pour l ; M, Ii, Ji
               pour li) : « !u[i] » → « lu[i] », « mott » → « molt » ;
  parasite     signe parasite de l'EPUB absent de la référence (` ~ ° ' ^ |) : supprimé.
Deux mots connus qui diffèrent sans vote (« tost » / « l'ost ») ne sont pas touchés : ils vont au journal
comme « variante ». Les mots remplacés sont repérés a-verifier (« Autre lecture : … »), pas les signes.

  python3 epub_vers_reference.py t2.epub ia_djvu.txt --ref2 google-t2.pdf -o t2-ref.epub \\
      --vocab t1.epub --report t2-ref.tsv
  # document maître déjà relu : seulement ce sur quoi les deux références s'accordent
  python3 epub_vers_reference.py t1.epub tesseract.txt --ref2 google-t1.pdf --vote-seul -o …
"""
import argparse
import collections
import difflib
import re
import unicodedata
import zipfile

import epub_ocr_vers as O

NB = " "
PRIV = "-"
SPC = "   "
PONCT = set("«»:;,.?!")
PARASITE = set("`~°'^|’\"")
# confusions de l'OCR Gallica qu'une autre lecture corrige (lettre de l'EPUB → lettre de la référence)
CONF_GALLICA = {("t", "l"), ("I", "l"), ("J", "l"), ("i", "l")}
LI_GALLICA = {"M", "Ii", "Ji", "tl", "h", "H"}
BRUIT = {"a", "<", "<t", "t", "c", "f", "D", "B", "s", "r", "p", "n", "e", "d", ">", "1", "&", "°", "`", "~"}


def squelette(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.replace("!", "l"))


def coeur(tok):
    return re.sub(r"^[^\w\[]+|[^\w\]]+$", "", tok)


def confusion_gallica(x, y):
    """y s'obtient de x en remplaçant seulement des lettres que l'OCR Gallica confond (t/I/J/i lus pour l)."""
    if len(x) != len(y) or x == y:
        return False
    return all(a == b or (a, b) in CONF_GALLICA for a, b in zip(x, y))


def accent_seul(x, y):
    """x et y ne diffèrent que par des è/é (« pére » / « père », « Mès » / « Mes » exclu)."""
    return len(x) == len(y) and x != y and all(a == b or {a, b} == {"è", "é"} for a, b in zip(x, y))


def lignes_reference(path):
    if path.lower().endswith(".pdf"):
        import pymupdf
        doc = pymupdf.open(path)
        brut = [l for p in doc for l in p.get_text().split("\n")]
    else:
        brut = open(path, encoding="utf-8", errors="replace").read().split("\n")
    out = []
    for l in brut:
        l = re.sub(r"\s+", " ", l).strip()
        l = l.replace("<<", "«").replace(">>", "»")              # guillemets de l'OCR Google
        l = re.sub(r" ([,.])(?= |$)", r"\1", l)                  # « Ric. , bien » → « Ric., bien »
        l = re.sub(r"^\d(?: ?\d){3,5} ", "", l)                  # numéro de vers (« 1 0940 »)
        if l:
            out.append(l)
    return out


class Reference:
    def __init__(self, path, opts):
        self.lignes = lignes_reference(path)
        self.sq = [squelette(l) for l in self.lignes]
        self.pos = 0
        self.o = opts
        # flux de mots (prose : notes, vocabulaire), coupures de fin de ligne recollées
        flux = re.sub(r"(\w)- (?=[a-zà-ÿ])", r"\1", " ".join(self.lignes))
        self.mots = flux.split()
        self.msq = [squelette(w) or w for w in self.mots]
        self.mpos = 0

    def passage(self, a):
        """Passage de prose correspondant aux mots a (None si introuvable)."""
        asq = [squelette(w) or w for w in a]
        for large in (3 * len(a) + 400, 3 * len(a) + 4000):
            w0 = self.mpos
            win = self.msq[w0:w0 + large]
            sm = difflib.SequenceMatcher(None, asq, win, autojunk=False)
            blocs = [b for b in sm.get_matching_blocks() if b.size]
            if not blocs:
                continue
            ancre = max(blocs, key=lambda b: b.size)          # le plus long bloc commun fait foi
            deb = max(0, ancre.b - ancre.a - 3)
            fin = min(len(win), ancre.b + len(a) - ancre.a + 3)
            seg = win[deb:fin]
            r = difflib.SequenceMatcher(None, asq, seg, autojunk=False)
            if ancre.size >= min(4, len(a)) and sum(x.size for x in r.get_matching_blocks()) >= 0.6 * len(a):
                self.mpos = w0 + max(deb, fin - 3)
                return self.mots[w0 + deb:w0 + fin]
        return None

    def apparier(self, txt):
        sq = squelette(txt)
        if len(sq) < 8:
            return None
        best, bj = 0, None
        for j in range(self.pos, min(len(self.sq), self.pos + self.o.fenetre)):
            if abs(len(self.sq[j]) - len(sq)) > max(6, len(sq) // 3):
                continue
            r = difflib.SequenceMatcher(None, sq, self.sq[j], autojunk=False).ratio()
            if r > best:
                best, bj = r, j
                if r == 1:
                    break
        if bj is not None and best >= self.o.min_ratio:
            self.pos = bj + 1
            return self.lignes[bj]
        # perdu : on cherche plus loin, avec une exigence plus forte (vers assez long, 0,88)
        if len(sq) >= 18:
            for j in range(self.pos, min(len(self.sq), self.pos + 4000)):
                if abs(len(self.sq[j]) - len(sq)) > 4:
                    continue
                m = difflib.SequenceMatcher(None, sq, self.sq[j], autojunk=False)
                if m.real_quick_ratio() >= 0.88 and m.quick_ratio() >= 0.88 and m.ratio() >= 0.88:
                    self.pos = j + 1
                    return self.lignes[j]
        return None


def correspondance(a, ref):
    """Mots de l'EPUB ↔ mots d'une référence : un pour un, signes insérés, blocs inégaux, mots en trop."""
    sm = difflib.SequenceMatcher(None, [squelette(t) or t for t in a], [squelette(t) or t for t in ref],
                                 autojunk=False)
    un, ins, blocs, dels = {}, collections.defaultdict(list), [], set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                un[i1 + k] = ref[j1 + k]
        elif op == "insert":
            ins[i1].extend(ref[j1:j2])
        elif op == "delete":
            dels.update(range(i1, i2))
        else:
            blocs.append((i1, i2, ref[j1:j2]))
    return un, ins, blocs, dels


class Arbitre:
    def __init__(self, freq, vote_seul=False, accents_ref2=False):
        self.f = freq
        self.vote_seul = vote_seul
        self.accents_ref2 = accents_ref2
        self.log = []

    def freq(self, w):
        """Occurrences du mot ; avec apostrophe (« l'ost »), celles de sa partie la plus rare."""
        parts = [p for p in re.split(r"['’]", re.sub(r"[\[\]]", "", coeur(w)).lower()) if len(p) > 1]
        if not parts:
            return 99 if coeur(w) else 0
        return min(self.f.get(p, 0) for p in parts)

    @staticmethod
    def ponct_seul(t):
        return bool(t) and all(c in PONCT for c in t)

    @staticmethod
    def marque(avant, apres):
        """Repère a-verifier (rendu par epub_ocr_vers.Ligne.out) : le mot vient d'une autre lecture."""
        return "\x01%s\x02Autre lecture : « %s » lu « %s »\x03" % (apres, avant.replace('"', "'"), apres)

    def vers(self, a, refs, ctx):
        """a : mots de l'EPUB ; refs : mots de chaque référence appariée (None si pas de partenaire)."""
        maps = [correspondance(a, r) if r else None for r in refs]
        m1 = maps[0]
        m2 = maps[1] if len(maps) > 1 else None
        rep = {}
        ins = collections.defaultdict(list)
        for i, x in enumerate(a):
            y1 = m1[0].get(i) if m1 else None
            y2 = m2[0].get(i) if m2 else None
            if self.accents_ref2 and y2 is not None and y2 != x and accent_seul(x, y2):
                r = y2                                     # è / é : la seconde référence lit l'imprimé
                self.log.append((ctx, "accent", x, y2))
            elif y1 is not None and y1 == y2 and y1 != x:
                r = self.vote(x, y1, ctx)
            elif self.vote_seul:
                r = None
            elif y1 is not None and y1 != x and y2 != x:
                r = self.mot(x, y1, ctx)
                if r is None and y2 is not None and y2 != x:
                    r = self.mot(x, y2, ctx)
            elif y1 is None and y2 is not None and y2 != x:
                r = self.mot(x, y2, ctx)
            else:
                if y1 is not None and y1 != x and y2 == x and squelette(x) != squelette(y1):
                    self.log.append((ctx, "veto", x, y1))
                r = None
            if r is not None:
                rep[i] = r
        # signes insérés : d'accord entre les références, ou proposés par l'une sans objection de l'autre
        for i in sorted((set(m1[1]) if m1 else set()) | (set(m2[1]) if m2 else set())):
            p1 = [p for p in (m1[1].get(i, []) if m1 else []) if self.ponct_seul(p)]
            p2 = [p for p in (m2[1].get(i, []) if m2 else []) if self.ponct_seul(p)]
            if p1 and p1 == p2:
                ins[i] = p1
            elif not self.vote_seul and (p1 or p2):
                ins[i] = p1 or [p for p in p2 if p in ":;«»?!"]
            if ins.get(i):
                self.log.append((ctx, "ponctuation", "", " ".join(ins[i])))
            elif i in ins:
                del ins[i]
        if self.vote_seul:
            return rep, ins
        # mots en trop : signes parasites
        for i in (m1[3] if m1 else set()):
            if all(c in PARASITE for c in a[i]) and (not m2 or i not in m2[0]):
                rep[i] = None
                self.log.append((ctx, "parasite", a[i], ""))
        # blocs inégaux (même suite de lettres coupée autrement), d'après la première référence puis la seconde
        for m in (m1, m2):
            if not m:
                continue
            for i1, i2, B in m[2]:
                if any(k in rep for k in range(i1, i2)):
                    continue
                A = a[i1:i2]
                if m is m1 and m2 and all(m2[0].get(k) == a[k] for k in range(i1, i2)):
                    continue                                  # veto de la seconde lecture
                r = self.bloc(A, B, ctx)
                if r is not None:
                    rep[i1] = r
                    for k in range(i1 + 1, i2):
                        rep[k] = None
        return rep, ins

    def bloc(self, A, B, ctx):
        if len(A) == 1 and A[0] in BRUIT and all(self.ponct_seul(y) for y in B) and "«" in B:
            self.log.append((ctx, "ponctuation", A[0], " ".join(B)))   # « dist a Alez » → « dist : « Alez »
            return " ".join(B)
        if squelette("".join(A)) and squelette("".join(A)) == squelette("".join(B)) \
                and not any(re.search(r"[({)}]", t) for t in A + B) \
                and (any(self.freq(x) < 2 for x in A if not self.ponct_seul(x)) or any(x.startswith("!") for x in A)) \
                and all(self.freq(y) >= 3 and len(coeur(y)) > 1 or self.ponct_seul(y) for y in B) \
                and not ("ü" in "".join(A) and "ii" in "".join(B)) \
                and not (len(B) > len(A) and any(re.match(r"\[|\S*\]$", t) for t in B[1:])) \
                and sum(t.count("[") for t in A) == sum(t.count("[") for t in B):
            # « Mo ! t » → « Molt » ; jamais « verai[e]ment » → « verai [e]ment »
            self.log.append((ctx, "mot", " ".join(A), " ".join(B)))
            return self.marque(" ".join(A), " ".join(B))
        self.log.append((ctx, "variante", " ".join(A), " ".join(B)))
        return None

    def vote(self, x, y, ctx):
        """Les deux références s'accordent contre l'EPUB."""
        if re.fullmatch(r"\d{4,5}[.,]?", y) and re.fullmatch(r"[\dHIltif~]{4,6}[.,]?", x) and re.search(r"\d", x):
            self.log.append((ctx, "vote", x, y))           # numéro de vers abîmé dans une note
            return y
        if re.search(r"[({)}\d]", x + y) or x.count("[") != y.count("["):
            return None
        if self.ponct_seul(y) or self.ponct_seul(x):
            if self.ponct_seul(x) and self.ponct_seul(y) or x in BRUIT or all(c in PARASITE for c in x):
                self.log.append((ctx, "vote", x, y))
                return y
            return None
        cx, cy = coeur(x), coeur(y)
        if not cx or not cy:
            return None
        if cx == cy:
            return self.signes(x, y, cx, cy, ctx)
        sans = "".join(c for c in unicodedata.normalize("NFD", cx) if not unicodedata.combining(c))
        if unicodedata.normalize("NFC", sans) != cx and sans == cy and not re.search("[àìòù]", cx):
            # tréma, cédille… perdus par l'OCR : Meyer les imprime ou non (« ço », « processïons »)
            self.log.append((ctx, "variante", x, y))
            return None
        propre = re.fullmatch(r"[A-ZÀ-Ý]?[a-zà-ÿœæ'’\[\]]+", cx)
        if propre and (len(cy) < len(cx) and cy.lower() in cx.lower() or self.freq(cy) < 2):
            self.log.append((ctx, "variante", x, y))     # lettre perdue (« Qui » → « ui ») ou mot inconnu
            return None
        if propre and len(cx) >= 4 and difflib.SequenceMatcher(None, squelette(cx), squelette(cy)).ratio() < 0.6:
            self.log.append((ctx, "variante", x, y))     # mot propre et très différent : décalage probable
            return None
        self.log.append((ctx, "vote", x, y))
        return self.marque(x, y)

    def signes(self, x, y, cx, cy, ctx):
        """Même mot, signes différents autour : ajouter ceux de la référence, ôter les parasites."""
        px, sx = x[:x.index(cx)], x[x.index(cx) + len(cx):]
        py, sy = y[:y.index(cy)], y[y.index(cy) + len(cy):]
        nx = "".join(c for c in px if c not in PARASITE), "".join(c for c in sx if c not in PARASITE)
        if not nx[1] and sy and all(c in PONCT for c in sy):
            nx = nx[0], sy
        if not nx[0] and py and all(c in PONCT for c in py):
            nx = py, nx[1]
        r = nx[0] + cx + nx[1]
        if r != x:
            self.log.append((ctx, "ponctuation", x, r))
            return r
        return None

    def mot(self, x, y, ctx):
        """Une seule référence propose y."""
        if x == y or re.search(r"[({)}\d]", x + y):
            return None
        if self.ponct_seul(x) and not self.ponct_seul(y):
            return None                                   # un signe juste de l'EPUB n'est jamais remplacé
        if self.ponct_seul(y):
            if x in BRUIT or all(c in PARASITE for c in x) or (self.ponct_seul(x) and y in ("«", "»") and x not in ("«", "»")):
                self.log.append((ctx, "ponctuation", x, y))
                return y
            return None
        cx, cy = coeur(x), coeur(y)
        if x.count("[") != y.count("[") or not cy or not cx:
            return None
        if re.search("[àìòù]", cx) and squelette(cx) == squelette(cy):    # « pàïs » → « païs », pas « pais »
            r = x.translate(str.maketrans("àìòù", "aiou"))
            self.log.append((ctx, "mot", x, r))
            return r
        if cx == cy:
            return self.signes(x, y, cx, cy, ctx)
        if cx.lower() == cy.lower():
            return None                                   # casse : on garde l'EPUB
        if squelette(cx) == squelette(cy):
            if self.freq(cx) < 2:                         # accents seuls : choix de l'éditeur, on garde
                self.log.append((ctx, "variante", x, y))
            return None
        fx, fy = self.freq(cx), self.freq(cy)
        if (cy == "li" and cx in LI_GALLICA) or (confusion_gallica(cx, cy) and fy >= 5 * fx + 3):
            self.log.append((ctx, "mot", x, y))
            return self.marque(x, y) if cx not in LI_GALLICA else y
        if fx < 2 and fy >= 3 and fy >= 5 * fx and not ("ü" in cx and "ii" in cy) \
                and difflib.SequenceMatcher(None, squelette(cx), squelette(cy)).ratio() >= 0.5:
            self.log.append((ctx, "mot", x, y))
            return self.marque(x, y)
        if fx >= 2 and fy >= 2:
            self.log.append((ctx, "variante", x, y))
        return None


def recompose(parts, rep, ins):
    """parts : liste de (mot, séparateur) ; applique remplacements et insertions."""
    out = []
    for i, (w, sep) in enumerate(parts):
        for p in ins.get(i, []):
            out.append((p, " "))
        if i in rep:
            if rep[i] is None:
                continue
            w = rep[i]
        out.append((w, sep))
    out = [(re.sub(r"(?<=[\w\]])([;:?!»])", NB + r"\1", w) if not re.search(r"\[[^\]]*[;:?!]", w) else w, sep)
           for w, sep in out]
    s = ""
    for w, sep in out:
        if s and w and w[0] in ":;?!»" and not s.endswith(NB):
            s = s.rstrip(" ") + NB
        elif s and w and w[0] in ",." and s.endswith((" ", NB)):
            s = s.rstrip(" " + NB)
        s += w
        if w == "«":
            sep = NB
        s += sep
    s = re.sub(r"«(?=[^\s%s])" % NB, "«" + NB, s)
    return re.sub(r"([;:?!,.])[ %s]*\1" % NB, r"\1", s)     # signe déjà présent : pas de doublon


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("reference", help="texte brut ou PDF à couche texte d'une autre numérisation (même édition)")
    ap.add_argument("--ref2", help="seconde référence (autre moteur d'OCR) : vote et veto")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--vote-seul", action="store_true",
                    help="n'appliquer que ce sur quoi les deux références s'accordent (document déjà relu)")
    ap.add_argument("--accents-ref2", action="store_true",
                    help="è / é : suivre la seconde référence (Meyer imprime « pére », « maniére », mais « près »)")
    ap.add_argument("--vocab", nargs="*", default=[])
    ap.add_argument("--prose", default="variantes,glossaire",
                    help="classes de paragraphes de prose corrigés par vote seul (vide : aucun)")
    ap.add_argument("--report", help="journal TSV (fichier, règle, avant, après, vers EPUB, lignes de référence)")
    ap.add_argument("--min-ratio", type=float, default=0.72, help="ressemblance minimale pour apparier un vers")
    ap.add_argument("--fenetre", type=int, default=60, help="lignes de référence explorées après le dernier vers apparié")
    opts = ap.parse_args()
    if opts.vote_seul and not opts.ref2:
        ap.error("--vote-seul demande --ref2")

    refs = [Reference(opts.reference, opts)] + ([Reference(opts.ref2, opts)] if opts.ref2 else [])
    freq = collections.Counter()
    for r in refs:
        for l in r.lignes:
            O.mots_de(l, freq)
    for k, n in O.vocabulaire([opts.epub] + opts.vocab).items():
        freq[k] += n
    arb = Arbitre(freq, opts.vote_seul, opts.accents_ref2)
    arb_prose = Arbitre(freq, True, opts.accents_ref2)
    arb_prose.log = arb.log
    prose = set(c for c in opts.prose.split(",") if c)
    stats = collections.Counter()

    zin = zipfile.ZipFile(opts.epub)
    # ordre de lecture (spine) : l'appariement avance dans les références, l'ordre de l'archive peut différer
    opf = next(n for n in zin.namelist() if n.endswith(".opf"))
    o = zin.read(opf).decode("utf-8")
    base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
    hrefs = dict(re.findall(r'<item\b[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', o))
    hrefs.update({i: h for h, i in re.findall(r'<item\b[^>]*?href="([^"]+)"[^>]*?id="([^"]+)"', o)})
    ordre = [base + hrefs[i] for i in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', o) if i in hrefs]
    ordre += [n for n in zin.namelist() if n not in ordre]
    nouveaux = {}
    for name in ordre:
        data = zin.read(name)
        item = zin.getinfo(name)
        if item.filename.endswith(".xhtml") and re.search(rb'class="[^"]*\b(vers|variantes|glossaire)\b', data):
            t = data.decode("utf-8")

            def para(m):
                classes = set(m.group(2).split())
                if classes & prose and len(refs) > 1:
                    return para_prose(m)
                if "vers" not in classes:
                    return m.group(0)
                lines = re.split(r"(<br\s*/>)", m.group(4))
                for i in range(0, len(lines), 2):
                    li = O.Ligne(lines[i])
                    txt = re.sub("[%s]" % PRIV, " ", li.s)
                    stats["vers"] += 1
                    lus = [r.apparier(txt) for r in refs]
                    for k, l in enumerate(lus):
                        stats["appariés %d" % (k + 1)] += l is not None
                    if not any(lus):
                        continue
                    # mots de l'EPUB ; les repères de balises collés à un mot (ancre de page…) sont mis de côté
                    parts = re.findall(r"([^\s%s%s]+|[%s]+)([\s%s]*)" % (SPC, PRIV, PRIV, SPC), li.s)
                    idx = [k for k, (w, _) in enumerate(parts) if not re.fullmatch("[%s]+" % PRIV, w)]
                    bords = [re.fullmatch(r"([%s]*)(.*?)([%s]*)" % (PRIV, PRIV), parts[k][0]).groups() for k in idx]
                    words = [b[1] for b in bords]
                    ctx = (item.filename.rsplit("/", 1)[-1], txt.strip()[:70], " ‖ ".join((l or "")[:70] for l in lus))
                    rep, ins = arb.vers(words, [l.split() if l else None for l in lus], ctx)
                    if not rep and not ins:
                        continue
                    rep2 = {idx[k]: (bords[k][0] + (v or "") + bords[k][2]) if (v or bords[k][0] or bords[k][2]) else None
                            for k, v in rep.items()}
                    ins2 = {idx[k]: v for k, v in ins.items() if k < len(idx)}
                    # une insertion en fin de vers se place après le dernier mot, avant les repères finals
                    if len(idx) in ins and idx:
                        k = len(idx) - 1
                        base = rep[k] if k in rep and rep[k] is not None else words[k]
                        rep2[idx[k]] = bords[k][0] + base + "".join((NB if p in ":;?!»" else "") + p
                                                                    for p in ins[len(idx)]) + bords[k][2]
                    li.s = recompose(parts, rep2, ins2)
                    lines[i] = li.out()
                return m.group(1) + "".join(lines) + m.group(5)
            def para_prose(m):
                li = O.Ligne(m.group(4))
                parts = re.findall(r"([^\s%s%s]+|[%s]+)([\s%s]*)" % (SPC, PRIV, PRIV, SPC), li.s)
                idx = [k for k, (w, _) in enumerate(parts) if not re.fullmatch("[%s]+" % PRIV, w)]
                bords = [re.fullmatch(r"([%s]*)(.*?)([%s]*)" % (PRIV, PRIV), parts[k][0]).groups() for k in idx]
                words = [b[1] for b in bords]
                if len(words) < 3:
                    return m.group(0)
                stats["prose"] += 1
                lus = [r.passage(words) for r in refs]
                stats["prose appariée"] += all(lus)
                if not all(lus):
                    return m.group(0)
                ctx = (item.filename.rsplit("/", 1)[-1], " ".join(words)[:70], "")
                rep, ins = arb_prose.vers(words, lus, ctx)
                ins = {k: v for k, v in ins.items() if 0 < k < len(idx)}
                if not rep and not ins:
                    return m.group(0)
                rep2 = {idx[k]: (bords[k][0] + (v or "") + bords[k][2]) if (v or bords[k][0] or bords[k][2]) else None
                        for k, v in rep.items()}
                li.s = recompose(parts, rep2, {idx[k]: v for k, v in ins.items()})
                return m.group(1) + li.out() + m.group(5)
            t = re.sub(r'(<p class="([^"]*)"([^>]*)>)(.*?)(</p>)', para, t, flags=re.S)
            nouveaux[name] = t.encode("utf-8")
    zout = zipfile.ZipFile(opts.output, "w")
    for item in zin.infolist():
        data = nouveaux.get(item.filename) or zin.read(item.filename)
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    n = collections.Counter(r for _, r, _, _ in arb.log)
    print("vers : %d, appariés : %s ; paragraphes de prose : %d, appariés : %d"
          % (stats["vers"], " / ".join(str(stats["appariés %d" % (k + 1)]) for k in range(len(refs))),
             stats["prose"], stats["prose appariée"]))
    print("journal : " + ", ".join("%s %d" % kv for kv in n.most_common())
          + " (variantes et vetos ne sont pas appliqués)")
    if opts.report:
        with open(opts.report, "w", encoding="utf-8") as f:
            f.write("fichier\trègle\tavant\taprès\tvers EPUB\tlignes de référence\n")
            for (fn, txt, rl), r, a, b in arb.log:
                f.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (fn, r, a, b, txt, rl))


if __name__ == "__main__":
    main()
