#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_errata.py — Applique au texte les corrections de l'errata imprimé du livre.

L'errata (« ERRATA. » suivi d'un tableau « AU LIEU DE | LISEZ ») est lu dans l'EPUB
lui-même :

    P. 24, l. 30,   sont      font
    P. 74, l. 2,    tout      toute

Chaque correction est cherchée sur la page indiquée (ancres de page et liste des
pages du toc.ncx), dans le texte courant seulement (variantes en bas de page et
errata exclus) :
  - une seule occurrence sur la page : elle est corrigée ;
  - plusieurs : le numéro de ligne départage (position estimée dans la page) ; si
    deux occurrences restent trop proches, rien n'est fait ;
  - aucune, ou ligne d'errata illisible : rien n'est fait.
Tout est listé : ce qui est appliqué, et ce qui reste à faire à la main (avec le
lien vers la page scannée quand l'EPUB le connaît).

L'errata reste dans le livre (fidélité à l'imprimé) ; --retirer le supprime une fois
les corrections faites. Pour Gutenberg, le signaler dans la note de transcription
(epub_gutenberg.py --note "Les corrections indiquées dans l'errata ont été faites.").

Usage :
  python3 epub_errata.py livre.epub -o livre-errata.epub
  python3 epub_errata.py livre.epub -o livre-errata.epub --lignes 33 --retirer
"""

import argparse
import html
import os
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from epub_longs import (Doc, EPUB2, decode_text, fix_doctype, get_attr, resolve,  # noqa: E402
                        text_holders)

ENTRY = re.compile(r"^\s*P(?:age)?\s*\.?\s*(\d+)\s*(?:[,.]\s*[l1Ii|]\s*\.?\s*(\d+))?\s*[,.]?\s*$")
HEADER = re.compile(r"(?i)au\s+lieu\s+de|li?sez|usez")


def lname(el):
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def text_of(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def classes(el):
    return set((el.get("class") or "").split())


def page_labels(z, names):
    """id d'ancre → numéro imprimé, d'après la liste des pages du toc.ncx."""
    ncx = next((n for n in names if n.endswith(".ncx")), None)
    out = {}
    if ncx:
        t = decode_text(z.read(ncx))[0]
        for m in re.finditer(r"<pageTarget\b.*?<text>(.*?)</text>.*?<content\s+src=\"[^\"#]*#([^\"]+)\"", t, re.S):
            out[html.unescape(m.group(2))] = html.unescape(m.group(1)).strip()
    return out


def join_parts(a, b):
    """Suite d'une ligne d'errata sur la ligne suivante (« Guil-| lemme »)."""
    a, b = a.strip(), b.strip()
    if not a:
        return b
    if not b:
        return a
    if re.search(r"[^\W\d_]-$", a):
        return a[:-1] + b
    return a + " " + b


def read_errata(docs):
    """Entrées de l'errata : [{page, ligne, faux, juste, elems}] et les éléments de la section."""
    start = None
    for d in docs:
        for el in d.body.iter():
            if lname(el) in ("h1", "h2", "h3", "p") and re.fullmatch(r"ERRATA\.?", text_of(el), re.I):
                start = (d, el)
                break
        if start:
            break
    if not start:
        return [], []
    section, entries, cur = [start], [], None
    begun = False
    for d in docs[docs.index(start[0]):]:
        kids = list(d.body)
        i0 = kids.index(start[1]) + 1 if d is start[0] and start[1] in kids else 0
        for el in kids[i0:]:
            if lname(el) in ("h1", "h2"):
                return entries, section
            if lname(el) == "table":
                section.append((d, el))
                for tr in el.iter():
                    if lname(tr) != "tr":
                        continue
                    cells = [text_of(td) for td in tr if lname(td) in ("td", "th")]
                    if not cells or HEADER.search(" ".join(cells)) and len(" ".join(cells)) < 30:
                        continue
                    m = ENTRY.match(cells[0])
                    rest = [c for c in cells[1:]]
                    if m:
                        cur = {"page": m.group(1), "ligne": int(m.group(2)) if m.group(2) else None,
                               "faux": rest[0] if rest else "", "juste": rest[1] if len(rest) > 1 else "",
                               "brut": " | ".join(cells)}
                        entries.append(cur)
                        begun = True
                    elif cur is not None and not cells[0]:
                        cur["faux"] = join_parts(cur["faux"], rest[0] if rest else "")
                        cur["juste"] = join_parts(cur["juste"], rest[1] if len(rest) > 1 else "")
                        cur["brut"] += " / " + " | ".join(cells)
            elif lname(el) in ("p", "div"):
                if begun and len(text_of(el)) > 200:
                    return entries, section          # fin de l'errata : retour au texte
                section.append((d, el))
    return entries, section


