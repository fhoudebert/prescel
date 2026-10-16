#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_temoins.py — Cibler la relecture d'un EPUB d'OCR en le confrontant à plusieurs lectures du même
livre (autres OCR d'une autre numérisation de la même édition) et, à titre d'indice, au texte d'une
autre édition (Wikisource).

Principe, vérifié sur le scan pour les Chroniques de Froissart (éd. Kervyn, t. XIII) : quand deux
lectures indépendantes de la même édition (OCR de Google, Tesseract sur le scan d'Internet Archive)
s'accordent contre l'EPUB, c'est presque toujours l'EPUB qui se trompe. Une autre édition (Buchon sur
Wikisource) suit un autre manuscrit et modernise l'orthographe : elle ne tranche rien, elle est citée
dans les notes de relecture.

Corrections faites d'office (toutes listées dans le TSV et le rapport) :
  substitution    toutes les lectures donnent le même mot, différent de l'EPUB (« due » → « duc »,
                  « Guéries » → « Guerles », « dévoient » → « devoient ») ; jamais pour un nombre romain
                  (les OCR perdent l'exposant : « IIIIm », « XXVIIe ») ;
  mots collés     « cuidoiepasjà » → « cuidoie pas jà » quand toutes les lectures coupent de même ;
  mot perdu       toutes les lectures ont le même mot (« à », « se », « considéré ») là où l'EPUB n'a rien ;
  lettre parasite lettre isolée (« a », « Il », « c »…) qu'aucune lecture n'a : le plus souvent un
                  guillemet de début de ligne mal lu.
Marqué <span class="a-verifier" title="…"> (à trancher dans Sigil, la note donne les lectures) :
  lectures en désaccord sur un mot inconnu ; nombre romain mal lu ; lettre isolée près d'un chiffre
  (appel de variante perdu ?) ; mot ou passage absent de toutes les lectures (apparat mêlé au texte,
  ligne répétée) ; chiffre arabe dans le récit (appel de variante en chiffre ordinaire).
Rapport : pages à relire de près (marques, désaccords restants) et pages où les lectures concordent.

Usage :
  python3 scripts/epub_temoins.py livre-a-relire.epub -o livre-temoins.epub \\
      --lecture google.epub --lecture livre-tesseract.txt \\
      --wikisource "Les_Chroniques_de_Sire_Jean_Froissart/Livre_III" --de XC --a CXXXVIII \\
      --recit-jusqua titre-4 --scan "https://archive.org/details/oeuvresdefroiss02belggoog/page/n{vue}" \\
      --decalage-scan 7 --rapport temoins.html --tsv temoins.tsv
"""

import argparse
import bisect
import collections
import difflib
import html
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from epub_reference import reference_text            # noqa: E402
from epub_longs import load_wordlist                  # noqa: E402

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.U)
ROMAN = re.compile(r"^[IVXLCDM]+[A-Za-zé]{0,3}$")      # « XIIIe », « IIIIm », « IIP », « XXVIIo »
ROMAN_STRICT = re.compile(r"^[IVXLC]+(?:e|es|m|c|xx|me|re)?$")
SKIP_CLASSES = ("variantes", "marge")
PARASITES = {"il", "ci", "cc", "lû", "li", "ll"}


# --------------------------------------------------------------------------
# Formes
# --------------------------------------------------------------------------

def norm(w):
    return w.lower().replace("’", "'").replace("ſ", "s")


def skel(w):
    """Squelette insensible aux graphies (alignement et comparaison avec une autre édition)."""
    w = unicodedata.normalize("NFD", norm(w))
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    w = re.sub(r"[^a-z']", "", w).replace("y", "i").replace("oi", "ai")
    w = re.sub(r"s(?=[bcdfghjklmnpqrtvwz])", "", w)
    w = re.sub(r"(.)\1", r"\1", w)
    w = re.sub(r"(ez|es|e|s|x|z)$", "", w)
    return w.replace("ain", "an").replace("ei", "e").replace("ai", "e") or "_"


def flat(w):
    return re.sub(r"['’\-]", "", norm(w))


# --------------------------------------------------------------------------
# EPUB à relire : mots avec leur position dans le XHTML
# --------------------------------------------------------------------------

def page_labels(z):
    """ancre page-N → numéro imprimé, d'après la liste des pages (NCX ou nav)."""
    labels = {}
    for n in z.namelist():
        if n.endswith((".ncx", ".xhtml")) and ("toc" in n or "nav" in n):
            t = z.read(n).decode("utf-8", "replace")
            for m in re.finditer(r'<pageTarget[^>]*>\s*<navLabel>\s*<text>([^<]*)</text>.*?src="[^"#]*#(page-\d+)"', t, re.S):
                labels[m.group(2)] = m.group(1).strip()
    return labels


def read_master(path, stop_id):
    z = zipfile.ZipFile(path)
    opf_path = re.search(r'full-path="([^"]+)"', z.read("META-INF/container.xml").decode()).group(1)
    opf = z.read(opf_path).decode("utf-8")
    base = os.path.dirname(opf_path)
    items = {m.group(1): m.group(2) for m in re.finditer(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf)}
    items.update({m.group(2): m.group(1) for m in re.finditer(r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', opf)})
    spine = [os.path.normpath(os.path.join(base, items[i])).replace("\\", "/")
             for i in re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf) if i in items]
    labels = page_labels(z)
    toks, digits, raws = [], [], {}
    page, recit = "", True
    for f in spine:
        if not f.endswith(("html", "htm")) or f not in z.namelist():
            continue
        raw = z.read(f).decode("utf-8")
        raws[f] = raw
        stop = raw.find('id="%s"' % stop_id) if stop_id else -1
        for m in re.finditer(r"<p(\s[^>]*)?>(.*?)</p>", raw, re.S):
            attrs, content, c0 = m.group(1) or "", m.group(2), m.start(2)
            if 0 <= stop < m.start():
                recit = False
            skip = any(re.search(r'class="[^"]*\b%s\b' % c, attrs) for c in SKIP_CLASSES)
            in_sup = False
            spans_mark = {}
            for m2 in re.finditer(r'(<span class="a-verifier"[^>]*>)([^<]*)(</span>)', content):
                spans_mark[(m2.start(2) + c0, m2.end(2) + c0)] = ((m2.start(1) + c0, m2.end(1) + c0),
                                                                 (m2.start(3) + c0, m2.end(3) + c0))
            for tm in re.finditer(r"<[^>]+>|[^<]+", content):
                seg = tm.group(0)
                if seg.startswith("<"):
                    pg = re.search(r'id="(page-\d+)"', seg)
                    if pg:
                        page = labels.get(pg.group(1), pg.group(1))
                    if seg.startswith("<sup"):
                        in_sup = True
                    elif seg == "</sup>":
                        in_sup = False
                    continue
                if skip or in_sup:
                    continue
                base_off = c0 + tm.start()
                seg = re.sub(r"&#?\w+;", lambda e: " " * len(e.group(0)), seg)     # « &amp; » n'est pas un mot
                for wm in WORD.finditer(seg):
                    s = base_off + wm.start()
                    toks.append({"f": f, "s": s, "e": s + len(wm.group(0)), "w": html.unescape(wm.group(0)),
                                 "page": page, "recit": recit, "mark": spans_mark.get((s, s + len(wm.group(0))))})
                if recit:
                    for dm in re.finditer(r"(?<![\w.,])(\d{1,2})(?![\w,.]\d)", seg):
                        s = base_off + dm.start(1)
                        digits.append({"f": f, "s": s, "e": s + len(dm.group(1)), "w": dm.group(1), "page": page})
    return z, raws, toks, digits


# --------------------------------------------------------------------------
# Lectures et autre édition
# --------------------------------------------------------------------------

def reading_text(path):
    t = reference_text(path, 1, None)
    t = re.sub(r"(?<=\w)[-¬]\s+(?:«\s*)?(?=[a-zàâäéèêëîïôöûüç])", "", t)     # « Cou- longne »
    return re.sub(r"(?<=\w)«\s*(?=[a-zàâäéèêëîïôöûüç])", "", t)               # « Cou« longne »


def tokens_with_spans(text):
    ms = list(WORD.finditer(text))
    return [m.group(0) for m in ms], [m.span() for m in ms]


def wikisource_text(parent, first, last, cache, lang="fr"):
    """Texte des sous-pages de PARENT (« Livre_III/Chapitre_XC » …) de FIRST à LAST, mis en cache."""
    os.makedirs(cache, exist_ok=True)
    api = "https://%s.wikisource.org/w/index.php?title=%%s&action=render" % lang

    def get(title):
        fn = os.path.join(cache, re.sub(r"[^\w.-]", "_", title) + ".html")
        if os.path.exists(fn) and os.path.getsize(fn) > 3000:
            return open(fn, encoding="utf-8").read()
        for attempt in range(5):
            req = urllib.request.Request(api % urllib.parse.quote(title),
                                         headers={"User-Agent": "Prescel/0.1 (epub_temoins.py)"})
            try:
                data = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
            except Exception:
                data = ""
            if "mw-parser-output" in data and "Wikimedia Error" not in data:
                open(fn, "w", encoding="utf-8").write(data)
                time.sleep(0.5)
                return data
            time.sleep(3 * (attempt + 1))
        sys.exit("Wikisource : page illisible après 5 essais : %s" % title)

    index = get(parent)
    subs = []
    for m in re.finditer(r'href="[^"]*/wiki/(%s/[^"#?]+)"' % re.escape(urllib.parse.quote(parent, safe="/_")), index):
        t = urllib.parse.unquote(m.group(1))
        if t not in subs:
            subs.append(t)
    names = [s.rsplit("/", 1)[-1] for s in subs]
    key = lambda x: next((i for i, n in enumerate(names) if n.endswith("_" + x) or n == x), None)
    a = key(first) if first else 0
    b = key(last) if last else len(subs) - 1
    if a is None or b is None:
        sys.exit("Wikisource : chapitre %s ou %s introuvable parmi %d sous-pages" % (first, last, len(subs)))
    out = []
    for t in subs[a:b + 1]:
        page = get(t)
        page = re.sub(r"(?s)<style.*?</style>", "", page)
        i = page.find("mw-html-heading")
        page = page[i:] if i > 0 else page
        page = re.sub(r'(?s)<div class="footertemplate.*', "", page)
        page = re.sub(r'(?s)<div class="alineanegatif".*?</div>', "", page)
        page = re.sub(r'<span class="pagenum[^>]*></span>', " ", page)
        out.append(" ".join(html.unescape(re.sub(r"<[^>]+>", " ", p)) for p in re.findall(r"(?s)<p>(.*?)</p>", page)))
    print("Wikisource : %d sous-pages (%s → %s)" % (b - a + 1, names[a], names[b]))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Alignement
# --------------------------------------------------------------------------

def align(ms, ws, n=5):
    """Ancres (n-grammes de squelettes uniques des deux côtés, en ordre croissant), puis difflib entre elles."""
    def grams(seq):
        c = collections.Counter(tuple(seq[i:i + n]) for i in range(len(seq) - n + 1))
        return {g: i for g, i in ((tuple(seq[i:i + n]), i) for i in range(len(seq) - n + 1)) if c[g] == 1}
    gm, gw = grams(ms), grams(ws)
    pairs = sorted((gm[g], gw[g]) for g in gm.keys() & gw.keys())
    tails, idx, prev = [], [], [None] * len(pairs)
    for i, (_, b) in enumerate(pairs):
        j = bisect.bisect_left(tails, b)
        if j == len(tails):
            tails.append(b)
            idx.append(i)
        else:
            tails[j] = b
            idx[j] = i
        prev[i] = idx[j - 1] if j else None
    chain, i = [], (idx[-1] if idx else None)
    while i is not None:
        chain.append(pairs[i])
        i = prev[i]
    chain.reverse()
    ops, pk, pw = [], 0, 0
    for a, b in chain + [(len(ms), len(ws))]:
        if a < pk or b < pw:
            continue
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ms[pk:a], ws[pw:b], autojunk=False).get_opcodes():
            ops.append((tag, pk + i1, pk + i2, pw + j1, pw + j2))
        pk, pw = a, b
    return ops


class Witness:
    def __init__(self, name, text, mskel, mwords):
        self.name = name
        self.text = text
        self.words, self.spans = tokens_with_spans(text)
        ops = align(mskel, [skel(w) for w in self.words])
        n = len(mskel)
        self.m2w = [None] * n          # mot de l'EPUB → mot de la lecture (1 pour 1)
        self.split = {}                # mot de l'EPUB → plusieurs mots de la lecture (mots collés)
        self.ins = {}                  # position dans l'EPUB → mots de la lecture absents de l'EPUB
        self.dele = set()              # mots de l'EPUB absents de la lecture
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
                for k in range(i2 - i1):
                    self.m2w[i1 + k] = j1 + k
            elif tag == "insert":
                self.ins[i1] = (j1, j2)
            elif tag == "delete":
                self.dele.update(range(i1, i2))
            elif tag == "replace" and i2 - i1 < j2 - j1:
                # mots collés de l'EPUB : chaque mot doit être la concaténation d'une suite de mots lus
                j, ok, parts = j1, True, []
                for i in range(i1, i2):
                    target, acc, k = flat(mwords[i]), "", j
                    while k < j2 and len(acc) < len(target):
                        acc += flat(self.words[k])
                        k += 1
                    if acc != target:
                        ok = False
                        break
                    parts.append((i, j, k))
                    j = k
                if ok and j == j2:
                    for i, a, b in parts:
                        if b - a == 1:
                            self.m2w[i] = a
                        else:
                            self.split[i] = (a, b)
                elif j2 - j1 - (i2 - i1) <= 3:
                    for k in range(i2 - i1):
                        self.m2w[i1 + k] = j1 + k
                    self.ins[i2] = (j1 + (i2 - i1), j2)
        self.coverage = sum(x is not None for x in self.m2w) / max(1, n)

    def form(self, i):
        j = self.m2w[i]
        return None if j is None else self.words[j]

    def gap(self, i, n):
        """Texte de la lecture entre les mots alignés qui entourent le mot i de l'EPUB."""
        a = next((self.m2w[j] for j in range(i - 1, max(-1, i - 6), -1) if self.m2w[j] is not None), None)
        b = next((self.m2w[j] for j in range(i + 1, min(n, i + 6)) if self.m2w[j] is not None), None)
        if a is None or b is None:
            return None
        return self.text[self.spans[a][1]:self.spans[b][0]]


# --------------------------------------------------------------------------
# Décisions
# --------------------------------------------------------------------------

def decide(M, readings, other, known):
    n = len(M)
    fixes, marks = [], []            # (i, action, valeur, raison, lectures)
    # mots collés et substitutions
    for i, t in enumerate(M):
        m = t["w"]
        splits = [r.split.get(i) for r in readings]
        if all(splits):
            parts = [tuple(r.words[a:b]) for r, (a, b) in zip(readings, splits)]
            if all(tuple(map(norm, p)) == tuple(map(norm, parts[0])) for p in parts):
                # séparateurs réels des lectures : espace, trait d'union ou apostrophe ; une fin de ligne
                # (césure ?) ou deux lectures en désaccord laissent le cas à vérifier
                seps = set()
                for r, (a, b) in zip(readings, splits):
                    seps.add(tuple(re.sub(r"[ \t]+", " ", r.text[r.spans[k][1]:r.spans[k + 1][0]])
                                   for k in range(a, b - 1)))
                sep = seps.pop() if len(seps) == 1 else None
                ok = sep is not None and all(x in (" ", "-", "- ") for x in sep) and \
                    all(known(w) for w in parts[0])
                if ok:
                    val = parts[0][0] + "".join(("-" if x.startswith("-") else " ") + w
                                                for x, w in zip(sep, parts[0][1:]))
                    fixes.append((i, "remplacer", val, "mots collés", " | ".join(parts[0])))
                else:
                    marks.append((i, "mots collés ? les lectures donnent « %s »" % " ".join(parts[0])))
                continue
        forms = [r.form(i) for r in readings]
        if any(f is None for f in forms):
            continue
        if t.get("mark") and all(norm(f) == norm(m) for f in forms):
            fixes.append((i, "confirmer", m, "marque levée : toutes les lectures confirment", "—"))
            continue
        if any(norm(f) == norm(m) for f in forms):
            continue
        b = other.form(i) if other else None
        lectures = "%s ; %s" % (" ; ".join("%s : %s" % (r.name, f) for r, f in zip(readings, forms)),
                                ("autre édition : %s" % b) if b else "autre édition : —")
        if all(norm(f) == norm(forms[0]) for f in forms):
            r = forms[0]
            if (ROMAN.match(m) and not known(m)) or (ROMAN.match(r) and not known(r)):
                if not ROMAN_STRICT.match(m):
                    marks.append((i, "nombre romain mal lu ? " + lectures))
                continue
            if r[:1].isupper() != m[:1].isupper():
                marks.append((i, "majuscule différente : alignement douteux ? " + lectures))
            elif not known(r) and known(m):
                fixes.append((i, "remplacer-marqué", r, "forme rare ou coquille de l'imprimé", lectures))
            else:
                fixes.append((i, "remplacer", r, "toutes les lectures", lectures))
        elif not known(m):
            marks.append((i, "lectures en désaccord, forme inconnue ; " + lectures))
    # mots en trop : absents de toutes les lectures
    gone = sorted(set.intersection(*(r.dele for r in readings)))
    runs, cur = [], []
    for i in gone:
        if cur and i == cur[-1] + 1 and M[i]["f"] == M[cur[-1]]["f"]:
            cur.append(i)
        else:
            if cur:
                runs.append(cur)
            cur = [i]
    if cur:
        runs.append(cur)
    for run in runs:
        if len(run) == 1:
            i = run[0]
            w = M[i]["w"]
            prev_w = M[i - 1]["w"] if i > 0 else ""
            if ROMAN.match(prev_w) and norm(w) in ("x", "xx", "c", "e", "m", "o"):
                marks.append((i, "exposant d'un nombre romain ? (« %s %s » : %s%s ?)" % (prev_w, w, prev_w, w)))
            elif len(w) <= 2 or norm(w) in PARASITES:
                gaps = [r.gap(i, n) or "" for r in readings]
                num = sorted({d for g in gaps for d in re.findall(r"(?<![\d.])(\d{1,2})(?![\d.])", g)})
                if num:
                    marks.append((i, "lettre isolée absente des autres lectures, près de l'appel %s : appel de "
                                  "variante mal lu ?" % ", ".join(num)))
                else:
                    fixes.append((i, "supprimer", "", "lettre parasite", "absente de toutes les lectures"))
            else:
                marks.append((i, "mot absent de toutes les autres lectures (ajouté par l'OCR ?)"))
        else:
            marks.append((run, "passage absent de toutes les autres lectures (%d mots) : apparat mêlé au texte, "
                          "ligne répétée ?" % len(run)))
    # mots perdus : toutes les lectures ont le même mot en plus au même endroit
    common = set.intersection(*(set(r.ins) for r in readings))
    for pos in sorted(common):
        groups = [tuple(norm(w) for w in r.words[slice(*r.ins[pos])]) for r in readings]
        if not groups[0] or any(g != groups[0] for g in groups) or len(groups[0]) > 2:
            continue
        words = readings[0].words[slice(*readings[0].ins[pos])]
        if any(len(w) < 2 and w not in ("à", "À") for w in words) or any(norm(w) in PARASITES for w in words):
            continue
        if any(w.isupper() and len(w) > 1 for w in words):
            continue                                   # titre (NOTES, TABLE) hors des paragraphes lus
        prev = norm(M[pos - 1]["w"]) if pos > 0 else ""
        if prev.endswith(flat("".join(words))):
            continue                                   # moitié d'un mot coupé que l'EPUB a entier
        if len(words) == 1 and known(words[0]):
            fixes.append((pos, "insérer", words[0], "mot perdu", "présent dans toutes les lectures"))
        else:
            fixes.append((pos, "insérer-marqué", " ".join(words), "mots perdus (à vérifier)",
                          "présents dans toutes les lectures"))
    return fixes, marks


# --------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------

def esc_attr(s):
    return html.escape(s, quote=True)


def build_edits(M, digits, fixes, marks, raws):
    edits = collections.defaultdict(list)       # fichier → (début, fin, texte)
    for i, action, val, why, _ in fixes:
        if action in ("insérer", "insérer-marqué"):
            prev = M[i - 1]
            text = html.escape(val, quote=False)
            if action == "insérer-marqué":
                text = '<span class="a-verifier" title="ajouté d\'après toutes les lectures">%s</span>' % text
            edits[prev["f"]].append((prev["e"], prev["e"], " " + text))
            continue
        t = dict(M[i])
        if t.get("mark"):
            # ancienne marque sur ce seul mot : le cas est tranché, la marque tombe avec le mot, en une seule
            # modification (un chevauchement ne laisse jamais de balise orpheline)
            (o1, o2), (c1, c2) = t["mark"]
            if action == "confirmer":
                edits[t["f"]].append((o1, c2, html.escape(t["w"], quote=False)))
                continue
            t["s"], t["e"] = o1, c2
        if action == "confirmer":
            continue
        raw = raws[t["f"]]
        s0, e0 = t["s"], t["e"]
        while s0 > 0 and raw[s0 - 1].isdigit():
            s0 -= 1
        while e0 < len(raw) and raw[e0].isdigit():
            e0 += 1
        if (s0, e0) != (t["s"], t["e"]) and action in ("remplacer", "remplacer-marqué", "supprimer"):
            title = ("chiffre collé au mot « %s » (appel de variante ?) ; les lectures donnent « %s »"
                     % (raw[s0:e0], val or "∅"))
            edits[t["f"]].append((s0, e0, '<span class="a-verifier" title="%s">%s</span>'
                                  % (esc_attr(title), html.escape(val, quote=False) or raw[s0:e0])))
            continue
        if action == "remplacer":
            edits[t["f"]].append((t["s"], t["e"], html.escape(val, quote=False)))
        elif action == "remplacer-marqué":
            title = ("imprimé : « %s » (Google et Tesseract) au lieu de « %s » ; forme rare ou coquille de "
                     "l'édition : garder, ou corriger avec une note de transcription" % (val, t["w"]))
            edits[t["f"]].append((t["s"], t["e"], '<span class="a-verifier" title="%s">%s</span>'
                                  % (esc_attr(title), html.escape(val, quote=False))))
        elif action == "supprimer":
            edits[t["f"]].append((t["s"], t["e"], ""))
    for target, why in marks:
        run = target if isinstance(target, list) else [target]
        a, b = M[run[0]], M[run[-1]]
        if a["f"] != b["f"]:
            continue
        edits[a["f"]].append((a["s"], b["e"], ("<span class=\"a-verifier\" title=\"%s\">" % esc_attr(why), "</span>")))
    for d in digits:
        edits[d["f"]].append((d["s"], d["e"], ("<span class=\"a-verifier\" title=\"chiffre dans le récit : appel de "
                                               "variante en chiffre ordinaire ?\">", "</span>")))
    return edits


def apply_edits(raw, edits):
    """Du dernier au premier ; une modification qui en chevauche une autre est écartée."""
    out, last, done, dropped = raw, len(raw) + 1, 0, 0
    for s, e, rep in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        if e > last:
            dropped += 1
            continue
        if isinstance(rep, tuple):
            text = rep[0] + out[s:e] + rep[1]
        else:
            text = rep
            if rep == "" and out[s - 1:s] == " ":
                s -= 1                                   # supprimer aussi l'espace avant (mot supprimé)
        out = out[:s] + text + out[e:]
        last = s
        done += 1
    out = re.sub(r"(?<=[^\s>]) {2,}(?=[^\s<])", " ", out)       # espace double laissée par une suppression
    return out, done, dropped


def write_epub(z, raws, edits, out_path):
    stats = collections.Counter()
    with zipfile.ZipFile(out_path, "w") as zo:
        for info in sorted(z.infolist(), key=lambda i: i.filename != "mimetype"):
            data = z.read(info)
            if info.filename in edits:
                new, done, dropped = apply_edits(raws[info.filename], edits[info.filename])
                stats["faites"] += done
                stats["écartées (chevauchement)"] += dropped
                data = new.encode("utf-8")
            zo.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype"
                        else zipfile.ZIP_DEFLATED)
    return stats


def marks_per_page(path):
    """Marques a-verifier (anciennes et nouvelles) par page imprimée, dans l'EPUB écrit."""
    z = zipfile.ZipFile(path)
    labels = page_labels(z)
    count, order, page = collections.Counter(), [], ""
    for n in sorted(z.namelist()):
        if not n.endswith(("html", "htm")):
            continue
        for m in re.finditer(r'id="(page-\d+)"|<span class="a-verifier"', z.read(n).decode("utf-8")):
            if m.group(1):
                page = labels.get(m.group(1), m.group(1))
                if page not in order:
                    order.append(page)
            else:
                count[page] += 1
    return count, order


def context(M, i, k=5):
    return " ".join(t["w"] for t in M[max(0, i - k):i]), " ".join(t["w"] for t in M[i + 1:i + 1 + k])


def write_report(path, M, fixes, marks, digits, readings, other, scan, decalage, out_epub):
    def link(p):
        if not scan or not str(p).isdigit():
            return html.escape(str(p))
        return '<a href="%s">%s</a>' % (html.escape(scan.format(vue=int(p) + decalage, page=p)), html.escape(str(p)))
    per_page, pages_order = marks_per_page(out_epub)
    pages_order = [p for p in pages_order if str(p).isdigit()]
    rows_f = []
    for i, action, val, why, lect in fixes:
        a, b = context(M, i if not action.startswith("insérer") else i - 1, 5)
        old = "" if action.startswith("insérer") else M[i]["w"]
        if action.startswith("insérer"):
            a = " ".join(t["w"] for t in M[max(0, i - 5):i])
            b = " ".join(t["w"] for t in M[i:i + 5])
        rows_f.append("<tr><td>%s</td><td>%s</td><td><del>%s</del> → <ins>%s</ins></td><td>%s <b>[%s]</b> %s</td>"
                      "<td>%s</td></tr>" % (link(M[min(i, len(M) - 1)]["page"]), html.escape(why), html.escape(old),
                                            html.escape(val), html.escape(a), html.escape(val or "∅"), html.escape(b),
                                            html.escape(str(lect))))
    rows_m = []
    for target, why in marks:
        run = target if isinstance(target, list) else [target]
        a, b = context(M, run[0], 5)
        b = context(M, run[-1], 5)[1]
        rows_m.append("<tr><td>%s</td><td>%s <mark>%s</mark> %s</td><td>%s</td></tr>"
                      % (link(M[run[0]]["page"]), html.escape(a), html.escape(" ".join(M[j]["w"] for j in run)),
                         html.escape(b), html.escape(why)))
    pages = [p for p in pages_order]
    hot = sorted(((per_page[p], p) for p in pages if per_page[p]), key=lambda x: (-x[0], pages.index(x[1])))
    calm = [p for p in pages if not per_page[p]]
    cov = " ; ".join("%s : %.1f %% des mots alignés" % (r.name, 100 * r.coverage) for r in readings)
    if other:
        cov += " ; autre édition : %.1f %%" % (100 * other.coverage)
    doc = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Témoins — relecture ciblée</title>
<style>body{font-family:system-ui,sans-serif;margin:2em;max-width:72em}table{border-collapse:collapse;width:100%%}
td,th{border-bottom:1px solid #ddd;padding:.3em .5em;vertical-align:top;font-size:.92em}del{color:#a00}ins{color:#060;text-decoration:none;font-weight:600}
mark{background:#ffe58a}.pages span{display:inline-block;margin:.15em .3em}</style></head><body>
<h1>Relecture ciblée</h1><p>%s</p>
<ul><li>corrections faites : <b>%d</b> (%s)</li>
<li>passages marqués <code>a-verifier</code> : <b>%d</b> (dont %d chiffres dans le récit)</li>
<li>pages sans aucune marque (anciennes et nouvelles) : <b>%d</b> sur %d — aucun mot n'y est contesté par les lectures (la ponctuation et l'apparat ne sont pas contrôlés)</li></ul>
<h2>Pages à relire de près (nombre de marques)</h2><p class="pages">%s</p>
<h2>Corrections faites</h2><table><tr><th>Page</th><th>Cas</th><th>Correction</th><th>Contexte</th><th>Lectures</th></tr>%s</table>
<h2>À vérifier</h2><table><tr><th>Page</th><th>Passage</th><th>Pourquoi</th></tr>%s</table>
</body></html>""" % (html.escape(cov), len(fixes),
                     html.escape(", ".join("%s : %d" % kv for kv in collections.Counter(x[3] for x in fixes).most_common())),
                     len(marks) + len(digits), len(digits), len(calm), len(pages),
                     " ".join('<span>p. %s (%d)</span>' % (link(p), c) for c, p in hot),
                     "\n".join(rows_f), "\n".join(rows_m))
    open(path, "w", encoding="utf-8").write(doc)


def main():
    ap = argparse.ArgumentParser(description="Relecture ciblée : l'EPUB face à d'autres lectures du même livre.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", required=True, help="EPUB corrigé et marqué")
    ap.add_argument("--lecture", action="append", required=True,
                    help="autre lecture de la même édition (EPUB, texte, PDF) ; au moins deux, répétable")
    ap.add_argument("--nom", action="append", default=[], help="nom de chaque lecture, dans l'ordre (rapport)")
    ap.add_argument("--autre", help="texte d'une autre édition (indice seulement)")
    ap.add_argument("--wikisource", help="page Wikisource parente de l'autre édition (« Livre/Partie »)")
    ap.add_argument("--de", help="première sous-page Wikisource (fin du titre : « XC »)")
    ap.add_argument("--a", dest="a_", help="dernière sous-page Wikisource (« CXXXVIII »)")
    ap.add_argument("--recit-jusqua", default="",
                    help="identifiant où finit le récit (titre-4 : NOTES) ; les chiffres ne sont signalés qu'avant")
    ap.add_argument("--scan", default="", help="adresse d'une page du scan pour le rapport, avec {vue} ou {page}")
    ap.add_argument("--decalage-scan", type=int, default=0, help="vue du scan = page imprimée + ce nombre")
    ap.add_argument("--rapport", default="", help="rapport HTML (défaut : <sortie>-temoins.html)")
    ap.add_argument("--tsv", default="", help="liste des corrections et marques (défaut : <sortie>-temoins.tsv)")
    ap.add_argument("--wordlist", default="auto")
    opts = ap.parse_args()
    if len(opts.lecture) < 2:
        sys.exit("Il faut au moins deux autres lectures du même livre (--lecture deux fois).")

    z, raws, M, digits = read_master(opts.epub, opts.recit_jusqua)
    mskel = [skel(t["w"]) for t in M]
    mwords = [t["w"] for t in M]
    names = opts.nom + [os.path.basename(p) for p in opts.lecture[len(opts.nom):]]
    readings = []
    for name, p in zip(names, opts.lecture):
        r = Witness(name, reading_text(p), mskel, mwords)
        readings.append(r)
        print("%s : %d mots, %.1f %% des mots de l'EPUB alignés" % (name, len(r.words), 100 * r.coverage))
    other = None
    if opts.wikisource or opts.autre:
        if opts.wikisource:
            text = wikisource_text(opts.wikisource, opts.de, opts.a_,
                                   os.path.join(os.path.expanduser("~"), ".cache", "prescel", "wikisource"))
        else:
            text = reading_text(opts.autre) if not opts.autre.endswith(".html") else \
                html.unescape(re.sub(r"<[^>]+>", " ", open(opts.autre, encoding="utf-8").read()))
        other = Witness("autre édition", text, mskel, mwords)
        print("Autre édition : %d mots, %.1f %% des mots de l'EPUB alignés" % (len(other.words), 100 * other.coverage))

    wl = load_wordlist(opts.wordlist)
    words = {w.lower() for w in wl} if wl is not None else set()
    book = collections.Counter(norm(w) for w in mwords)
    known = lambda w: norm(w) in words or book[norm(w)] >= 2
    fixes, marks = decide(M, readings, other, known)
    edits = build_edits(M, digits, fixes, marks, raws)
    stats = write_epub(z, raws, edits, opts.output)

    base = os.path.splitext(opts.output)[0]
    tsv = opts.tsv or base + "-temoins.tsv"
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("page\tcas\tavant\taprès\tcontexte\tlectures\n")
        for i, action, val, why, lect in fixes:
            j = min(i, len(M) - 1)
            a, b = context(M, j)
            f.write("%s\t%s\t%s\t%s\t%s [] %s\t%s\n" % (M[j]["page"], why, "" if action.startswith("insérer") else M[i]["w"],
                                                       val, a, b, lect))
        for target, why in marks:
            run = target if isinstance(target, list) else [target]
            a, b = context(M, run[0])
            f.write("%s\tà vérifier\t%s\t\t%s [] %s\t%s\n" % (M[run[0]]["page"], " ".join(M[j]["w"] for j in run), a, b, why))
    rapport = opts.rapport or base + "-temoins.html"
    write_report(rapport, M, fixes, marks, digits, readings, other, opts.scan, opts.decalage_scan, opts.output)
    kinds = collections.Counter(x[3] for x in fixes)
    print("Corrections : %d (%s)" % (len(fixes), ", ".join("%s %d" % (k, v) for k, v in kinds.most_common())))
    print("Marques a-verifier ajoutées : %d (dont %d chiffres dans le récit)" % (len(marks) + len(digits), len(digits)))
    print("Modifications écrites : %d ; écartées (chevauchement) : %d" % (stats["faites"], stats["écartées (chevauchement)"]))
    print("EPUB : %s\nRapport : %s\nListe : %s" % (opts.output, rapport, tsv))


if __name__ == "__main__":
    main()
