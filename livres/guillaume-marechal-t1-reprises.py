#!/usr/bin/env python3
"""Reprises du t. I de Guillaume le Maréchal (maître relu, marques retirées) avant la sortie Gutenberg, vérifiées sur le
PDF Google Livres : avant-propos (notes de bas de page rétablies, paragraphe coupé par la page recollé),
errata de l'avant-propos, notes de variantes égarées dans les vers, quelques lectures isolées.

  python3 livres/guillaume-marechal-t1-reprises.py t1.epub t1-repris.epub
"""
import re
import sys
import zipfile

NB = "&#160;"

# (fichier, avant, après, nombre attendu) — remplacements exacts dans le XHTML
REMPLACEMENTS = [
    ("texte-001", "Société de l'Histoibe de France", "Société de l'Histoire de France", 1),
    ("texte-001", "toutes les questions-historiques", "toutes les questions historiques", 1),
    ("texte-001", "Romania1 l'autre",
     'Romania<sup><a href="#note-ap1" id="appel-ap1">1</a></sup>, l\'autre', 1),
    ("texte-001", "Société de l'histoire de France2.",
     "Société de l'histoire de France<sup><a href=\"#note-ap2\" id=\"appel-ap2\">2</a></sup>.", 1),
    # fin de page : les notes collées au texte, puis le paragraphe coupé
    ("texte-001", "la restitution du 1. XII, 22-74. 2. Année 1882, pp. 244-264. </p>\n<p><a id=\"page-14\" />texte.",
     "la restitution du <a id=\"page-14\" />texte.", 1),
    ("texte-001", "employer, pour le besoin de la rime, des formes différentes en des cas identiques.</p>",
     "employer, pour le besoin de la rime, des formes différentes en des cas identiques.</p>\n"
     "<p class=\"note\" id=\"note-ap1\"><a href=\"#appel-ap1\">1</a>. XII, 22-74.</p>\n"
     "<p class=\"note\" id=\"note-ap2\"><a href=\"#appel-ap2\">2</a>. Année 1882, pp. 244-264.</p>", 1),
    # errata de l'avant-propos
    ("texte-001", "lis. taill[iê\\6.", "lis. taill[ié]e.", 1),
    ("texte-001", "essili[é]6.", "essili[é]e.", 1),
    ("texte-001", "lire Shrewshury.", "lire Shrewsbury.", 1),
    ("texte-001", "après hauberc. — — Ensanglanta —</p>\n<p>V. 1700, corr. delai[e]. V. 1715, lis. la terre. V. 1990",
     "après hauberc. — V. 1700, corr. delai[e]. — V. 1715, lis. Ensanglanta la terre. — V. 1990", 1),
    ("texte-001", "corr. maisni[e^e-li[é]e.", "corr. maisni[é]e-li[é]e.", 1),
    ("texte-001", "corr. essauci[é]e-sorliauci[é]e.", "corr. essauci[é]e-sorhauci[é]e.", 1),
    ("texte-001", "V. 4701, Olive est bien", "V. 4701, Clive est bien", 1),
    ("texte-001", "après furent.-- P. 176", "après furent. — P. 176", 1),
    ("texte-001", "nous a conservé L'Histoire de Guillaume", "nous a conservé l'Histoire de Guillaume", 1),
    # lectures isolées (PDF Google) ; « naien[t[ fu » est une coquille de l'imprimé
    ("texte-001", "Li chastels, naien[t[fu del rendre", "Li chastels, naien[t] fu del rendre", 1),
    ("texte-001", "« Certes, vos ri'i morrés uimès. »", "« Certes, vos n'i morrés uimès. »", 1),
    ("texte-002", "Veist l'om f[amb[e]ier al vent.", "Veïst l'om flamb[e]ier al vent.", 1),
    ("texte-002", "Fait fu reis a Fasompcion. (15 août, corr. <span class=\"manchette\">3 sept.)</span>",
     "Fait fu reis a l'Asompcion. <span class=\"manchette\">(15 août, corr. 3 sept.)</span>", 1),
    ("texte-001", "Sor lui comence la bataille :<span class=\"manchette\">&#160;»^-</span>",
     "Sor lui comence la bataille :", 1),
    # débuts de notes de variantes restés dans les vers (rendus à leur note, ôtés des vers)
    ("texte-002", '<p class="variantes" title="p. 307">précédent. — 8505',
     '<p class="variantes" title="p. 307">8503 Ce vers semble une fin de phrase. Lacune entre ce vers et le '
     'précédent. — 8505', 1),
    ("texte-002", 'title="p. 328">V. 6915. — 9095',
     'title="p. 328">9087 persie, les deux dern. lettres sont écrites en surcharge. Cf. v. 6915. — 9095', 1),
    ("texte-002", '<p class="variantes" title="p. 353">lacune. — 9790',
     '<p class="variantes" title="p. 353">9789 La restitution proposée est douteuse parce qu\'elle porte sur '
     'deux endroits du vers. Il est possible que l\'enlumineur ait mis une capitale pour une autre ; il est '
     'possible aussi qu\'il y ait ici une lacune. — 9790', 1),
]

