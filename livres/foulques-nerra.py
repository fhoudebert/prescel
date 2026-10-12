#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Histoire de Foulques-Nerra, comte d'Anjou (Alexandre de Salies, Paris-Angers, 1874) : EPUB tiré de la
transcription en PDF faite avec un traitement de texte (OpenOffice, 2006). Le PDF a une vraie couche texte,
sans OCR : la mise en forme se lit aux polices.

- corps en Garamond 9, alinéa en retrait ; titres « CHAPITRE … » en Garamond gras, sommaire du chapitre
  en Bookman 7 juste dessous ; « PRÉFACE », « NOTES COMPLÉMENTAIRES ET JUSTIFICATIVES », « NOTE DERNIÈRE » ;
- notes de bas de page en Bookman 7-8, numérotées de 1 à 308 sur tout le livre : une ligne qui commence
  par le numéro attendu ouvre une note, les autres la continuent (même sur la page suivante) ; appels en
  petit corps (5,2) reliés dans les deux sens, notes regroupées en fin de chapitre ;
- petits caractères qui ne sont pas des appels : apostrophe (« d'Anjou ») ou exposant (« Xᵉ ») ;
- notes complémentaires « Note XIV — … » : ancre note-xiv, et les renvois « (Note XIV) » du texte y mènent ;
- planches et cartes : les morceaux d'image d'une même figure et les mots posés dessus (noms de lieux
  des cartes) sont rendus ensemble en une image ; la légende centrée dessous reste du texte ;
- coupures de fin de ligne : trait d'union gardé (« Foulques-Nerra », « celles-ci »), sauf quand le mot
  entier est ailleurs dans le livre et la forme coupée nulle part (« creu-ser ») ;
- mots espacés lettre à lettre (« S A L I E S ») resserrés ; « l ' abbaye » → « l'abbaye ».

La table des matières du traitement de texte (p. 2-5) est remplacée par celle de l'EPUB (titres et
sommaires). Usage :
  python3 livres/foulques-nerra.py pdf/foulquesNerra.pdf epub/Histoire_de_Foulques-Nerra.epub
