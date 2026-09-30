#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_modernise.py — Modernise l'orthographe d'un livre des XVIᵉ-XVIIIᵉ siècles,
sur le modèle de epub_longs.py : une liste TSV des corrections, modifiable,
les cas sûrs appliqués d'office, les cas douteux laissés au choix.

Trois modes :

  --mode oi     imparfaits et conditionnels en -ois / -oit / -oient
                (« il estoit » → « il était », « ils auroient » → « ils auraient »).
                Sources : dictionnaires/verbes_oi.py (formes connues, avec leur
                graphie moderne complète), puis la règle -oi- → -ai- quand la forme
                obtenue est un mot français. Jamais d'office : les mots où « oi »
                est légitime (« croit », « soit », « mois », « fois », « droit »,
                « exploit »…) et les noms propres (« François »).

  --mode ez     pluriels anciens en -ez (« bontez » → « bontés », « armez » → « armés »),
                sauf la 2ᵉ personne du pluriel : après « vous » (« vous avez », « vous les
                envoyez »), à l'impératif avec pronom (« allez-vous ») ou en tête de phrase
                (« Venez ») quand la forme est aussi un verbe moderne. Jamais : « nez »,
                « chez », « assez ».

  --mode vocab  vocabulaire (« luy » → « lui », « mesme » → « même », « faict » → « fait »,
                « aussi tost » → « aussitôt ») : dictionnaires/vocabulaire_17_18.py.
                Laissé au choix quand la graphie ancienne est aussi un mot moderne
                (« teste » : tête, ou le verbe tester ?).

Liste TSV : appliquer  forme_lue  correction  occurrences  occ_correction  remarque
Avec --use-tsv, les choix déjà faits sont repris.

La casse est respectée (Estoit → Était, ESTOIT → ÉTAIT) ; seuls les mots listés
changent : la ponctuation du texte est vérifiée avant/après.

Usage :
  python3 epub_modernise.py livre.epub -o livre-oi.epub --mode oi --tsv livre-oi.tsv --wordlist auto
  python3 epub_modernise.py livre.epub -o livre-mod.epub --mode vocab --tsv livre-moderne.tsv --use-tsv
"""

import argparse
import collections
import csv
import os
import re
import runpy
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from epub_longs import (Doc, TSV_HEAD, decode_text, fix_doctype, get_attr, load_wordlist,  # noqa: E402
                        read_tsv, resolve, text_holders, write_tsv, EPUB2)
import xml.etree.ElementTree as ET  # noqa: E402

LETTERS = "A-Za-zÀ-ÖØ-öø-ÿœŒæÆ"
WORD = re.compile(r"[%s]+" % LETTERS)
OI_END = re.compile(r"^(.+?)(ois|oit|oient)$")

# Niveau 2 et 3 : formes fréquentes (complètent dictionnaires/verbes_oi.py)
OI_BUILTIN = {
    "estois": "étais", "estoit": "était", "estoient": "étaient",
    "etois": "étais", "etoit": "était", "etoient": "étaient",
    "avois": "avais", "avoit": "avait", "avoient": "avaient",
    "faisois": "faisais", "faisoit": "faisait", "faisoient": "faisaient",
    "disois": "disais", "disoit": "disait", "disoient": "disaient",
    "pouvois": "pouvais", "pouvoit": "pouvait", "pouvoient": "pouvaient",
    "devois": "devais", "devoit": "devait", "devoient": "devaient",
    "voulois": "voulais", "vouloit": "voulait", "vouloient": "voulaient",
    "savois": "savais", "savoit": "savait", "savoient": "savaient",
    "aurois": "aurais", "auroit": "aurait", "auroient": "auraient",
    "serois": "serais", "seroit": "serait", "seroient": "seraient",
    "ferois": "ferais", "feroit": "ferait", "feroient": "feraient",
    "irois": "irais", "iroit": "irait", "iroient": "iraient",
    "viendrois": "viendrais", "viendroit": "viendrait", "viendroient": "viendraient",
}
# « oi » légitime en français moderne : jamais changé d'office, même sans liste de mots
OI_KEEP = set("""
mois fois trois bois lois rois vois voit crois croit dois doit sois soit bois boit reçois reçoit
droit droits endroit endroits étroit adroit maladroit exploit exploits toit toits froid
emploi emplois choix poids pois noix voix croix foi soi moi toi loi roi quoi pourquoi
aperçois aperçoit conçois conçoit déçoit perçoit reçoivent doivent voient croient soient
""".split())


# Mots en -ez qui ne sont pas des pluriels anciens en -és
EZ_KEEP = set("nez chez assez rez lez sez raz".split())
# Pronoms qui peuvent s'intercaler entre « vous » et le verbe : « vous ne les avez »
VOUS_BEFORE = re.compile(r"\bvous(?:\s+|['’])(?:(?:ne|n['’]|pas|le|la|les|l['’]|lui|leur|en|y|me|m['’]|"
                         r"te|t['’]|se|s['’]|nous)(?:\s+|(?<=['’])))*$", re.I)


def ez_is_verb_here(m, source_is_word):
    """Occurrence de « -ez » à garder : 2ᵉ personne du pluriel (« vous avez », « vous les
    envoyez »), impératif avec pronom (« allez-vous », « donnez-le ») ou en tête de phrase
    (« Venez ») quand la forme est aussi un verbe moderne."""
    s, a, b = m.string, m.start(), m.end()
    if VOUS_BEFORE.search(s[max(0, a - 40):a]):
        return True
    if b < len(s) and s[b] in "-‑":
        return True
    if re.match(r"\s+vous\b", s[b:b + 8], re.I):
        return True                               # inversion sans trait : « où allez vous ? »
    if source_is_word and m.group(0)[:1].isupper() and re.search(r"(?:^|[.!?:«»\"“]\s*)$", s[max(0, a - 3):a]):
        return True
    return False


def load_dict(path, name_hint):
    """Premier dictionnaire (variable en MAJUSCULES) d'un fichier Python."""
    ns = runpy.run_path(path)
    for k, v in ns.items():
        if k.isupper() and isinstance(v, dict):
            return {a.lower(): b for a, b in v.items() if isinstance(a, str) and isinstance(b, str)
                    and a.lower() != b.lower()}
    raise SystemExit("Aucun dictionnaire (%s) dans %s" % (name_hint, path))


