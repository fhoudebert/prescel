#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_longs.py — Corrige le « s long » (ſ) que l'OCR a lu « f » dans les
imprimés anciens : « eft » → « est », « auffi » → « aussi », « chofes » →
« choses », « faifoit » → « faisoit »… (et « ß » → « ss »).

Le livre sert de dictionnaire : une correction n'est proposée que si la forme
en « s » existe ailleurs dans le livre (au moins 2 fois), ou dans une liste
de mots fournie (--wordlist). Toutes les positions de « f » sont essayées :
« faifoit » donne « faisoit », pas « saisoit ».

Chaque correction est rangée dans un fichier TSV modifiable :
    appliquer  forme_lue  correction  occurrences  occ_correction  remarque
  * 1 = appliquée ; 0 = laissée telle quelle.
  * Par défaut, 1 pour les corrections sûres ; 0 quand la forme lue est aussi
    un vrai mot (« font »/« sont », « fait »/« sait », « forte »/« sorte »…)
    ou quand elle est bien plus fréquente que la correction.
Avec --use-tsv, les choix du fichier existant sont respectés (les nouvelles
formes y sont ajoutées avec leur choix par défaut).

Le texte est vérifié : seules des lettres f → s (et ß → ss) changent.

Usage :
  python3 epub_longs.py livre.epub -o livre-s.epub --tsv livre-s-long.tsv
  python3 epub_longs.py livre.epub -o livre-s.epub --tsv livre-s-long.tsv --use-tsv
  python3 epub_longs.py livre.epub --tsv livre-s-long.tsv --propose-only
"""

import argparse
import collections
import csv
import html
import html.entities
import itertools
import os
import posixpath
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote

XHTML_NS = "http://www.w3.org/1999/xhtml"
for _p, _u in (("", XHTML_NS), ("svg", "http://www.w3.org/2000/svg"),
               ("xlink", "http://www.w3.org/1999/xlink"), ("epub", "http://www.idpf.org/2007/ops"),
               ("m", "http://www.w3.org/1998/Math/MathML")):
    ET.register_namespace(_p, _u)

WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿœŒæÆßſ]+")
TSV_HEAD = ["appliquer", "forme_lue", "correction", "occurrences", "occ_correction", "remarque"]

# Formes en « f » qui sont aussi de vrais mots : jamais corrigées d'office.
COLLISIONS = set("""
font fait fais foi fois fort forts forte fortes fuite fuites fuis fuit fuir falut faut
faute fautes fauter fera ferai feras ferez ferons feront feroit feroient ferois ferions
ferment fervent fervente fol fols folle fou fous fable fables fain faine fac fec fecond
fonde fonder fondé fondez fonder foule foules fouler fouler fûr fin fins fil fils fille
fier fiers fiere fieres fixe fûre fonge fage feu feux fond fonds fer fers fête fêtes
fire fis fit fît firent fut fût furent fus fusse fussent faire faites faite faits fit
force forces forcer forcé forcée forcez fosse faisons faisois faisoit faisoient faisant faisait faisaient fausse faussé feint fente fixe folie
fouler fondre fondu forcé forme formes fosse fossé
""".split())


def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def X(tag):
    return "{%s}%s" % (XHTML_NS, tag)


def resolve(base, href):
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(href)))


def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8", data[:3]
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    enc = m.group(1).decode("ascii") if m else "utf-8"
    return data.decode(enc), enc, b""


def get_attr(tag, name):
    m = re.search(r"""\s%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % re.escape(name), tag, re.I)
    return None if not m else (m.group(1) if m.group(1) is not None else m.group(2))


def replace_named_entities(text):
    def rep(m):
        if m.group(1) in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        cp = html.entities.name2codepoint.get(m.group(1))
        return "&#%d;" % cp if cp else m.group(0)
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", rep, text)


class Doc:
    def __init__(self, path, text, enc, bom):
        self.path, self.enc, self.bom = path, enc, bom
        m = re.search(r"<(?:[\w-]+:)?html\b", text)
        self.prefix = text[:m.start()] if m else '<?xml version="1.0" encoding="utf-8"?>\n'
        self.root = ET.fromstring(replace_named_entities(text).encode("utf-8"))
        self.body = self.root.find(X("body"))

    def serialize(self):
        out = ET.tostring(self.root, encoding="unicode")
        return self.bom + (self.prefix.rstrip() + "\n" + out + "\n").encode(self.enc, "xmlcharrefreplace")


def text_holders(body):
    """(élément, attribut) de chaque nœud de texte hors script/style."""
    out = []

    def walk(el):
        if lname(el) in ("script", "style"):
            return
        out.append((el, "text"))
        for ch in el:
            walk(ch)
            out.append((ch, "tail"))
    walk(body)
    return out