"""
import collections
import html
import re
import sys
import uuid
import zipfile

import pymupdf

L = "A-Za-zÀ-ÖØ-öø-ÿŒœÆæ"
PREMIERE, DERNIERE = 6, 152          # pages du PDF lues (la table du traitement de texte est avant)
SAUTEES = {17}                       # faux-titre
INDENT = (61.5, 66)                  # retrait d'alinéa (57 : suite ; 60 : bloc en léger retrait)
ROMAIN = r"(?:[IVXLC]+|1(?:</b>)?(?:<sup>)?ere(?:</sup>)?)"
DEBUT_NOTE = r"(?:«\s*)?(?:<b>)?\s*Note\s*(?:</b>)?\s*(?:<b>)?(%s)" % ROMAIN


def de_romain(r):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    if r.startswith("1"):
        return 1
    n = sum(-v[a] if v[a] < v[b] else v[a] for a, b in zip(r, r[1:])) + v[r[-1]]
    return n if romain(n) == r else None          # « LXXVVI », « LXXXXI » : pas une forme régulière


def romain(n):
    out = ""
    for v, c in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += c
            n -= v
    return out


FAUTIVES = {}


def renumerote(blocs, journal):
    """Notes complémentaires : numéro répété ou mal formé remplacé par celui que la suite attend."""
    paras = [b for b in blocs if b["type"] == "p" and re.match(DEBUT_NOTE, b["html"])]
    vals = [de_romain(re.match(DEBUT_NOTE, b["html"]).group(1)) for b in paras]
    for k, b in enumerate(paras):
        prev = vals[k - 1] if k else 0
        nxt = vals[k + 1] if k + 1 < len(vals) else None
        if vals[k] == prev + 1:
            continue
        if nxt == prev + 2 or vals[k] is None or vals[k] in vals[:k]:
            m = re.match(DEBUT_NOTE, b["html"])
            journal.append("Note %s → Note %s" % (m.group(1), romain(prev + 1)))
            if vals[k] is None:
                FAUTIVES[m.group(1)] = romain(prev + 1)        # renvois du texte à la même forme fautive
            b["html"] = b["html"][:m.start(1)] + romain(prev + 1) + b["html"][m.end(1):]
            vals[k] = prev + 1


def esc(s):
    return html.escape(s, quote=False)


def cle(r):
    return "I" if r.startswith("1") else r


def romain_id(r):
    return "note-" + cle(r).lower()


# --------------------------------------------------------------------------
# Lignes
# --------------------------------------------------------------------------

class Ligne:
    def __init__(self, l, page):
        self.page = page
        self.x0, self.y0, self.x1, self.y1 = l["bbox"]
        self.spans = [s for s in l["spans"] if s["text"]]
        pleins = [s for s in self.spans if re.search(r"[\w«»]", s["text"])] or self.spans
        self.taille = max(s["size"] for s in pleins)
        grands = [s for s in pleins if s["size"] >= self.taille - 0.6]
        self.police = collections.Counter(s["font"] for s in grands for _ in s["text"]).most_common(1)[0][0]
        self.texte = "".join(s["text"] for s in self.spans)
        self.gras = "Bold" in self.police and "Ital" not in self.police
        premier = next((s for s in self.spans if re.search(r"\w", s["text"])), self.spans[0])
        self.note = premier["font"].startswith("Bookman") and 6 <= premier["size"] <= 8.5   # « 29 Dans la <i>…</i> »
        self.centre = abs((self.x0 + self.x1) / 2 - 297.5) < 25 and self.x0 > 90

    def html(self, appels):
        """Rendu en ligne ; appels : liste où l'on ajoute les numéros d'appel rencontrés."""
        out = []
        base = self.taille
        for k, s in enumerate(self.spans):
            t = s["text"]
            petit = s["size"] < base * 0.75
            ital = "Ital" in s["font"]
            gras = "Bold" in s["font"] and not ital and t.strip()
            if petit:
                c = t.strip()
                if c in ("'", "’", ""):
                    out.append(t)
                    continue
                if re.fullmatch(r"\d[\d ]{0,4}", c) and not self.note:      # « 1 2 », « 8 7 » : appels 12, 87
                    c = c.replace(" ", "")
                    appels.append(int(c))
                    out.append("\x00%s\x00" % c + (" " if t.endswith(" ") else ""))
                    continue
                if re.fullmatch(r"[a-zè]{1,3}", c):
                    out.append("<sup>%s</sup>" % esc(c) + (" " if t.endswith(" ") else ""))
                    continue
            e = esc(t)
            if ital and t.strip():
                e = "<i>%s</i>" % e
            elif gras:
                e = "<b>%s</b>" % e
            out.append(e)
        h = "".join(out)
        h = re.sub(r"\x00(\d)\x00\s*(?:<i>)?\x00(\d+)\x00(?:</i>)?", lambda m: "\x00%s%s\x00" % (m.group(1), m.group(2)), h)   # « 2 » + « 7 5 »
        h = re.sub(r"</i>(\s*)<i>", r"\1", h)
        h = re.sub(r"</b>(\s*)<b>", r"\1", h)
        h = re.sub(r"\s+(\x00\d+\x00)", r"\1", h)               # « Bourdigné ²³ » : pas d'espace avant l'appel
        return h


def nettoie(h):
    h = re.sub(r"(?<=[%s]) ?' ?(?=[%s])" % (L, L), "'", h)                    # l ' abbaye
    h = re.sub(r"\b(?:[A-ZÀ-Ý] ){2,}[A-ZÀ-Ý]\b", lambda m: m.group(0).replace(" ", ""), h)   # S A L I E S
    h = re.sub(r"[  ]{2,}", " ", h)
    h = re.sub(r"<i>(\s+)", r"\1<i>", h)
    h = re.sub(r"(\s+)</i>", r"</i>\1", h)
    h = re.sub(r"<i></i>|<b></b>", "", h)
    h = re.sub(r"</i>(\s*|['’])<i>", r"\1", h)
    h = re.sub(r"[ \u00a0]{2,}", " ", h)
    h = re.sub(r"\s+((?:</i>)?\x00\d+\x00)", r"\1", h)
    return h.strip()


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def figures(page):
    rects = []
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.is_empty or r.width * r.height < 300 or info["bbox"][2] > page.rect.x1 - 5:   # morceaux hors page
            continue
        rects.append(r)
    groupes = []
    for r in sorted(rects, key=lambda r: r.y0):
        for k, g in enumerate(groupes):
            if (g + (-15, -15, 15, 15)).intersects(r):
                groupes[k] = g | r
                break
        else:
            groupes.append(pymupdf.Rect(r))
    return groupes


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------

def lire(pdf, dossier_images):
    doc = pymupdf.open(pdf)
    blocs = []                 # dicts : type, html, ...
    notes = collections.OrderedDict()
    images = []
    vocab = collections.Counter()
    for pn in range(PREMIERE - 1, DERNIERE):
        for w in re.findall(r"[%s]+(?:-[%s]+)*" % (L, L), doc[pn].get_text()):
            vocab[w.lower()] += 1
    etat = {"para": None, "note": None, "derniere_note": 0, "apres_titre": False}
    attente = []

    def fermer():
        if etat["para"]:
            blocs.append(etat["para"])
            etat["para"] = None
        blocs.extend(attente)
        attente.clear()

    def ajouter(cible, h, ligne_prec_texte):
        """Recolle une ligne à la précédente (trait d'union de fin de ligne)."""
        if not cible:
            return h
        m = re.search(r"([%s]+)-$" % L, ligne_prec_texte)
        if cible.endswith("-") and m:
            n = re.match(r"([%s]+)" % L, re.sub(r"<[^>]+>|\x00\d+\x00", "", h))
            if n:
                a, b = m.group(1), n.group(1)
                entier, coupe = (a + b).lower(), (a + "-" + b).lower()
                if b[0].islower() and not vocab[coupe] and (vocab[entier] or vocab[a.lower()] <= 1):
                    return cible[:-1] + h
            return cible + h
        return cible + " " + h

    for pn in range(PREMIERE - 1, DERNIERE):
        if pn + 1 in SAUTEES:
            continue
        page = doc[pn]
        figs = figures(page)
        lignes = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                if "".join(s["text"] for s in l["spans"]).strip():
                    lignes.append(Ligne(l, pn + 1))
        lignes.sort(key=lambda x: (round(x.y0), x.x0))
        # lignes posées sur une figure : rendues avec l'image
        dans = set()
        legendes = collections.defaultdict(list)
        for k in range(len(figs)):
            for i, x in enumerate(lignes):
                c = pymupdf.Point((x.x0 + x.x1) / 2, (x.y0 + x.y1) / 2)
                if c in figs[k] + (-4, -4, 4, 4):
                    dans.add(i)
                    figs[k] = figs[k] | pymupdf.Rect(x.x0, x.y0, x.x1, x.y1)
            g = figs[k]
            for i, x in enumerate(lignes):       # légende : lignes centrées juste sous la figure
                if i in dans:
                    continue
                bas = max([g.y1] + [lignes[j].y1 for j in legendes[k]])
                if x.centre and 0 <= x.y0 - bas < 32 and len(x.texte.strip()) < 70 and not x.gras:
                    legendes[k].append(i)
                    dans.add(i)
        evenements = [(x.y0, "l", i) for i, x in enumerate(lignes) if i not in dans]
        evenements += [(g.y0, "f", k) for k, g in enumerate(figs)]
        evenements.sort(key=lambda e: (e[0], e[1] != "f"))
        prec = None
        for y, kind, i in evenements:
            if kind == "f":
                g = figs[i]
                nom = "fig-%03d-%d.png" % (pn + 1, i + 1)
                pix = page.get_pixmap(clip=g + (-2, -2, 2, 2), dpi=200, colorspace=pymupdf.csGRAY
                                      if all(page.parent.extract_image(x[0]).get("colorspace", 1) == 1
                                             for x in page.get_images()) else pymupdf.csRGB)
                pix.save("%s/%s" % (dossier_images, nom))
                images.append(nom)
                leg = " ".join(nettoie(lignes[j].html([])) for j in sorted(legendes[i], key=lambda j: lignes[j].y0))
                leg = re.sub(r"(?<=\d) (?=\d)|(?<=\bP) (?=\.)|(?<=n) (?=°)", "", leg)     # « P . 4 6 4 , n ° »
                leg = re.sub(r"\s+([.,])", r"\1", leg)
                fig = {"type": "figure", "src": nom, "legende": leg, "page": pn + 1}
                if etat["para"]:
                    attente.append(fig)               # dans un alinéa : après l'alinéa
                else:
                    blocs.append(fig)
                continue
            x = lignes[i]
            t = x.texte.strip()
            # notes de bas de page (pas le sommaire d'un chapitre)
            if x.note and not etat["apres_titre"] and x.y0 > 200 or (x.note and x.y0 > 690):
                m = re.match(r"\s*(\d+)\s*", x.texte)
                h = nettoie(x.html([]))
                if m and int(m.group(1)) == etat["derniere_note"] + 1:
                    n = int(m.group(1))
                    etat["derniere_note"] = n
                    h = nettoie(re.sub(r"^\s*%d\s*" % n, "", h))
                    notes[n] = h
                    etat["note"] = n
                elif etat["note"]:
                    notes[etat["note"]] = ajouter(notes[etat["note"]], h, notes[etat["note"]])
                prec = None
                continue
            appels = []
            h = x.html(appels)
            t = re.sub(r"C\s*H\s*A\s*P\s*I\s*T\s*R\s*E", "CHAPITRE", t)       # « C H A PITRE XIV. »
            if t.startswith("CHAPITRE"):
                h = re.sub(r"C\s*H\s*A\s*P\s*I\s*T\s*R\s*E", "CHAPITRE", h)
            if x.gras and (re.match(r"CHAPITRE|PRÉFACE|NOTES COMPL|HISTOIRE DE FOULQUES", t)):
                fermer()
                niveau = "h2" if t.startswith("CHAPITRE") else "h1"
                blocs.append({"type": niveau, "html": nettoie(re.sub(r"</?b>", "", h))})
                etat["apres_titre"] = t.startswith("CHAPITRE")
                prec = x
                continue
            if t.startswith("NOTE DERNIÈRE") or t.startswith("A L'OCCASION DE NOTRE PLANCHE") or \
                    re.match(r"A L\s*'\s*OCCASION", t):
                fermer()
                h = re.sub(r"</?b>", "", h)
                if blocs and blocs[-1]["type"] == "h3":
                    blocs[-1]["html"] += " " + nettoie(h)
                else:
                    blocs.append({"type": "h3", "html": nettoie(h)})
                prec = x
                continue
            if etat["apres_titre"] and (x.note or x.centre):
                if blocs[-1]["type"] == "sommaire":
                    blocs[-1]["html"] = ajouter(blocs[-1]["html"], nettoie(h), blocs[-1]["html"])
                else:
                    blocs.append({"type": "sommaire", "html": nettoie(h)})
                prec = x
                continue
            etat["apres_titre"] = False
            nouveau = (prec is None and (INDENT[0] <= x.x0 <= INDENT[1] or x.centre or x.x0 > 100)) or \
                (prec is not None and (x.y0 - prec.y1 > 8.5 or x.x0 > 100
                                       or (INDENT[0] <= x.x0 <= INDENT[1] and abs(prec.x0 - x.x0) > 1.5)
                                       or prec.centre or x.centre))
            if re.match(r"\W{0,2}Note\s+(?:[IVXLC]+|1)", t) and x.spans and "Bold" in x.spans[0]["font"] + \
                    (x.spans[1]["font"] if len(x.spans) > 1 else ""):
                nouveau = True                        # note complémentaire « Note XIV — »
            elif prec is None and etat["para"] and not x.centre:
                fin = re.sub(r"<[^>]+>|\x00\d+\x00|\s", "", etat["para"]["html"])[-1:]
                if fin and fin not in ".!?»:;…)":
                    nouveau = False                   # alinéa continué sur la page suivante
            if nouveau or not etat["para"]:
                fermer()
                cls = "centre" if x.centre else ("retrait" if x.x0 > 100 else "")
                etat["para"] = {"type": "p", "html": "", "cls": cls}
            etat["para"]["html"] = ajouter(etat["para"]["html"], h, etat["para"]["html"])
            prec = x
    fermer()
    for b in blocs:
        if "html" in b:
            b["html"] = nettoie(b["html"])
    return blocs, notes, images


# --------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------

CSS = """body { font-family: serif; margin: 0 1em; text-align: justify; }
h1 { text-align: center; font-size: 1.4em; margin: 2em 0 1em; }
h2 { text-align: center; font-size: 1.15em; margin: 2em 0 0.6em; }
h3 { text-align: center; font-size: 1em; margin: 1.5em 0 0.6em; }
p { text-indent: 1.5em; margin: 0 0 0.3em; }
p.sommaire { text-indent: 0; margin: 0 2em 1.2em; font-size: 0.85em; text-align: justify; }
p.centre, p.titre { text-indent: 0; text-align: center; }
p.retrait { text-indent: 0; margin-left: 3em; }
p.note { text-indent: 0; font-size: 0.85em; margin: 0.3em 0 0.3em 1.5em; }
p.complement { text-indent: 0; margin-top: 0.8em; }
div.figure { text-align: center; margin: 1em 0; page-break-inside: avoid; }
div.figure img { max-width: 100%; }
div.figure img.sceau { width: 22%; }
p.legende { text-indent: 0; text-align: center; font-size: 0.85em; margin: 0.3em 0 1em; }
p.t1 { text-indent: 0; text-align: center; font-size: 1.6em; font-weight: bold; margin-top: 3em; letter-spacing: 0.1em; }
p.t2 { text-indent: 0; text-align: center; font-size: 1.1em; margin: 0.6em 0; }
p.t3 { text-indent: 0; text-align: center; font-size: 0.8em; margin: 0.3em 0; }
p.dedicace { text-indent: 0; text-align: center; margin: 0.8em 0; }
sup { font-size: 0.7em; line-height: 0; }
span.a-verifier { background: #ffef99; }
"""

TITRE = """<p class="t1">HISTOIRE DE FOULQUES-NERRA</p>
<p class="t2">COMTE D'ANJOU</p>
<p class="t3">D'APRÈS LES CHARTES CONTEMPORAINES ET LES ANCIENNES CHRONIQUES</p>
<p class="t3">SUIVIE DE</p>
<p class="t2">L'OFFICE DU SAINT-SÉPULCRE<br />DE L'ABBAYE DE BEAULIEU</p>
<p class="t3">DONT LES LEÇONS FORMENT UNE CHRONIQUE INÉDITE</p>
<p class="t3">AVEC 12 PLANCHES ET UNE GRANDE CARTE</p>
<p class="t2">PAR ALEXANDRE DE SALIES</p>
<div class="figure"><img class="sceau" src="../Images/sceau.png" alt="Sceau" /></div>
<p class="t3">PARIS<br />Chez J.-B. Dumoulin, libraire, quai des Grands-Augustins, 13.</p>
<p class="t3">ANGERS<br />Chez E. Barassé, imp.-libraire, rue St-Laud, 83.</p>
<p class="t2">1874</p>"""


def xhtml(titre, corps):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"\n'
            '  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head>\n  <title>%s</title>\n  <link href="../Styles/livre.css" rel="stylesheet" type="text/css" />\n'
            '</head>\n<body>\n%s\n</body>\n</html>\n' % (esc(titre), corps))