def match_case(orig, new):
    if len(orig) > 1 and orig.isupper():
        return new.upper()
    if orig[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def skeleton(s):
    """Ce qui ne doit pas bouger : la ponctuation (lettres, traits, apostrophes et blancs exclus)."""
    return re.sub(r"[\w'’\-\s]", "", s)


# --------------------------------------------------------------------------
# Propositions
# --------------------------------------------------------------------------

def book_counts(docs):
    counts, caps = collections.Counter(), collections.Counter()
    text = []
    for d in docs:
        t = "".join(d.body.itertext())
        text.append(t)
        for m in WORD.finditer(t):
            w = m.group(0)
            counts[w.lower()] += 1
            # majuscule hors début de phrase : nom propre probable
            before = t[max(0, m.start() - 3):m.start()]
            if w[:1].isupper() and not re.search(r"[.!?»]\s*$|^\s*$", before):
                caps[w.lower()] += 1
    return counts, caps, "\n".join(text)


def propose_oi(counts, caps, wordlist, verbs):
    rows = []
    for w, n in counts.items():
        m = OI_END.match(w)
        if not m or len(w) < 4:
            continue
        stem, end = m.groups()
        target = verbs.get(w) or OI_BUILTIN.get(w)
        from_dict = target is not None
        if target is None:
            target = stem + {"ois": "ais", "oit": "ait", "oient": "aient"}[end]
        if not from_dict and wordlist is not None and target not in wordlist and target.endswith("ait") \
                and target[:-3] + "aît" in wordlist:
            target = target[:-3] + "aît"      # « reconnoit » → « reconnaît », « paroit » → « paraît »
        nt = counts.get(target, 0)
        modern_old = w in OI_KEEP or (wordlist is not None and w in wordlist)
        if modern_old and not from_dict:
            continue            # « trois », « fois », « droit » : pas un imparfait, rien à proposer
        if modern_old:
            ok, why = 0, "« %s » existe aussi en français moderne : à vérifier au cas par cas" % w
        elif caps.get(w, 0) >= max(2, 0.6 * n):
            ok, why = 0, "surtout avec une majuscule : nom propre ?"
        elif from_dict:
            ok, why = 1, "dictionnaire des verbes"
        elif wordlist is not None and target in wordlist:
            ok, why = 1, "règle -oi- → -ai-"
        else:
            ok, why = 0, "« %s » inconnu : forme à vérifier" % target
        rows.append({"appliquer": str(ok), "forme_lue": w, "correction": target,
                     "occurrences": str(n), "occ_correction": str(nt), "remarque": why})
    rows.sort(key=lambda r: (-int(r["occurrences"]), r["forme_lue"]))
    return rows


def propose_ez(counts, caps, wordlist, plurals=None):
    """Pluriels anciens en -ez : « bontez » → « bontés », « armez » → « armés »."""
    rows = []
    for w, n in counts.items():
        if not w.endswith("ez") or len(w) < 4 or w in EZ_KEEP:
            continue
        if plurals and w in plurals:
            rows.append({"appliquer": "1", "forme_lue": w, "correction": plurals[w],
                         "occurrences": str(n), "occ_correction": str(counts.get(plurals[w], 0)),
                         "remarque": "dictionnaire des pluriels"})
            continue
        target = w[:-2] + "és"
        if w.endswith("iez") and wordlist is not None and target not in wordlist and \
                w[:-3] + "yés" in wordlist:
            target = w[:-3] + "yés"             # « envoiez » → « envoyés »
        known = (wordlist is not None and target in wordlist) or counts.get(target, 0) >= 2
        verb = wordlist is not None and w in wordlist
        if not known and verb:
            continue                             # « aviez », « étiez » : verbes, rien à proposer
        if caps.get(w, 0) >= max(2, 0.6 * n):
            ok, why = 0, "surtout avec une majuscule : nom propre ?"
        elif not known:
            ok, why = 0, "« %s » inconnu : forme à vérifier" % target
        elif verb:
            ok, why = 1, "aussi un verbe : gardé après « vous », à l'impératif"
        else:
            ok, why = 1, ""
        rows.append({"appliquer": str(ok), "forme_lue": w, "correction": target,
                     "occurrences": str(n), "occ_correction": str(counts.get(target, 0)), "remarque": why})
    rows.sort(key=lambda r: (-int(r["occurrences"]), r["forme_lue"]))
    return rows


def propose_vocab(counts, caps, text, wordlist, vocab):
    rows = []
    low = text.lower().replace("’", "'")
    for old, new in vocab.items():
        if re.fullmatch(r"[%s]+" % LETTERS, old):
            n = counts.get(old, 0)
        else:
            n = len(re.findall(r"(?<![%s])%s(?![%s])" % (LETTERS, re.escape(old), LETTERS), low))
        if not n:
            continue
        nt = counts.get(new.lower(), 0) if re.fullmatch(r"[%s]+" % LETTERS, new) else 0
        if wordlist is not None and old in wordlist:
            ok, why = 0, "« %s » existe aussi en français moderne : à vérifier" % old
        else:
            ok, why = 1, ""
        rows.append({"appliquer": str(ok), "forme_lue": old, "correction": new,
                     "occurrences": str(n), "occ_correction": str(nt), "remarque": why})
    rows.sort(key=lambda r: (-int(r["occurrences"]), r["forme_lue"]))
    return rows


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def build_replacer(mapping, counts_out, ez_guard=None, kept=None):
    """Fonction de remplacement : expressions (« aussi tost ») d'abord, puis mots seuls."""
    phrases = sorted((k for k in mapping if not re.fullmatch(r"[%s]+" % LETTERS, k)), key=len, reverse=True)
    words = {k: v for k, v in mapping.items() if re.fullmatch(r"[%s]+" % LETTERS, k)}
    phrase_re = None
    if phrases:
        alts = "|".join(re.escape(p).replace("'", "['’]").replace(r"\ ", r"\s+") for p in phrases)
        phrase_re = re.compile(r"(?<![%s])(%s)(?![%s])" % (LETTERS, alts, LETTERS), re.I)

    def repl_phrase(m):
        key = re.sub(r"\s+", " ", m.group(0).lower().replace("’", "'"))
        new = mapping.get(key)
        if new is None:
            return m.group(0)
        counts_out[key] += 1
        return match_case(m.group(0), new)

    def repl_word(m):
        w = m.group(0)
        new = words.get(w.lower())
        if new is None:
            return w
        if ez_guard is not None and w.lower().endswith("ez") and ez_is_verb_here(m, w.lower() in ez_guard):
            if kept is not None:
                kept[w.lower()] += 1
            return w
        counts_out[w.lower()] += 1
        return match_case(w, new)

    def apply(s):
        if phrase_re is not None:
            s = phrase_re.sub(repl_phrase, s)
        return WORD.sub(repl_word, s)
    return apply


def apply_doc(doc, replace):
    changed = False
    for holder, attr in text_holders(doc.body):
        s = getattr(holder, attr)
        if not s:
            continue
        ns = replace(s)
        if ns != s:
            if skeleton(ns) != skeleton(s):
                raise SystemExit("ARRÊT : ponctuation modifiée dans %s ; rien n'a été écrit." % doc.path)
            setattr(holder, attr, ns)
            changed = True
    return changed


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Modernisation : imparfaits en oi, vocabulaire ancien.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB modernisé (défaut : en place)")
    ap.add_argument("--mode", choices=["oi", "ez", "vocab"], required=True)
    ap.add_argument("--tsv", required=True, help="liste des corrections (créée ou relue)")
    ap.add_argument("--use-tsv", action="store_true", help="respecter les choix d'un TSV existant")
    ap.add_argument("--no-apply", action="store_true", help="liste seulement, rien n'est corrigé")
    ap.add_argument("--wordlist", help="liste de mots français (fichier ou « auto »)")
    ap.add_argument("--dict", help="dictionnaire Python à utiliser (défaut : dictionnaires/…)")
    opts = ap.parse_args()

    dict_path = opts.dict or os.path.join(HERE, "dictionnaires",
                                          "verbes_oi.py" if opts.mode == "oi" else "vocabulaire_17_18.py")
    if opts.mode == "ez" and not opts.dict:
        dict_path = os.path.join(HERE, "dictionnaires", "pluriels_ez.py")
    table = load_dict(dict_path, opts.mode) if dict_path and os.path.exists(dict_path) else {}
    if not table and opts.mode == "vocab":
        sys.exit("Dictionnaire de vocabulaire introuvable : %s" % dict_path)

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(zin.namelist())
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(zin.read(opf_path))[0]
        ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf)
        EPUB2[0] = not (ver and ver.group(1).startswith("3"))
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

        counts, caps, text = book_counts(docs)
        wordlist = load_wordlist(opts.wordlist)
        if opts.mode == "oi":
            rows = propose_oi(counts, caps, wordlist, table)
        elif opts.mode == "ez":
            rows = propose_ez(counts, caps, wordlist, table)
        else:
            rows = propose_vocab(counts, caps, text, wordlist, table)
        if opts.no_apply:
            for r in rows:
                r["appliquer"] = "0"
        if opts.use_tsv and os.path.exists(opts.tsv):
            old = {r["forme_lue"]: r for r in read_tsv(opts.tsv)}
            fresh = {r["forme_lue"]: r for r in rows}
            merged = []
            for w, r in old.items():
                if w in fresh:
                    r["occurrences"], r["occ_correction"] = fresh[w]["occurrences"], fresh[w]["occ_correction"]
                    merged.append(r)
            new = [r for w, r in fresh.items() if w not in old]
            for r in new:
                r["remarque"] = ("nouveau ; " + r["remarque"]).rstrip(" ;")
            rows = merged + new
            print("Choix repris de %s (%d formes, %d nouvelles)" % (opts.tsv, len(old), len(new)))
        write_tsv(opts.tsv, rows)

        chosen = {r["forme_lue"]: r["correction"] for r in rows if r.get("appliquer", "0").strip() == "1"}
        pending = [r for r in rows if r.get("appliquer", "0").strip() != "1"]
        label = {"oi": "Imparfaits et conditionnels en oi", "ez": "Pluriels en -ez",
                 "vocab": "Vocabulaire ancien"}[opts.mode]
        print("%s : %d formes (%d occurrences) — %d à appliquer, %d laissées au choix"
              % (label, len(rows), sum(int(r["occurrences"]) for r in rows), len(chosen), len(pending)))
        print("Liste : %s" % opts.tsv)

        counts_out, kept = collections.Counter(), collections.Counter()
        guard = None
        if opts.mode == "ez":
            guard = {w for w in chosen if wordlist is None or w in wordlist}
        replace = build_replacer(chosen, counts_out, guard, kept)
        new_data = {}
        for d in docs:
            if apply_doc(d, replace) or fix_doctype(d.prefix) != d.prefix:
                new_data[d.path] = d.serialize()
        print("Mots modernisés : %d" % sum(counts_out.values()))
        if kept:
            print("Gardés tels quels (verbe : « vous … », impératif) : %d occurrences" % sum(kept.values()))
        for w, n in counts_out.most_common(12):
            print("  %-18s → %-18s %5d" % (w, chosen.get(w, "?"), n))
        if pending:
            print("Laissés tels quels (à décider dans la liste) :")
            for r in pending[:12]:
                print("  %-18s → %-18s %5s   %s" % (r["forme_lue"], r["correction"], r["occurrences"], r["remarque"]))

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