# lignes de vers à supprimer (morceaux de notes) : motif de la ligne entière, <br /> qui la précède compris
LIGNES_OTEES = [
    ("texte-002", r"<br\s*/>\s*Ce vers semble une fin de phrase\. Lacune entre ce vers <span class=\"manchette\">et le</span>"),
    ("texte-002", r"<br\s*/>\s*persie, les deux dern\. lettres sont écrites en surcharge\. <span class=\"manchette\">Cf\.</span>"),
    ("texte-002", r"<br\s*/>\s*La restitution proposée est douteuse parce qu'elle <span class=\"manchette\">porte sur</span>"
                  r"<br\s*/>deux endroits du vers\. Il est possible que l'enlumineur ait <span class=\"manchette\">mis une</span>"
                  r"<br\s*/>capitale pour une autre[ \u00a0]*; il est possible aussi qu'il y ait <span class=\"manchette\">ici une</span>"),
]


def souple(a):
    """Motif exact, mais une espace autour de « » ; : ! ? peut être insécable (caractère ou entité)."""
    a = a.replace("&#160;", "\u00a0")
    out = []
    for k, c in enumerate(a):
        prec = a[k - 1] if k else ""
        suiv = a[k + 1] if k + 1 < len(a) else ""
        if c in " \u00a0" and (prec == "«" or suiv in "»;:!?"):
            out.append("[ \u00a0]")
        else:
            out.append(re.escape(c))
    return "".join(out)


def main():
    src, dst = sys.argv[1:3]
    zin = zipfile.ZipFile(src)
    zout = zipfile.ZipFile(dst, "w")
    for item in zin.infolist():
        data = zin.read(item.filename)
        nom = item.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if item.filename.endswith(".xhtml"):
            t = data.decode("utf-8").replace("&#160;", "\u00a0")
            for f, a, b, n in REMPLACEMENTS:
                if f == nom:
                    motif = souple(a)
                    k = len(re.findall(motif, t))
                    assert k == n, (f, a[:60], k)
                    t = re.sub(motif, lambda m: b, t)
            for f, motif in LIGNES_OTEES:
                if f == nom:
                    t, k = re.subn(motif, "", t)
                    assert k == 1, (f, motif[:50], k)
            # notes de variantes : manchettes = texte de la note ; « ~ » lu pour « — », « ^ » pour « ? »
            def note(m):
                x = re.sub(r'<span class="manchette">([^<]*)</span>', r"\1", m.group(2))
                x = re.sub(r" ~ (?=\d|Ibid|[A-Z])", " — ", x)
                x = re.sub(r"(?<=[a-zé])\^(?= —|\s*$)", "\u00a0?", x)
                return m.group(1) + x + m.group(3)
            t = re.sub(r'(<p class="[^"]*variantes[^"]*"[^>]*>)(.*?)(</p>)', note, t, flags=re.S)
            data = t.encode("utf-8")
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    print("Reprises appliquées : %d remplacements, %d lignes ôtées" % (len(REMPLACEMENTS), len(LIGNES_OTEES)))


if __name__ == "__main__":
    main()