def ecrire(dst, blocs, notes, images, dossier_images):
    journal = []
    i = next(k for k, b in enumerate(blocs) if b["type"] == "h1" and "NOTES COMPL" in b["html"])
    renumerote(blocs[i:], journal)
    # découpage : titre, dédicace + préface, un fichier par chapitre, notes complémentaires
    parties, cur = [], None
    for b in blocs:
        if b["type"] in ("h1", "h2") and not (b["type"] == "h2" and cur and cur[0] == "HISTOIRE DE FOULQUES-NERRA"
                                              and not any(x["type"] == "h2" for x in cur[1])):
            cur = [re.sub(r"<[^>]+>", "", b["html"]), []]
            parties.append(cur)
        if cur is None:
            cur = ["Dédicace", []]
            parties.append(cur)
        cur[1].append(b)
    fichiers, nav, cible = [], [], {}
    # où est chaque note complémentaire, chaque note de bas de page
    for k, (nom, bl) in enumerate(parties):
        fn = "texte-%02d.xhtml" % (k + 1)
        for b in bl:
            if b["type"] == "p":
                m = re.match(DEBUT_NOTE, b["html"])
                if m:
                    cible.setdefault(cle(m.group(1)), fn)
            b["fichier"] = fn
    vus, ids, doublons = set(), set(), []
    for k, (nom, bl) in enumerate(parties):
        fn = "texte-%02d.xhtml" % (k + 1)
        corps, a_noter = [], []
        for b in bl:
            if b["type"] in ("h1", "h2", "h3"):
                if a_noter and b["type"] != "h3":
                    corps += notes_html(a_noter, notes)
                    a_noter = []
                nid = "t%d" % (len(nav) + 1)
                corps.append('<%s id="%s">%s</%s>' % (b["type"], nid, b["html"], b["type"]))
                if b["type"] != "h3":
                    nav.append([b["type"], re.sub(r"<[^>]+>", "", b["html"]).strip(), fn, nid])
                continue
            if b["type"] == "sommaire":
                corps.append('<p class="sommaire">%s</p>' % b["html"])
                if nav:
                    nav[-1][1] += " — " + re.sub(r"<[^>]+>", "", b["html"]).split(" — ")[0].strip()
                continue
            if b["type"] == "figure":
                corps.append('<div class="figure"><img src="../Images/%s" alt="%s" /></div>'
                             % (b["src"], html.escape(re.sub(r"<[^>]+>", "", b["legende"]) or "Figure")))
                if b["legende"]:
                    corps.append('<p class="legende">%s</p>' % b["legende"])
                continue
            h = b["html"]

            def appel(m):
                n = int(m.group(1))
                if n not in notes or n in vus:
                    return "<sup>%d</sup>" % n
                vus.add(n)
                a_noter.append(n)
                return '<sup><a href="#note-%d" id="appel-%d">%d</a></sup>' % (n, n, n)
            h = re.sub(r"\x00(\d+)\x00", appel, h)
            attrs = ""
            m = re.match(DEBUT_NOTE, h)
            if m and k == len(parties) - 1:
                ident = romain_id(m.group(1))
                if ident in ids:
                    doublons.append(m.group(1))
                    ident += "-%d" % (sum(1 for x in ids if x.startswith(ident + "-")) + 2)
                ids.add(ident)
                attrs = ' class="complement" id="%s"' % ident
            elif b.get("cls"):
                attrs = ' class="%s"' % b["cls"]
            if k < len(parties) - 1 or not m:
                def renvoi(mm):
                    r = mm.group(2)
                    r = FAUTIVES.get(r, r)
                    if cle(r) in cible:
                        return '%s<a href="%s#%s">Note %s</a>' % (mm.group(1), cible[cle(r)], romain_id(r), r)
                    if False:
                        return '%s<a href="%s#%s">Note %s</a>' % (mm.group(1), cible[r], romain_id(r), r)
                    return mm.group(0)
                h = re.sub(r"(\(\s*)Note (%s)\b" % ROMAIN, renvoi, h)
            corps.append("<p%s>%s</p>" % (attrs, h))
        corps += notes_html(a_noter, notes)
        fichiers.append((fn, xhtml(nom.capitalize() if nom.isupper() else nom, "\n".join(corps))))
    manquantes = sorted(set(notes) - vus)
    z = zipfile.ZipFile(dst, "w")
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)

    def w(n, data):
        z.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
    w("META-INF/container.xml", '<?xml version="1.0"?>\n<container version="1.0" '
      'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n<rootfiles><rootfile '
      'full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n</container>\n')
    w("OEBPS/Styles/livre.css", CSS)
    w("OEBPS/Text/titre.xhtml", xhtml("Histoire de Foulques-Nerra", TITRE))
    for fn, data in fichiers:
        w("OEBPS/Text/" + fn, data)
    for im in images + ["sceau.png"]:
        z.write("%s/%s" % (dossier_images, im), "OEBPS/Images/" + im, compress_type=zipfile.ZIP_DEFLATED)
    bid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "prescel/foulques-nerra-salies-1874"))
    man = ['    <item id="titre" href="Text/titre.xhtml" media-type="application/xhtml+xml"/>']
    man += ['    <item id="x%d" href="Text/%s" media-type="application/xhtml+xml"/>' % (k, fn)
            for k, (fn, _) in enumerate(fichiers)]
    man += ['    <item id="i%d" href="Images/%s" media-type="image/png"/>' % (k, im)
            for k, im in enumerate(images + ["sceau.png"])]
    spine = ['    <itemref idref="titre"/>'] + ['    <itemref idref="x%d"/>' % k for k in range(len(fichiers))]
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" '
           'unique-identifier="bookid" version="2.0">\n  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
           'xmlns:opf="http://www.idpf.org/2007/opf">\n'
           '    <dc:title>Histoire de Foulques-Nerra, comte d\'Anjou</dc:title>\n'
           '    <dc:creator opf:role="aut" opf:file-as="Salies, Alexandre de">Alexandre de Salies</dc:creator>\n'
           '    <dc:publisher>J.-B. Dumoulin (Paris), E. Barassé (Angers)</dc:publisher>\n'
           '    <dc:date>1874</dc:date>\n    <dc:language>fr</dc:language>\n'
           '    <dc:subject>Foulques III Nerra, comte d\'Anjou</dc:subject>\n'
           '    <dc:identifier id="bookid">%s</dc:identifier>\n'
           '    <meta name="cover" content="i%d"/>\n'
           '  </metadata>\n  <manifest>\n    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
           '    <item id="css" href="Styles/livre.css" media-type="text/css"/>\n%s\n  </manifest>\n'
           '  <spine toc="ncx">\n%s\n  </spine>\n</package>\n'
           % (bid, len(images), "\n".join(man), "\n".join(spine)))
    w("OEBPS/content.opf", opf)
    pts, ordre, ouvert = [], 1, False
    pts.append('<navPoint id="n1" playOrder="1"><navLabel><text>Titre</text></navLabel>'
               '<content src="Text/titre.xhtml"/></navPoint>')
    for niv, titre, fn, nid in nav:
        ordre += 1
        pt = '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="Text/%s#%s"/>' % (
            ordre, ordre, esc(titre[:150]), fn, nid)
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
           '<docTitle><text>Histoire de Foulques-Nerra</text></docTitle>\n<navMap>\n%s\n</navMap>\n</ncx>\n'
           % (bid, "\n".join(pts)))
    w("OEBPS/toc.ncx", ncx)
    z.close()
    return len(fichiers), manquantes, doublons + journal, sorted(cible)


def notes_html(nums, notes):
    return ['<p class="note" id="note-%d"><a href="#appel-%d">%d</a>. %s</p>' % (n, n, n, notes[n]) for n in nums]


def main():
    src, dst = sys.argv[1], sys.argv[2]
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    doc = pymupdf.open(src)
    xref = doc[0].get_images()[0][0]                    # sceau de la page de titre : l'image elle-même
    pymupdf.Pixmap(doc, xref).save(os.path.join(tmp, "sceau.png"))
    blocs, notes, images = lire(src, tmp)
    nf, manquantes, doublons, complements = ecrire(dst, blocs, notes, images, tmp)
    print("Fichiers : %d ; notes : %d ; figures : %d" % (nf, len(notes), len(images)))
    if doublons:
        print("Notes complémentaires : %s" % " ; ".join(doublons))
    if manquantes:
        print("Notes sans appel : %s" % ", ".join(map(str, manquantes)))


if __name__ == "__main__":
    main()
