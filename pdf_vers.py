#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_vers.py — EPUB d'un poème édité vers par vers (édition savante du XIXᵉ siècle : numéros
de vers en marge tous les 4 ou 5 vers, folios du manuscrit et dates en manchette, notes
critiques en bas de page), à partir de la couche texte d'un PDF (Internet Archive, Google…).

pdf_to_epub.py recolle les lignes en paragraphes : bien pour la prose, pas pour des vers.
Ici, chaque ligne imprimée reste un vers :
- les mots sont regroupés en lignes d'après leur position (une ligne coupée par l'OCR en deux
  morceaux de hauteurs différentes est recollée) ;
- à gauche du texte : le numéro de vers (« 1 60 » lu par l'OCR → 160) ; la numérotation de
  tous les vers est recalculée d'après ces repères, et le numéro est rendu tous les
  --pas vers dans <span class="numvers"> ;
- à droite : les manchettes (« (f°. 2) », « (1141) ») dans <span class="manchette"> ;
- une ligne en retrait commence un nouveau paragraphe (<p class="vers">, vers séparés par
  <br/>) ;
- le titre courant et le folio du haut de page sont retirés ; les notes du bas de page
  (« 162 naufré. — 163 veve, ms. uine. ») vont dans <p class="variantes" title="p. 7">,
  regroupées en fin de volume par epub_gutenberg.py.
Les pages avant le premier vers (titre, avertissement, avant-propos) sont traitées en prose.

Usage :
  python3 pdf_vers.py livre.pdf -o livre.epub [--premier-vers 1] [--pas 4] [--pages 9-386]
"""
import argparse
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_to_epub as P  # noqa: E402

NUM = re.compile(r"[\d\\|/]+")


def norm_quote(t):
    """Guillemet de début de vers lu « € », « (( »… par l'OCR."""
    return "«" if t in ("€", "<«", "«<", "((", "<<", "C") else t


def page_lines(page):
    """Lignes visuelles de haut en bas : [y, x0, x1, [(x0, x1, mot)]]."""
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words") if w[4].strip()]
    if not words:
        return []
    tol = max(3.0, 0.45 * statistics.median([w[3] - w[1] for w in words]))
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines = []
    for w in words:
        yc = (w[1] + w[3]) / 2
        if lines and abs(yc - lines[-1][0]) <= tol:
            lines[-1][3].append((w[0], w[2], w[4]))
        else:
            lines.append([yc, 0, 0, [(w[0], w[2], w[4])]])
    for ln in lines:
        ln[3].sort()
        ln[1], ln[2] = ln[3][0][0], ln[3][-1][1]
    lines.sort(key=lambda ln: ln[0])
    # morceaux de ligne restés seuls (« ; », « (f. », « — Por ») : l'OCR les a posés sur une
    # ligne de base un peu décalée ; ils rejoignent la ligne la plus proche si l'écart est
    # nettement inférieur à l'interligne
    if len(lines) > 4:
        pitch = statistics.median(b[0] - a[0] for a, b in zip(lines, lines[1:]))
        merged = []
        for ln in lines:
            small = len("".join(w[2] for w in ln[3])) <= 12
            prev_small = merged and len("".join(w[2] for w in merged[-1][3])) <= 12
            # deux morceaux d'un même vers posés sur des lignes de base voisines : ils ne se
            # chevauchent pas en largeur (« Par fei! or quit » … « — ge que c'est gas. »)
            disjoint = merged and (ln[1] >= merged[-1][2] - 2 or ln[2] <= merged[-1][1] + 2)
            gap = ln[0] - merged[-1][0] if merged else 99
            if merged and (gap < 0.45 * pitch                     # même ligne visuelle
                           or (small or prev_small) and gap < 0.62 * pitch
                           or disjoint and gap < 0.85 * pitch):
                merged[-1][3] = sorted(merged[-1][3] + ln[3])
                merged[-1][1], merged[-1][2] = merged[-1][3][0][0], merged[-1][3][-1][1]
            else:
                merged.append(ln)
        lines = merged
    return lines


def column(doc, first, last):
    """Bord gauche le plus fréquent du texte des vers, et bord droit (95ᵉ centile)."""
    lefts, rights = [], []
    for i in range(first, last):
        for ln in page_lines(doc[i]):
            ws = [w for w in ln[3] if not NUM.fullmatch(w[2])]
            if len(ws) >= 3:
                lefts.append(ws[0][0])
                rights.append(ws[-1][1])
    bins = {}
    for v in lefts:
        bins.setdefault(round(v / 3), []).append(v)
    left = statistics.median(max(bins.values(), key=len))
    # bord droit des vers seulement (pas des notes, qui commencent plus à gauche et vont plus loin)
    rights = [r for l_, r in zip(lefts, rights) if abs(l_ - left) < 15]
    right = sorted(rights)[int(0.95 * (len(rights) - 1))]
    return left, right


def main():
    ap = argparse.ArgumentParser(description="EPUB d'un poème numéroté vers par vers (couche texte d'un PDF).")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pages", help="pages du PDF à traiter (à partir de 1), ex. 9-386")
    ap.add_argument("--premier-vers", type=int, default=1, help="numéro du premier vers du volume (défaut 1)")
    ap.add_argument("--pas", type=int, default=4, help="numéro de vers affiché tous les N vers (défaut 4)")
    ap.add_argument("--debut", type=int, help="page du PDF où commence le poème (défaut : détectée)")
    ap.add_argument("--title", help="titre (défaut : métadonnées du PDF)")
    opts = ap.parse_args()

    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    doc = pymupdf.open(opts.pdf)
    a, b = 0, doc.page_count
    if opts.pages:
        x, _, y = opts.pages.partition("-")
        a, b = int(x) - 1, int(y or x)

    start = (opts.debut - 1) if opts.debut else None
    if start is None:                    # première page où plusieurs vers portent un numéro en marge
        for i in range(a, b):
            lines = page_lines(doc[i])
            nums = sum(1 for ln in lines if NUM.fullmatch(ln[3][0][2]) and len(ln[3]) > 2)
            if nums >= 3 and len(lines) > 15:
                start = i
                break
        start = a if start is None else start
    left, right = column(doc, start, min(b, start + 40))
    print("Poème : à partir de la page %d du PDF ; colonne des vers x≈%.0f–%.0f" % (start + 1, left, right))

    blocks, pages, cur = [], [], None
    verse_no = opts.premier_vers - 1
    st = {"vers": 0, "num": 0, "recal": 0, "notes": 0, "side": 0}
    anomalies = []

    pending = []                       # notes de bas de page en attente de la fin du paragraphe

    def flush():
        nonlocal cur
        if cur is not None:
            while cur["parts"] and cur["parts"][-1][0] == "br":
                cur["parts"].pop()
            if any(p[0] == "text" for p in cur["parts"]):
                blocks.append(cur)
            elif cur["parts"]:
                blocks.append({"type": "p", "parts": cur["parts"]})
        cur = None
        blocks.extend(pending)         # les notes suivent le paragraphe, qui n'est pas coupé
        pending.clear()

    for i in range(a, b):
        pg = doc[i]
        page = P.Page(i)
        page.view, page.label = i + 1, str(i + 1)
        lines = page_lines(pg)
        m = None
        if lines and lines[0][0] < 0.12 * pg.rect.height:       # titre courant et folio
            head = " ".join(w[2] for w in lines[0][3])
            m = re.search(r"(?:^|\s)(\d{1,4}|[ivxlc]+)\s*$|^\s*(\d{1,4}|[ivxlc]+)\s", head)
            if m:
                page.label = m.group(1) or m.group(2)
            if m or head.isupper():
                lines = lines[1:]
        # numéro de page : il suit le précédent ; un folio mal lu (« 854 » pour 354) est remplacé.
        # Une page sans folio lisible (début du poème) reçoit le numéro de la suivante moins un.
        prev = pages[-1] if pages else None
        ocr = page.label if m and page.label.isdigit() else None
        page.trusted = False
        if ocr and (prev is None or not getattr(prev, "trusted", False) or int(ocr) == int(prev.label) + 1):
            page.label, page.trusted = ocr, True
            if prev is not None and not getattr(prev, "trusted", False) and int(ocr) > 1 and i - 1 >= start:
                prev.label, prev.trusted = str(int(ocr) - 1), True
        elif prev is not None and getattr(prev, "trusted", False):
            page.label, page.trusted = str(int(prev.label) + 1), True
        else:
            page.label = "NP"
        if page.label in {p_.label for p_ in pages}:
            page.label, page.trusted = "NP", False
        pages.append(page)
        anchor = ("anchor", "page-%d" % page.view)

        if i < start:                                           # prose avant le poème
            flush()
            para, carry = None, ""
            for ln in lines:
                txt = " ".join(w[2] for w in ln[3]).strip()
                if para is None or ln[1] > left + 8:
                    if para:
                        blocks.append(para)
                    para = {"type": "p", "parts": [anchor] if anchor else []}
                    anchor = None
                txt = carry + txt
                carry = ""
                if re.search(r"[^\W\d_][-¬]$", txt):
                    carry, txt = txt[:-1], ""
                if txt:
                    para["parts"].append(("text", (" " if any(p[0] == "text" for p in para["parts"]) else "") + txt))
            if para:
                blocks.append(para)
            elif anchor:
                blocks.append({"type": "p", "parts": [anchor]})
            continue

        # colonne de cette page (les numérisations n'ont pas toutes le même cadrage)
        pl = [ln for ln in lines if len([w for w in ln[3] if not NUM.fullmatch(w[2])]) >= 3]
        if len(pl) >= 8:
            firsts = [next(w[0] for w in ln[3] if not NUM.fullmatch(w[2])) for ln in pl]
            bins = {}
            for v in firsts:
                bins.setdefault(round(v / 3), []).append(v)
            left = statistics.median(max(bins.values(), key=len))
            ends = sorted(ln[2] for ln, f in zip(pl, firsts) if abs(f - left) < 12)
            right = ends[int(0.6 * (len(ends) - 1))] if ends else right
        # notes du bas de page : première ligne commencée à gauche de la colonne et plus longue
        # qu'un vers, qui a l'allure d'une note (« — », « ms. », « 162 naufré »)
        cut = len(lines)
        for k, ln in enumerate(lines):
            txt = " ".join(w[2] for w in ln[3])
            # premier mot hors de la marge des numéros (lus « 2!2!0 », « 2)8 », « 1 1 20 »…) :
            # nettement à gauche de la colonne pour une note, dans la colonne pour un vers
            # (le guillemet « d'un vers cité dépasse un peu à gauche)
            first_text = next((w for w in ln[3] if w[1] > left - 3), None)
            note_like = first_text is not None and ln[1] < left - 12 and first_text[0] < left - 10
            # sans le numéro de vers de la marge
            inner = " ".join(w[2] for w in ln[3] if w[1] > left - 3)
            notes_look = k > 0.5 * len(lines) and re.search(r"—.*\b\d{2,5}\b|\b\d{2,5}\b.*—", inner) \
                and not inner.lstrip().startswith(("«", "€", "<"))
            if (k > 2 and note_like and ln[2] > right + 30 and re.search(r"—|\bms\b|\d", txt)) or notes_look:
                cut = k
                break
        # remonter : les lignes juste au-dessus qui ont le vocabulaire d'une note (« ms. »,
        # « corr. », « Ibid. », un numéro de vers dans le texte) en font partie
        notes_words = re.compile(r"\b(?:ms|corr|Ibid|cf|suppr|écrit|lisez|leçon|exponctué|grattage|interligne)\b"
                                 r"|(?<![\w.])\d{2,5}(?![\w.])")
        while cut < len(lines) and cut > 3:
            inner = " ".join(w[2] for w in lines[cut - 1][3] if w[1] > left - 3)
            if notes_words.search(inner) and not inner.lstrip().startswith(("«", "€", "<")):
                cut -= 1
            else:
                break
        verses, notes = lines[:cut], lines[cut:]
        for ln in verses:
            nums, side, body = [], [], []
            for w in ln[3]:
                if w[1] <= left - 3 and not body and (NUM.fullmatch(w[2]) or re.search(r"\d", w[2])
                                                      or len(w[2]) <= 3):
                    nums.append(re.sub(r"\D", "", w[2]))      # numéro de vers, même mal lu
                elif w[0] >= right + 35 and body:
                    side.append(w[2])
                else:
                    body.append(w)
            text = " ".join(norm_quote(w[2]) if k == 0 else w[2] for k, w in enumerate(body)).strip()
            if body and body[0][0] > left + 0.55 * (right - left) and re.match(r"[({\[]?\s*f\b|\(\d{4}\)", text):
                side, body, text = side + [w[2] for w in body], [], ""     # « (f. 3) » seul sur sa ligne
            if not text:
                if side and cur is not None:
                    st["side"] += 1
                    cur["parts"].append(("side", " ".join(side)))
                continue
            verse_no += 1
            if "".join(nums):
                n = int("".join(nums))
                st["num"] += 1
                # le numéro imprimé recale le compte s'il est plausible : multiple du pas et proche ;
                # un écart de 20 ou 24 vient d'un chiffre mal lu (« 1456 » pour 1480)
                if n != verse_no and abs(n - verse_no) <= 8 and n % opts.pas == 0:
                    st["recal"] += 1
                    anomalies.append("p. %s : vers %d compté %d" % (page.label, n, verse_no))
                    if n < verse_no and cur is not None:         # pas de numéro affiché deux fois
                        cur["parts"] = [x for x in cur["parts"] if not (x[0] == "num" and int(x[1]) >= n)]
                    verse_no = n                                 # le numéro imprimé fait foi
            if cur is None or body[0][0] > left + 7:
                flush()
                cur = {"type": "vers", "parts": []}
            if anchor:
                cur["parts"].append(anchor)
                anchor = None
            cur["parts"].append(("text", text))
            if verse_no % opts.pas == 0:
                cur["parts"].append(("num", str(verse_no)))
            if side:
                st["side"] += 1
                cur["parts"].append(("side", " ".join(side)))
            cur["parts"].append(("br",))
            st["vers"] += 1
        if anchor:                                              # page sans vers
            flush()
            blocks.append({"type": "p", "parts": [anchor]})
        if notes:
            txt = " ".join(" ".join(w[2] for w in ln[3]) for ln in notes)
            txt = re.sub(r"([^\W\d_])[-¬] ([^\W\d_])", r"\1\2", txt)
            pending.append({"type": "variantes", "page": page.label, "parts": [("text", txt)]})
            st["notes"] += 1
            if cur is None:
                flush()
    flush()

    meta = doc.metadata or {}
    P.write_epub(opts.output, blocks, pages, {"title": opts.title or meta.get("title") or "Poème",
                                              "author": meta.get("author") or "", "language": "fr"}, 400)
    print("Vers : %(vers)d — numéros lus en marge : %(num)d (dont %(recal)d recalés) — manchettes : %(side)d"
          " — pages de notes : %(notes)d" % st)
    print("Dernier vers : %d" % verse_no)
    if anomalies:
        print("Numérotation recalée (vers coupé ou deux vers collés à vérifier près de ces pages) :")
        for a_ in anomalies:
            print("  " + a_)
    print("EPUB écrit : %s" % opts.output)


if __name__ == "__main__":
    main()