def normalized(s):
    """Pour la vérification : f, s, ſ confondus ; ß compté comme deux s."""
    s = "".join(s.split())
    return s.replace("ß", "ss").replace("ſ", "s").replace("f", "s")


# --------------------------------------------------------------------------
# Propositions
# --------------------------------------------------------------------------

WORDLIST_URL = "https://raw.githubusercontent.com/words/an-array-of-french-words/master/index.json"
# Débuts de mot qui n'existent pas en français : « fleur » ne peut pas être « sleur »
BAD_START = re.compile(r"^s[lrdbgvnmfhzkqwcpj]")


def load_wordlist(spec):
    """Liste de mots : fichier (un mot par ligne ou .dic Hunspell) ou « auto »
    (liste française libre téléchargée une fois dans ~/.cache/prescel)."""
    if not spec:
        return None
    path = spec
    if spec == "auto":
        path = os.path.join(os.path.expanduser("~"), ".cache", "prescel", "mots-fr.txt")
        if not os.path.exists(path):
            try:
                import json
                import urllib.request
                req = urllib.request.Request(WORDLIST_URL, headers={"User-Agent": "Prescel"})
                words = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(sorted({w.lower() for w in words})) + "\n")
                print("Liste de mots français téléchargée : %s (%d mots)" % (path, len(words)))
            except Exception as e:
                print("Avertissement : liste de mots français indisponible (%s) ; "
                      "seule la liste intégrée des mots ambigus est utilisée." % e)
                return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return {l.split("/")[0].strip().lower() for l in f if l.strip()}


def best_s_form(word, vocab, wordlist, min_count):
    """Meilleure forme en « s » d'un mot lu avec des « f » (minuscules)."""
    if "ß" in word or "ſ" in word:
        cand = word.replace("ß", "ss").replace("ſ", "s")
        return cand if (vocab.get(cand, 0) >= min_count or (wordlist and cand in wordlist)) else None
    pos = [i for i, c in enumerate(word) if c == "f"]
    if not pos or len(pos) > 5:
        return None
    best, best_n = None, 0
    for k in range(1, len(pos) + 1):
        for combo in itertools.combinations(pos, k):
            cand = list(word)
            for i in combo:
                cand[i] = "s"
            cand = "".join(cand)
            if "fs" in cand or "sf" in cand or BAD_START.match(cand):
                continue            # forme elle-même mal lue (« afsurance »), ou impossible
            n = vocab.get(cand, 0)       # le livre seul décide de la forme corrigée
            # à fréquence égale, on préfère la forme qui garde le moins de « f »
            if n >= min_count and (n > best_n or (n == best_n and best and
                                                  cand.count("f") < best.count("f"))):
                best, best_n = cand, n
    return best


def propose(vocab, wordlist, min_count):
    rows = []
    for w, n in vocab.items():
        if len(w) < 2 or not ("f" in w or "ß" in w or "ſ" in w):
            continue
        s = best_s_form(w, vocab, wordlist, min_count)
        if not s:
            continue
        ns = vocab.get(s, 0)
        # Vrai mot : liste intégrée (toujours ambigu) ou liste de mots (ambigu sauf si la
        # forme en « s » est au moins aussi fréquente dans le livre : « fur »/« sur »)
        real = w in COLLISIONS or (wordlist is not None and w in wordlist and ns < n)
        if real:
            ok, why = 0, "« %s » est aussi un mot : à vérifier au cas par cas" % w
        elif ns * 3 < n and (len(w) < 5 or ns < 5):
            # « force » (32) → « sorce » (2) : la correction est elle-même une erreur rare
            ok, why = 0, "forme lue bien plus fréquente que la correction"
        else:
            ok, why = 1, ""
        rows.append({"appliquer": str(ok), "forme_lue": w, "correction": s,
                     "occurrences": str(n), "occ_correction": str(ns), "remarque": why})
    rows.sort(key=lambda r: (-int(r["occurrences"]), r["forme_lue"]))
    return rows


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f, delimiter="\t") if r.get("forme_lue")]


def write_tsv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TSV_HEAD, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def fix_token(tok, target):
    """Applique la correction en respectant la casse du mot lu."""
    if "ß" in tok or "ſ" in tok:
        return tok.replace("ß", "ss").replace("ſ", "s")
    if len(tok) != len(target):
        return tok
    out = []
    for c, t in zip(tok, target):
        out.append("s" if c == "f" and t == "s" else c)
    return "".join(out)


