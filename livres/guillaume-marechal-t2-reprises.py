#!/usr/bin/env python3
"""Reprises du t. II de Guillaume le Maréchal (maître relu, marques retirées) avant les folios et la sortie
Gutenberg, vérifiées sur le PDF Google Livres :
  - balisage abîmé à la relecture (texte hors paragraphe, vocabulaire) ; fin du poème ;
  - derniers vers de page passés en tête de la note de variantes de la page : rendus au poème ;
  - vers perdus en haut ou en bas de page : rétablis d'après le PDF Google ;
  - morceaux de notes de variantes restés parmi les vers : remis dans la note ;
  - vers mal lus, ancres de page perdues ;
puis le contrôle général d'epub_vers_controle.py (numéros de vers, crochets, doubles signes, dates,
« ms. » mal lus, notes sans page), qui liste les écarts restants du compte des vers.

  python3 livres/guillaume-marechal-t2-reprises.py t2.epub t2-repris.epub google-t2.pdf
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from epub_vers_controle import controle, ecrire_epub, lire_epub, souple   # noqa: E402

PREMIER_VERS = 10153

# vers rendus au poème : (début de la note de variantes à retirer, fin du vers qui le précède dans le
# poème, vers inséré, manchette éventuelle)
VERS_RENDUS = [
    ("Tant que Franceis s'en ennui[é]rent, (f 75 c) ", "Que a prendre le[s] i couvint,",
     "Tant que Franceis s'en ennui[é]rent,", ""),
    ("En sa chambre entra esraument (85) ", "Ne pout [plus] durer a nul fuer :",
     "En sa chambre entra esraument ;", ""),
    ("Que li arcevesque morut (1205,13 juillet) ", "Fortune si près li corut",
     "Que li arcevesque morut", "(1205, 13 juillet)"),
    ("a Puet c'estre que li reis fera (f 91 b) f3711 ", "« Si Dieu pleist b[i]en la defendrons.",
     "« Puet c'estre que li reis fera", ""),
    ("a Ge m'i metrai molt volentiers, (f. 95 c) ", None, None, ""),     # déjà rendu à la relecture
    ("a Or seit baillez par. vostre acort (f. 96 d) ", "« &amp; ge voil bien qu'il seit a ese.",
     "« Or seit baillez par vostre acort", ""),
    ("Quant Loeïs s'en departi (30 septembre ?) ", "En orent fet ventes ou dons.",
     "Quant Loeïs s'en departi", "(30 septembre ?)"),
    ("Quant les napes ostées érent (f. 126 d) ", "« Car trop l'en verras corecié. »",
     "Quant les napes ostées érent", ""),
]
# vers perdus (souvent le premier ou le dernier d'une page), lus dans le PDF Google : (fin du vers qui
# précède, vers inséré)
VERS_AJOUTES = [
    ("Boen ne biel, ainz en out grant ire.", "Al rei Ric. emprist a dire"),                 # 10724
    ("Li reis o tot sa baronie,", "O sa reïne &amp; o sa gent,"),                           # 12007
    ("Ne sout que faire ne que dire,", "Quer ne volt a nului redire"),                      # 12204
    ("E Hue de Welles ensemble", "O lui ala, si com mei semble,"),                          # 12941
    ("Jugement ne refus ge pas", "« N'unc ne fis ne ja ne f[e]rai, »"),                     # 13163
    ("Si conduist la quarte bataille", "[…]"),                     # 16262, laissé en blanc dans le ms.
    ("« E sachiez que [je] lor dorrai", "« Opledane, mun bon mane[i]r,"),                  # 18239
]
# morceaux de notes de variantes restés parmi les vers (début du texte de la ligne) : ôtés des vers et
# remis en tête de la note de variantes qui suit
FRAGMENTS = [
    "déferez v. riere. 11685", "Corr. Li legaz Est le rei saveir", "fist, ms. fuist ou fiust. 11700",
    "se, ms. ce. 12442 Out.", "ici. : 12460 nos, ms. vos", "(par v) tenismis ; ce vers",
    "mencement du vers est resté en blanc.", "Il n'est pas sûr qu'il y ait crueté",
    "Une lettre grattée entre amenérent", "cestre, les lettres or sont écrites",
    "nel lose, la seconde 1 ajoutée", "chevetaigne avec un signe d'abréviation",
    "ners. 17353.", "d'aler s'atourt. Au v.", "Lacune après ce vers ? ou faut-il changer",
    "Corr. avison ? Autrement on pourrait",
]
# fin du poème : « Amen. » suivi de la dernière note de variantes, restée dans le paragraphe de vers
FIN = ('<p class="vers">Amen.<br /> qui m. s\'esjouirent.',
       '<p class="vers">Amen.</p>\n<p class="variantes" title="p. 331">19207 qui m. s\'esjouirent. 19208 orront, '
       'ms. orrornt. 19210 orront, ms. orrent. 19211 del, prem. leçon le. 19214 Et en toutes lettres.</p>')
# balisage abîmé à la relecture (paragraphe vide, texte hors paragraphe) : (fichier, avant, après)
BALISAGE = [
    ("texte-001", "11227 C'ert.</p>\n11239 prendre", "11227 C'ert. 11239 prendre"),
    ("texte-001", "11256 prise écrit sur grattage.<p />", "11256 prise écrit sur grattage.</p>"),
    ("texte-001", "(f. 102c)<br /> \n</p>\n\n15424 tient,", "(f. 102c)</p>\n<p class=\"variantes\">15424 tient,"),
    ("texte-001", '<span class="manchette">Lues</span><br />douteux', "Lues douteux"),
    ("texte-001", '<span class="manchette">(eves).</span><br /><a id="page-198" /> \n\nOn pourrait', "(eves). On pourrait"),
    ("texte-001", "ioeroie est très<p />\n<p class=\"vers\">\n", "ioeroie est très</p>\n<p class=\"vers\"><a id=\"page-198\" />"),
    ("texte-001", 'Quant li quens Johan, sans dotance,</p>\n<p class="vers">Sout del frére',
     'Quant li quens Johan, sans dotance,<br />Sout del frére'),            # premier vers, à la lettrine
    ("vocabulaire", "vagabond,</p>\n  homme de basse6", "vagabond, homme de basse"),
    ("vocabulaire", "gent pautoniére 778.<p />", "gent pautoniére 778.</p>"),
    # vocabulaire : titre courant pris pour un article, article coupé par la page, article « empris »
    ("vocabulaire", '<h1 id="glossaire">VOCABULAIRE.</h1>\n  <p class="glossaire"><a id="page-338" /><b>VOCABULAIRE</b></p>',
     '<h1 id="glossaire"><a id="page-338" />VOCABULAIRE.</h1>'),
    ("vocabulaire", 'a terre</p>\n  <p class="glossaire"><a id="page-339" />1673;', 'a terre <a id="page-339" />1673 ;'),
    ("vocabulaire", "pris subst., co'Mr.</p>\n  <p class=\"glossaire\"><i>Du Cange</i>, IMPRiSII, sous , IMPRISA. <br />\n"
     "<span class=\"glossaire\"><b>emprise</b> enprise 123</span>,2287,",
     "pris subst., conjurés. <i>Du Cange</i>, IMPRISII, sous IMPRISA.</p>\n  <p class=\"glossaire\"><b>emprise</b>, "
     "enprise 123, 2287,"),
    ("vocabulaire", "<b>A</b>, prdpos., combiné avec l'art. sing. masc. al, avec l'art. p/. masc.",
     "<b>A</b>, prépos., combiné avec l'art. sing. masc. al, avec l'art. pl. masc."),
    ("vocabulaire", "(personne ou c/toe)", "(personne ou chose)"),
]
# ancres de page perdues à la relecture (la table des pages y renvoie) : (page, début du vers qui l'ouvre)
ANCRES = [(8, "Fussent en repos longement"), (22, "Le voleit li reis d'Engletere"),
          (229, "A nos &amp; a toz nos lignages")]
# vers mal lus (texte entier de la ligne, numéros et manchettes à part)
VERS_RELUS = [
    ("a u mon conseu en tenez,", "« Qu'a mon conseil en ferïez,"),                         # 12485
    ("Or laissiez le conte venir, D.", "« Or laissiez le conte venir, »"),                   # 15460
    # crochets abîmés que la comparaison avec Google ne retrouve pas d'elle-même
    ("Revestuz vint]i archevesques,", "Revestuz vint li archevesques,"),
    ("E il]or dist a toz itant :", "E il lor dist a toz itant :"),
    ("« ([Lealment e a mon poeir,", "« Lealment e a mon poeir,"),
    ("A u[nje part le Mar. ;", "A u[ne] part le Mar. ;"),
    ("Mès saciez que de tot cel ma],", "Mès saciez que de tot cel mal,"),
    ("Tuit cil qui i voldront entendre ! [", "Tuit cil qui i voldront entendre !"),
    ("« Tuit nos tenons a cest acort.]) »", "« Tuit nos tenons a cest acort. »"),
    ("Mist]i quens isi ses ostaiges", "Mist li quens isi ses ostaiges"),
    ("Ci n'avez vos rien conquesté,]) »", "Ci n'avez vos rien conquesté, »"),
    ("« Contre mai &amp; pur mon damage.]) »", "« Contre mai &amp; pur mon damage. »"),
    ("« Nis Savari de Mallïon. ;])", "« Nis Savari de Mallïon. »"),
    ("Que]i reis de France chaï", "Que li reis de France chaï"),
    ("E boens serjanz qu'ijï] out trouvez", "E boens serjanz qu'i[l] out trouvez"),
    ("17730&amp;aprèssis'enretornérent.", "&amp; après si s'en retornérent."),                 # 17720
    ("« Qu'os [l'javez prise &amp; porchaci[é] e.", "« Qu'os [l']avez prise &amp; porchaci[é]e."),
]
# reste de la note après le vers retiré : premier numéro mal lu
NOTE_DEBUT = {"a Puet c'estre que li reis fera (f 91 b) f3711 ": "13711 "}


def main():
    src, dst, google = sys.argv[1:4]
    zin, docs, poeme = lire_epub(src)
    # 1. balisage abîmé à la relecture : réparations ponctuelles
    for n in docs:
        nom = n.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        for f, a, b in BALISAGE:
            if f == nom:
                assert docs[n].count(a) == 1, (f, a[:50], docs[n].count(a))
                docs[n] = docs[n].replace(a, b)
    # 1a. fin du poème
    k = 0
    for n in poeme:
        docs[n], j = re.subn(re.escape(FIN[0]) + r".*?</p>", lambda m: FIN[1], docs[n], flags=re.S)
        k += j
    assert k == 1, "fin du poème"
    # 2. derniers vers de page rendus au poème (vérifiés un à un)
    rendus = 0
    for note, apres, vers, man in VERS_RENDUS:
        n_note = [n for n in poeme if re.search(r'<p class="variantes" title="[^"]*">' + souple(note), docs[n])]
        assert len(n_note) == 1, (note, n_note)
        nn = n_note[0]
        docs[nn], k = re.subn(r'(<p class="variantes" title="[^"]*">)' + souple(note),
                              lambda m: m.group(1) + NOTE_DEBUT.get(note, ""), docs[nn])
        assert k == 1, note
        if apres is None:
            continue
        ligne = (" " + vers + (' <span class="manchette">%s</span>' % man if man else ""))
        trouve = 0
        for n in poeme:
            motif = r"(" + souple(apres) + r"(?:\s*<span class=\"numvers\">\d+</span>)?)(?=<br\s*/>\s*<a id=\"page-|</p>)"
            docs[n], k = re.subn(motif, lambda m: m.group(1) + "<br />" + ligne, docs[n])
            trouve += k
        assert trouve == 1, (apres, trouve)
        rendus += 1
    # 2b. vers perdus
    for apres, vers in VERS_AJOUTES:
        trouve = 0
        for n in poeme:
            motif = r"(" + souple(apres) + r"(?:\s*<span class=\"(?:numvers|manchette)\">[^<]*</span>)*)(?=\s*<br\s*/>|</p>)"
            docs[n], k = re.subn(motif, lambda m: m.group(1) + "<br />" + vers, docs[n])
            trouve += k
        assert trouve == 1, (apres, trouve)
        rendus += 1
    # 2c. morceaux de notes parmi les vers, remis en tête de la note de variantes suivante
    otes = 0
    for n in poeme:
        attente = []

        def para(m):
            nonlocal otes
            if m.group(2) == "variantes":
                if attente:
                    x = m.group(1) + " ".join(attente) + " " + m.group(3) + m.group(4)
                    attente.clear()
                    return x
                return m.group(0)
            garde = []
            for l in re.split(r"<br\s*/>", m.group(3)):
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", l).replace("\u00a0", " ").replace("&amp;", "&")).strip()
                if any(txt.startswith(f) for f in FRAGMENTS):
                    attente.append(re.sub(r'<span class="(?:numvers|manchette)">([^<]*)</span>', r"\1", l).strip())
                    otes += 1
                else:
                    garde.append(l)
            return m.group(1) + "<br />".join(garde) + m.group(4)
        docs[n] = re.sub(r'(<p class="(vers|variantes)[^"]*"[^>]*>)(.*?)(</p>)', para, docs[n], flags=re.S)
        assert not attente, attente
    # 2d. vers mal lus
    for avant, apres in VERS_RELUS:
        k = 0
        for n in poeme:
            docs[n], j = re.subn(souple(avant), apres, docs[n])
            k += j
        assert k == 1, (avant, k)
    # 2e. ancres de page perdues
    for page, debut in ANCRES:
        if any('id="page-%d"' % page in docs[n] for n in poeme):
            continue
        k = 0
        for n in poeme:
            docs[n], j = re.subn(r'(<br\s*/>|<p class="vers[^"]*">)(\s*(?:«[\s\u00a0]?)?)(?=' + re.escape(debut) + ")",
                                 lambda m: m.group(1) + '<a id="page-%d" />' % page + m.group(2), docs[n])
            k += j
        assert k == 1, (page, k)
    print("Reprises du t. II : %d réparations du balisage, %d vers rendus ou rétablis, %d morceaux de notes ôtés "
          "des vers, %d vers relus" % (len(BALISAGE), rendus, otes, len(VERS_RELUS)))
    # 3. contrôle général d'après Google (epub_vers_controle.py)
    print("\n".join(controle(docs, poeme, google, PREMIER_VERS, 19214)))
    ecrire_epub(zin, docs, dst)


if __name__ == "__main__":
    main()