def pattern(s):
    s = s.strip()
    parts = [re.escape(w) for w in s.split()]
    p = re.sub(r"['’]", "['’]", r"\s+".join(parts))
    if re.match(r"\w", s):
        p = r"(?<![\w-])" + p
    if re.search(r"\w$", s):
        p += r"(?![\w-])"
    return re.compile(p)


WORDS = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def loose_pattern(s, span=False):
    """Mêmes mots dans le même ordre, ponctuation et guillemets ignorés : l'OCR, la référence ou
    l'errata lui-même ont pu perdre ou ajouter une virgule (« se tournent, » / « se tournent »)."""
    words = WORDS.findall(s)
    if not words:
        return None
    sep = r"(?:\W|\d)*" if span else r"(?:[^\w\n]|\d)*"     # le contexte peut enjamber un appel
    p = sep.join(re.sub(r"['’]", "['’]", re.escape(w)) for w in words)
    lead = r"(?:«\s*)?" if s.strip().startswith("«") else ""
    trail = r"(?:[ \t]*[.,;:!?])?" if re.search(r"[.,;:!?]\s*$", s) else ""
    return re.compile((r"(?<!\w)" if span else r"(?<![\w-])") + lead + p + r"(?![\w-])" + trail)


def read_tsv(path):
    out = []
    with open(path, encoding="utf-8") as f:
        head = f.readline()
        while head.startswith("#"):
            head = f.readline()
        head = head.rstrip("\n").split("\t")
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            row = dict(zip(head, line.rstrip("\n").split("\t")))
            out.append({"appliquer": (row.get("appliquer") or "oui").strip().lower() not in ("non", "n", "0", ""),
                        "page": row.get("page", "").strip(),
                        "ligne": int(row["ligne"]) if (row.get("ligne") or "").strip().isdigit() else None,
                        "faux": row.get("au_lieu_de", ""), "juste": row.get("lisez", ""),
                        "contexte": row.get("contexte", "").strip(),
                        "brut": "%s | %s" % (row.get("au_lieu_de", ""), row.get("lisez", ""))})
    return out