def apply_doc(doc, mapping, counts):
    changed = False
    for holder, attr in text_holders(doc.body):
        s = getattr(holder, attr)
        if not s:
            continue

        def rep(m):
            tok = m.group(0)
            tgt = mapping.get(tok.lower())
            if tgt is None:
                return tok
            new = fix_token(tok, tgt)
            if new != tok:
                counts[tok.lower()] += 1
            return new
        ns = WORD.sub(rep, s)
        if ns != s:
            setattr(holder, attr, ns)
            changed = True
    return changed


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Corrige le s long lu « f » par l'OCR.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB corrigé (défaut : en place)")
    ap.add_argument("--tsv", required=True, help="liste des corrections (créée ou relue)")
    ap.add_argument("--use-tsv", action="store_true",
                    help="respecter les choix d'un TSV existant (colonne « appliquer »)")
    ap.add_argument("--no-apply", action="store_true",
                    help="n'appliquer aucune correction automatiquement (liste seulement)")
    ap.add_argument("--propose-only", action="store_true", help="écrire le TSV sans produire d'EPUB")
    ap.add_argument("--wordlist", help="liste de mots de référence (un par ligne, ou .dic Hunspell), "
                    "ou « auto » : liste française libre téléchargée une fois ; une forme en « f » "
                    "qui y figure (« fleur », « force ») n'est jamais corrigée d'office")
    ap.add_argument("--min-count", type=int, default=2,
                    help="occurrences minimales de la forme en « s » dans le livre (défaut 2)")
    opts = ap.parse_args()

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(zin.namelist())
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(zin.read(opf_path))[0]
        docs = []
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if (get_attr(m.group(0), "media-type") or "").lower() != "application/xhtml+xml":
                continue
            p = resolve(opf_path, get_attr(m.group(0), "href") or "")
            if p in names:
                try:
                    d = Doc(p, *decode_text(zin.read(p)))
                except ET.ParseError as e:
                    print("Avertissement : %s ignoré (%s)" % (p, e), file=sys.stderr)
                    continue
                if d.body is not None:
                    docs.append(d)

        vocab = collections.Counter()
        for d in docs:
            for w in WORD.findall("".join(d.body.itertext())):
                vocab[w.lower()] += 1
        wordlist = load_wordlist(opts.wordlist)

        rows = propose(vocab, wordlist, opts.min_count)
        if opts.no_apply:
            for r in rows:
                r["appliquer"] = "0"
        if opts.use_tsv and os.path.exists(opts.tsv):
            old = {r["forme_lue"]: r for r in read_tsv(opts.tsv)}
            fresh = {r["forme_lue"]: r for r in rows}
            merged = []
            for w, r in old.items():          # choix de l'utilisateur conservés
                if w in fresh:
                    r["occurrences"] = fresh[w]["occurrences"]
                    r["occ_correction"] = fresh[w]["occ_correction"]
                merged.append(r)
            new = [r for w, r in fresh.items() if w not in old]
            for r in new:
                r["remarque"] = ("nouveau ; " + r["remarque"]).rstrip(" ;")
            rows = merged + new
            print("Choix repris de %s (%d formes, %d nouvelles)" % (opts.tsv, len(old), len(new)))
        write_tsv(opts.tsv, rows)

        chosen = {r["forme_lue"]: r["correction"] for r in rows if r.get("appliquer", "0").strip() == "1"}
        pending = [r for r in rows if r.get("appliquer", "0").strip() != "1"]
        total_f = sum(int(r["occurrences"] or 0) for r in rows)
        print("Formes repérées : %d (%d occurrences) — %d à appliquer, %d laissées au choix"
              % (len(rows), total_f, len(chosen), len(pending)))
        print("Liste : %s" % opts.tsv)
        if opts.propose_only:
            return

        counts = collections.Counter()
        new_data = {}
        for d in docs:
            before = normalized("".join(d.body.itertext()))
            if apply_doc(d, chosen, counts):
                if normalized("".join(d.body.itertext())) != before:
                    sys.exit("ARRÊT : le texte de %s a changé au-delà de f → s ; rien n'a été écrit." % d.path)
                new_data[d.path] = d.serialize()

        print("Mots corrigés : %d" % sum(counts.values()))
        for w, n in counts.most_common(15):
            print("  %-18s → %-18s %5d" % (w, chosen[w], n))
        if pending:
            print("Laissés tels quels (à décider dans la liste) :")
            for r in pending[:12]:
                print("  %-18s → %-18s %5s   %s" % (r["forme_lue"], r["correction"], r["occurrences"],
                                                   r["remarque"]))

        out_path = opts.output or src
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w") as zout:
                for info in sorted(infos, key=lambda i: i.filename != "mimetype"):
                    data = new_data.get(info.filename)
                    if data is None:
                        data = zin.read(info)
                    if info.filename == "mimetype":
                        info.compress_type = zipfile.ZIP_STORED
                    zout.writestr(info, data, compress_type=info.compress_type)
            shutil.copymode(src, tmp)
            os.replace(tmp, out_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    print("EPUB écrit : %s" % out_path)


if __name__ == "__main__":
    main()
