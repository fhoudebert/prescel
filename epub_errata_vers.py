#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_errata_vers.py — Applique l'errata d'un poème numéroté (EPUB de pdf_vers.py) : chaque
correction vise un vers par son numéro, retrouvé d'après les numéros affichés
(<span class="numvers">) ; la correction n'est faite que dans ce vers (ou, à défaut, le
précédent ou le suivant, pour un compte décalé d'une ligne).

Liste TSV (une ligne par correction, relue sur le scan) :
  vers   action             avant        après
  7880   lis                sais         sai
  323    lis                             s'entrecomtrérent   (avant vide : le mot le plus proche)
  1194   point-virgule-fin
  6119   virgule-fin
  6517   suppr-ponct-fin
  3503   suppr-virgule-apres Maresc.
  4787   virgule-apres      furent
  5280   suppr              ne
Les vers hors du volume (numéros absents de l'EPUB) sont ignorés : une même liste sert aux
deux tomes. Les corrections seulement proposées par l'éditeur (« corr. … ? ») ne sont pas à
mettre dans la liste.

Usage : python3 epub_errata_vers.py livre.epub -o livre-errata.epub --tsv errata.tsv
"""
import argparse
import difflib
import re
import zipfile

NUM = re.compile(r'\s*<span class="numvers">(\d+)</span>')


def plain(s):
    return re.sub(r"<[^>]+>", "", s)


def main():
    ap = argparse.ArgumentParser(description="Errata d'un poème, par numéro de vers.")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--tsv", required=True)
    opts = ap.parse_args()
    rows = []
    for line in open(opts.tsv, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        c = (line.rstrip("\n").split("\t") + ["", "", ""])[:4]
        if c[0].isdigit():
            rows.append((int(c[0]), c[1].strip(), c[2], c[3]))

    z = zipfile.ZipFile(opts.epub)
    files = {n: z.read(n).decode("utf-8") if n.endswith((".xhtml", ".opf")) else z.read(n) for n in z.namelist()}
    texts = sorted(n for n in files if re.match(r"OEBPS/Text/texte-\d+\.xhtml$", n))
    # tous les vers : (fichier, index du paragraphe, index de la ligne) et leur numéro
    verses = []
    for n in texts:
        for pi, m in enumerate(re.finditer(r'<p class="vers">(.*?)</p>', files[n], re.S)):
            for li, v in enumerate(m.group(1).split("<br />")):
                k = NUM.search(v)
                verses.append([int(k.group(1)) if k else None, n, pi, li])
    for i, v in enumerate(verses):                    # numéroter les lignes entre deux repères
        if v[0] is not None:
            for d in (1, 2, 3):
                if i - d >= 0 and verses[i - d][0] is None:
                    verses[i - d][0] = v[0] - d
    where = {}
    for v in verses:
        if v[0] is not None:
            where.setdefault(v[0], (v[1], v[2], v[3]))

    def get(loc):
        n, pi, li = loc
        m = list(re.finditer(r'<p class="vers">(.*?)</p>', files[n], re.S))[pi]
        return m, m.group(1).split("<br />")

    def put(loc, new_line):
        n, pi, li = loc
        m, lines = get(loc)
        lines[li] = new_line
        files[n] = files[n][:m.start(1)] + "<br />".join(lines) + files[n][m.end(1):]

    done, todo = [], []
    for num, action, before, after in rows:
        cands = [where[k] for k in (num, num - 1, num + 1) if k in where]
        if not cands:
            continue                                   # vers d'un autre volume
        ok = False
        for loc in cands:
            m, lines = get(loc)
            line = lines[loc[2]]
            body, tail = line, ""
            k = re.search(r'\s*<span class="(?:numvers|manchette)">', line)   # numéro, manchette
            if k:
                body, tail = line[:k.start()], line[k.start():]
            new = None
            if action == "lis" and before:
                pat = r"(?<![\w'])%s(?![\w'])" % re.escape(before)
                if re.search(pat, body):
                    new = re.sub(pat, after, body, count=1)
                elif after and after in body:
                    done.append((num, "déjà conforme : %s" % after))
                    ok = True
                    break
            elif action == "lis":                      # le mot le plus proche de la leçon donnée
                words = re.findall(r"[\w'\[\]]+", plain(body))
                best = difflib.get_close_matches(after, words, n=1, cutoff=0.6)
                if best and best[0] != after:
                    new = body.replace(best[0], after, 1)
                    before = best[0]
            elif action in ("virgule-fin", "point-virgule-fin"):
                if not re.search(r"[,;:.!?»]\s*$", plain(body)):
                    new = body.rstrip() + ("," if action == "virgule-fin" else "\u00a0;")
            elif action == "suppr-ponct-fin":
                new = re.sub(r"[\s\u00a0]*[,;:.]+(\s*)$", r"\1", body)
            elif action == "suppr-virgule-apres":
                new = body.replace(before + ",", before, 1) if before + "," in body else None
            elif action == "virgule-apres":
                new = re.sub(r"(?<![\w])%s(?![\w,])" % re.escape(before), before + ",", body, count=1)
            elif action == "suppr":
                new = re.sub(r"\s*(?<![\w'])%s(?![\w])" % re.escape(before), "", body, count=1)
            if new is not None and new != body:
                put(loc, new + tail)
                done.append((num, "%s : « %s » → « %s »" % (action, plain(body).strip(), plain(new).strip())))
                ok = True
                break
        if not ok:
            todo.append((num, action, before, after))

    opf = files["OEBPS/content.opf"]
    m = re.search(r'<meta name="prescel:errata" content="(\d+)/(\d+)"/>', opf)
    a0, b0 = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    n_here = len(done) + len(todo)
    opf = re.sub(r'\s*<meta name="prescel:errata"[^>]*/>', "", opf)
    opf = opf.replace("</metadata>", '  <meta name="prescel:errata" content="%d/%d"/>\n  </metadata>'
                      % (a0 + len(done), b0 + n_here), 1)
    files["OEBPS/content.opf"] = opf
    with zipfile.ZipFile(opts.output, "w") as zo:
        zo.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for n, data in files.items():
            zo.writestr(n, data.encode("utf-8") if isinstance(data, str) else data, compress_type=zipfile.ZIP_DEFLATED)
    for num, msg in done:
        print("v. %d — %s" % (num, msg))
    for num, action, before, after in todo:
        print("v. %d — À FAIRE : %s %s %s" % (num, action, before, after))
    print("Appliquées : %d ; à faire à la main : %d ; EPUB écrit : %s" % (len(done), len(todo), opts.output))


if __name__ == "__main__":
    main()