def write_tsv(path, entries, status):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Errata du livre, lu par OCR : corrigez « au_lieu_de » et « lisez » d'après le scan, \n"
                "# « contexte » (quelques mots de la ligne) départage plusieurs occurrences ; appliquer : oui/non.\n")
        f.write("appliquer\tpage\tligne\tau_lieu_de\tlisez\tcontexte\tresultat\n")
        for e in entries:
            f.write("\t".join([("oui" if e.get("appliquer", True) else "non"), e["page"],
                               str(e["ligne"] or ""), e["faux"], e["juste"], e.get("contexte", ""),
                               status.get(id(e), "")]) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Appliquer l'errata imprimé d'un livre à son texte.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB corrigé (défaut : en place)")
    ap.add_argument("--lignes", type=int, default=32,
                    help="lignes par page du livre imprimé, pour départager plusieurs occurrences (défaut 32)")
    ap.add_argument("--tsv", help="liste de l'errata à relire (TSV) : écrite d'après l'OCR si elle n'existe "
                                  "pas, reprise telle quelle sinon (vos corrections d'après le scan comptent)")
    ap.add_argument("--retirer", action="store_true",
                    help="retirer la section ERRATA quand toutes ses corrections ont été faites")
    opts = ap.parse_args()

    src = opts.epub
    with zipfile.ZipFile(src) as zin:
        infos, names = zin.infolist(), zin.namelist()
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
        opf = decode_text(zin.read(opf_path))[0]
        ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf)
        EPUB2[0] = not (ver and ver.group(1).startswith("3"))
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf):
            if get_attr(m.group(0), "href"):
                items[get_attr(m.group(0), "id")] = resolve(opf_path, get_attr(m.group(0), "href"))
        spine = [items[i] for i in re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf)
                 if i in items and items[i] in names]
        scan = re.search(r'name="prescel:scan-url"\s+content="([^"]+)"', opf)
        docs = []
        for p in spine:
            try:
                d = Doc(p, *decode_text(zin.read(p)))
            except ET.ParseError:
                continue
            if d.body is not None:
                docs.append(d)
        labels = page_labels(zin, names)
        if not labels:
            sys.exit("Pas de liste des pages dans le toc.ncx : l'errata renvoie à des numéros de page "
                     "(lancez d'abord epub_pages.py).")
        entries, section = read_errata(docs)
        from_tsv = bool(opts.tsv and os.path.exists(opts.tsv))
        if from_tsv:
            entries = read_tsv(opts.tsv)
            print("Errata repris de %s (relu)" % opts.tsv)
        if not entries:
            print("Aucun errata trouvé (titre « ERRATA. » suivi d'un tableau).")
            if opts.output and opts.output != src:
                shutil.copy2(src, opts.output)
            return
        print("Errata : %d corrections lues" % len(entries))
        status = {}

        # texte courant de chaque page : (nœud, attribut, début dans la page)
        skip = set()
        for d, el in section:
            skip.update(id(x) for x in el.iter())
        var_page = {}                      # élément de variantes → sa page (title="p. 12")
        for d in docs:
            for el in d.body.iter():
                c = classes(el)
                if c & {"note", "marge"} or (lname(el) == "sup" and "var" in c):
                    skip.add(id(el))           # appels de variante : leur texte n'est pas du texte
                    if not (lname(el) == "sup"):
                        skip.update(id(x) for x in el.iter())
                if "variantes" in c:
                    lab = re.sub(r"^p\.\s*", "", el.get("title") or "")
                    for x in el.iter():
                        var_page[id(x)] = lab
        view_of = {a: lab for a, lab in labels.items()}
        pages, cur = {}, None
        for d in docs:
            parent = {c: p for p in d.body.iter() for c in p}
            for holder, attr in text_holders(d.body):
                if attr == "text" and holder.get("id") in view_of:
                    cur = (view_of[holder.get("id")], holder.get("id"))
                owner = holder if attr == "text" else parent.get(holder)
                if owner is None or id(owner) in skip:
                    continue
                label = var_page.get(id(owner)) or (cur[0] if cur else None)
                if label is None:
                    continue
                pg = pages.setdefault(label, {"slots": [], "len": 0, "anchor": None, "doc": set()})
                if pg["anchor"] is None and cur and cur[0] == label:
                    pg["anchor"] = cur[1]
                s = getattr(holder, attr) or ""
                pg["slots"].append((holder, attr, pg["len"], d.path))
                pg["len"] += len(s) + 1            # « \n » entre deux nœuds : pas de mot à cheval

        done, todo, changed = [], [], set()
        for e in entries:
            faux, juste = e["faux"].strip(), e["juste"].strip()
            where = "p. %s%s" % (e["page"], ", l. %d" % e["ligne"] if e["ligne"] else "")
            if not e.get("appliquer", True):
                status[id(e)] = "écarté"
                continue
            if not faux or not juste:
                todo.append((e, where, "ligne d'errata illisible"))
                continue
            if faux == juste:
                todo.append((e, where, "« au lieu de » et « lisez » identiques : l'OCR de l'errata a perdu "
                                       "la différence (accent ?)"))
                continue
            pg = pages.get(e["page"])
            if not pg:
                todo.append((e, where, "page introuvable"))
                continue
            # une longue variante commencée sur la page précédente est rangée sous cette page-là :
            # si le contexte n'est pas sur la page indiquée, on le cherche sur la précédente
            if e.get("contexte") and e["page"].isdigit() and str(int(e["page"]) - 1) in pages:
                cp_ = loose_pattern(e["contexte"], span=True)
                here = "\n".join(getattr(h, a) or "" for h, a, _, _ in pg["slots"])
                if cp_ and not cp_.search(here):
                    prev = pages[str(int(e["page"]) - 1)]
                    there = "\n".join(getattr(h, a) or "" for h, a, _, _ in prev["slots"])
                    if len(list(cp_.finditer(there))) == 1:
                        pg = prev
            # positions recalculées à chaque correction : une correction précédente sur la même
            # page a pu changer la longueur d'un nœud (« grans » → « grant »)
            pos, acc = [], 0
            for h, a, _, path_ in pg["slots"]:
                pos.append((h, a, acc, path_))
                acc += len(getattr(h, a) or "") + 1
            pg["slots"] = pos
            text = "\n".join(getattr(h, a) or "" for h, a, _, _ in pg["slots"]) + "\n"
            lo, hi = 0, len(text)
            if e.get("contexte"):
                cp = loose_pattern(e["contexte"], span=True)
                cm = list(cp.finditer(text)) if cp else []
                if not cm:
                    # relance : la correction est peut-être déjà faite (le contexte contient « lisez »)
                    cw, fw, jw = WORDS.findall(e["contexte"]), WORDS.findall(faux), WORDS.findall(juste)
                    low = [w.lower() for w in cw]
                    k = next((i for i in range(len(cw) - len(fw) + 1)
                              if fw and low[i:i + len(fw)] == [w.lower() for w in fw]), None)
                    cp2 = None
                    if k is not None:
                        cp2 = loose_pattern(" ".join(cw[:k] + jw + cw[k + len(fw):]), span=True)
                        cp2 = re.compile(cp2.pattern, re.I) if cp2 else None
                    if cp2 and len(list(cp2.finditer(text))) == 1:
                        status[id(e)] = "déjà conforme"
                        done.append((where, "déjà conforme : « %s »" % juste))
                        continue
                if len(cm) != 1:
                    todo.append((e, where, "contexte « %s » trouvé %d fois" % (e["contexte"], len(cm))))
                    continue
                lo, hi = cm[0].start(), cm[0].end()
            flags = re.I if e.get("contexte") else 0     # « si » de l'errata pour « Si » en début de phrase
            hits = [m for m in re.compile(pattern(faux).pattern, flags).finditer(text) if lo <= m.start() < hi]
            if not hits and loose_pattern(faux):
                hits = [m for m in re.compile(loose_pattern(faux).pattern, flags).finditer(text)
                        if lo <= m.start() < hi]
            if not hits:
                if e.get("contexte") and pattern(juste).search(text, lo, hi):
                    status[id(e)] = "déjà conforme"
                    done.append((where, "déjà conforme : « %s »" % juste))
                    continue
                todo.append((e, where, "« %s » absent de la page" % faux))
                continue
            if not e.get("contexte") and len(WORDS.findall(faux)) == 1 and len(faux.strip(" .,;:")) <= 4:
                todo.append((e, where, "mot court (« %s ») : indiquez le contexte" % faux))
                continue
            hit = hits[0]
            if len(hits) > 1:
                if not e["ligne"]:
                    todo.append((e, where, "%d occurrences et pas de numéro de ligne" % len(hits)))
                    continue
                want = (e["ligne"] - 1) / max(1, opts.lignes - 1)
                ranked = sorted(hits, key=lambda m: abs(m.start() / max(1, len(text)) - want))
                d0 = abs(ranked[0].start() / len(text) - want)
                d1 = abs(ranked[1].start() / len(text) - want)
                if d0 > 0.2 or d1 - d0 < 0.06:
                    todo.append((e, where, "%d occurrences trop proches pour choisir" % len(hits)))
                    continue
                hit = ranked[0]
            # le passage doit tenir dans un seul nœud de texte
            slot = next(((h, a, st, p) for h, a, st, p in pg["slots"]
                         if st <= hit.start() and hit.end() <= st + len(getattr(h, a) or "")), None)
            if slot is None:
                todo.append((e, where, "le passage traverse une balise (italique, appel…)"))
                continue
            h, a, st, path = slot
            if hit.group(0) == juste:
                status[id(e)] = "déjà conforme"
                done.append((where, "déjà conforme : « %s »" % juste))
                continue
            s = getattr(h, a)
            if hit.group(0)[:1].isupper() and juste[:1].islower() and faux[:1].islower():
                juste = juste[:1].upper() + juste[1:]
            setattr(h, a, s[:hit.start() - st] + juste + s[hit.end() - st:])
            changed.add(path)
            ctx = text[max(0, hit.start() - 30):hit.start()] + "[" + faux + " → " + juste + "]" + \
                text[hit.end():hit.end() + 30]
            done.append((where, ctx.replace("\n", " ")))
            status[id(e)] = "appliqué"

        for e, where, why in todo:
            status[id(e)] = "à faire : " + why
        if opts.tsv:
            write_tsv(opts.tsv, entries, status)
            if not from_tsv:
                print("Liste à relire : %s — corrigez-la d'après le scan puis relancez." % opts.tsv)
        print("Appliquées : %d" % len(done))
        for where, ctx in done:
            print("  %-14s …%s…" % (where, ctx))
        if todo:
            print("À faire à la main : %d" % len(todo))
            for e, where, why in todo:
                link = ""
                if scan and e["page"] in pages and pages[e["page"]]["anchor"]:
                    m = re.match(r"page-(\d+)$", pages[e["page"]]["anchor"])
                    if m:
                        link = "  " + scan.group(1).replace("{page}", m.group(1))
                print("  %-14s %s — %s%s" % (where, e["brut"], why, link))
        if opts.retirer:
            if todo:
                print("Section ERRATA gardée : %d corrections restent à faire." % len(todo))
            else:
                for d, el in section:
                    kids = list(d.body)
                    if el in kids:
                        # les ancres de page restent (liste des pages du toc.ncx, liens Gallica)
                        ids = [a.get("id") for a in el.iter() if lname(a) == "a" and a.get("id")]
                        if ids:
                            ns = el.tag[:el.tag.index("}") + 1] if el.tag.startswith("{") else ""
                            keep = ET.Element(ns + "div")
                            for i in ids:
                                ET.SubElement(keep, ns + "a", {"id": i})
                            d.body.insert(kids.index(el), keep)
                        d.body.remove(el)
                    changed.add(d.path)
                print("Section ERRATA retirée.")

        out_path = opts.output or src
        new_data = {d.path: d.serialize() for d in docs if d.path in changed or fix_doctype(d.prefix) != d.prefix}
        # nombre de corrections faites, pour la note de transcription (epub_gutenberg.py)
        n_ok = sum(1 for v in status.values() if v in ("appliqué", "déjà conforme"))
        meta = '<meta name="prescel:errata" content="%d/%d"/>' % (n_ok, len(entries))
        opf2 = re.sub(r'\s*<meta name="prescel:errata"[^>]*/>', "", opf)
        opf2 = re.sub(r"(</(?:[\w-]+:)?metadata>)", "    " + meta + "\n  \\1", opf2, count=1)
        new_data[opf_path] = opf2.encode("utf-8")
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
