#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retouches du t. III de Guillaume le Maréchal, vérifiées sur les images du DjVu, à appliquer une fois au
maître relu :

  python3 livres/guillaume-marechal-t3-retouches.py epub/Guillaume_le_Marechal_T3-a-relire.epub sortie.epub

Dans ce corps gras, Google lit souvent le chiffre « 1 » comme « \\ » et le paragraphe « § » de même :
numéros de vers des citations (« \\HOt » : 11401 ; « \\ \\ 085 » : 11085), renvois au poème entre
crochets (« [\\ 01 30] » : 10130), paragraphes de Rigord ou de Guillaume le Breton (« \\ 69 » : § 69),
appels de note (« jeune roi \\ qui » : roi¹, qui). Les citations en vers reprennent la forme des autres
(numéro de vers en fin de ligne, italique de l'imprimé). P. vii-ix : les vers 4312-4318 et la suite du
texte, passés par l'OCR dans la note 2 de la p. vii, sont remis à leur place. P. lxxxviii : la note 1,
passée dans le texte, est remise en note.
Chaque remplacement doit trouver son texte une fois exactement ; sinon le script s'arrête.
"""
import sys
import zipfile

NB = " "
AV = '<span class="a-verifier" title="%s">%s</span>'

# (fichier, texte lu, texte rétabli)
RETOUCHES = [
    # p. vi : v. 11401-11404
    ("partie-02", '<p class="vers">\\' + AV % ("Casse mélangée dans un mot HOt", "HOt") + " Quer nuls qui de trouver volt vivre<br />"
     "Ne deit chose metre en son livre<br />Qui de dreite raison ne vienge<br />\\" + AV % ("Chiffres dans un mot U0i", "U0i")
     + " N'|a la",
     '<p class="vers">Quer nuls <i>qui de trouver volt vivre</i> <span class="numvers">11401</span><br />'
     "Ne deit chose metre en son livre<br />Qui de dreite raison ne vienge<br />N'[a la"),
    ("partie-02", "</sup>] matyre n'apartienge.</p>", "</sup>] matyre n'apartienge. <span class=\"numvers\">11404</span></p>"),
    # p. viii : v. 11085-11087
    ("partie-02", '<p class="vers">\\ \\ 085 Molt fu la guerre grant et forz<br />Puis l\'asemblé[e] de Gisorz,<br /> Mol[t] dura '
     + AV % ("Lettres isolées e", "e") + " unquor[e] dure.</p>",
     '<p class="vers">Molt fu la guerre grant et forz <span class="numvers">11085</span><br />Puis l\'asemblé[e] de Gisorz,<br />'
     "<i>Mol[t] dura e unquor[e] dure.</i></p>"),
    # p. vii-ix : vers 4312-4318 et suite du texte rendus au texte ; notes viii-1, viii-2 reliées
    ("partie-02", "mourut le 6 avril 12312, et Jean",
     'mourut le 6 avril 1231<sup><a href="#note-vii-2" id="appel-vii-2">2</a></sup>, et Jean'),
    ("partie-02", "des vers suivants" + NB + ': <a id="page-ix" />se remaria',
     "des vers suivants" + NB + ":</p>\n"
     '<p class="vers">Mais unquor vesrons lieu et tens, <span class="numvers">4312</span><br />'
     "Si li reis Henri[s] d'Engletere<br /><i>Poeit en pais aveir sa terre</i><br />Que chivalerie e proece<br />"
     'E bonté de cuer et largesse <span class="numvers">4316</span><br />S\'en istreient parmi sa porte' + NB + ":<br />"
     "Si serreit avarice morte.</p>\n"
     "<p>Pour le dire en passant, ces vers sont bien d'un trouvère de profession, aux yeux de qui la vertu qui "
     "l'emportait sur toutes les autres était la largesse. Une allusion, du reste assez vague, à un récent manque de foi "
     "des Poitevins envers leurs seigneurs semble se rapporter à un fait de l'année 1224"
     '<sup><a href="#note-viii-1" id="appel-viii-1">1</a></sup>.</p>\n'
     "<p>Quelques synchronismes plus précis peuvent se tirer du passage où l'auteur nous parle des enfants du Maréchal "
     "(v. 14860 et suiv.). Il nous dit (v. 14933-6) que la seconde fille, Isabel, épousa le comte de Gloucester "
     '(Gilbert de Clare)<sup><a href="#note-viii-2" id="appel-viii-2">2</a></sup>. Celui-ci mourut en 1229 ou 1230, '
     'et sa veuve <a id="page-ix" />se remaria'),
    ("partie-02", '<p class="note" id="note-vii-2">2.' + NB + "Dict. ofnat. Biography, XXXVI, 223. 4312 Mais unquor",
     '<p class="note" id="note-vii-2"><a href="#appel-vii-2">2</a>. <i>Dict. of nat. Biography</i>, XXXVI, 223.</p>'
     "\n<p class=\"supprime\">4312 Mais unquor"),
    ("partie-02", '<p class="note" id="note-viii-1">1.' + NB, '<p class="note" id="note-viii-1"><a href="#appel-viii-1">1</a>. '),
    ("partie-02", '<p class="note" id="note-viii-2">2.' + NB, '<p class="note" id="note-viii-2"><a href="#appel-viii-2">2</a>. '),
    # p. xxxix, xcv, cvii, cxxviii, cxl
    ("partie-02", "au xnf siècle et à plus forte raison au xif\\ ne sont",
     "au xiii<sup>e</sup> siècle et à plus forte raison au xii<sup>e</sup>, ne sont"),
    ("partie-02", "(Gesta regis Henrici secundi\\,", "(<i>Gesta regis Henrici secundi</i>),"),
    ("partie-02", "perfeïsse \\\\ Mon devis", "perfeïsse || Mon devis"),
    ("partie-02", "au \\&gt;lur. prengent", "au plur. <i>prengent</i>"),
    ("partie-02", "de\\s]feit", "de[s]feit"),
    # p. lxxxviii : note 1 rendue à sa place
    ("partie-02", "barons anglais" + AV % ("Appel de note sans note (lu « 1 »)", "*") + ".",
     'barons anglais<sup><a href="#note-lxxxviii-1" id="appel-lxxxviii-1">1</a></sup>.'),
    ("partie-02", "s'imposait à \\. R. de Coggeshall, éd. Stevenson, p. 180" + NB + "; cf. Petit-Dutaillis, p. 93. <a id=\"page-lxxxix\" />lui",
     "s'imposait à <a id=\"page-lxxxix\" />lui"),
    ("partie-02", '<p class="note" id="note-xcii-1">',
     '<p class="note" id="note-lxxxviii-1"><a href="#appel-lxxxviii-1">1</a>. R. de Coggeshall, éd. Stevenson, p. 180'
     + NB + '; cf. Petit-Dutaillis, p. 93.</p>\n<p class="note" id="note-xcii-1">'),
    # traduction : appels de note, renvois au poème
    ("partie-05", "auprès du jeune roi \\ qui", 'auprès du jeune roi<sup><a href="#note-81-1" id="appel-81-1">1</a></sup>, qui'),
    ("partie-05", "bien utile 4\\" + NB + "»", 'bien utile<sup><a href="#note-103-4" id="appel-103-4">4</a></sup>' + NB + "!" + NB + "»"),
    ("partie-05", "Equiqueville \\ d'où", 'Equiqueville<sup><a href="#note-121-1" id="appel-121-1">1</a></sup>, d\'où'),
    ("partie-05", "Bradenstokes\\<sup>", "Bradenstokes<sup>"),
    ("partie-05", "[\\ 01 30]", "[10130]"),
    ("partie-05", "[1 \\ 068]", "[11068]"),
    ("partie-05", "[\\ \\ 084]", "[11084]"),
    ("partie-05", "[1 \\ 206]", "[11206]"),
    ("partie-05", "[\\ 2756]", "[12756]"),
    ("partie-05", "comte de Varenne \\ Philippe", 'comte de Varenne<sup><a href="#note-244-1" id="appel-244-1">1</a></sup>, Philippe'),
    ("partie-05", "[\\ 8723]", "[18723]"),
    ("partie-05", "aux mots plaidelces, plaid\\e\\ier, <i>plaidier</i>", "aux mots <i>plaideices</i>, <i>plaid[e]ier</i>, <i>plaidier</i>"),
    ("partie-05", "(Rigord, \\ 69", "(Rigord, § 69"),
    ("partie-05", "Chron., \\184", "Chron., § 184"),
    ("partie-05", "(Chron., \\ 72", "(Chron., § 72"),
    ("partie-05", "Roussil- Ion, \\ 462", "Roussillon</i>, § 462"),
    ("partie-05", "Rigord, \\ 140", "Rigord, § 140"),
    ("partie-05", "Chron., \\ 165", "Chron., § 165"),
    ("partie-05", "Wailly, \\ 295", "Wailly, § 295"),
    # table
    ("partie-06", "<p>— de \\er, comte d'Oxford", "<p>— de Ver, comte d'Oxford"),
    ("partie-06", "Wherwell(Varcsvalle)2\\2 (note)", "Wherwell (<i>Varesvalle</i>) 212 (note)"),
]


def main():
    src, dst = sys.argv[1], sys.argv[2]
    zin = zipfile.ZipFile(src)
    files = {n: zin.read(n) for n in zin.namelist()}
    for part, a, b in RETOUCHES:
        name = "OEBPS/Text/%s.xhtml" % part
        s = files[name].decode("utf-8")
        k = s.count(a)
        if k != 1:
            sys.exit("%s : « %s » trouvé %d fois" % (part, a[:70], k))
        files[name] = s.replace(a, b).encode("utf-8")
    # le paragraphe parasite (vers et texte de la p. viii passés dans la note vii-2) est retiré
    name = "OEBPS/Text/partie-02.xhtml"
    s = files[name].decode("utf-8")
    i = s.index('<p class="supprime">')
    j = s.index("</p>", i) + len("</p>")
    files[name] = (s[:i].rstrip("\n") + s[j:]).encode("utf-8")
    # « Roussillon</i> » ci-dessus : ouvrir l'italique
    s = files["OEBPS/Text/partie-05.xhtml"].decode("utf-8")
    s = s.replace("traduction de Girart de Roussillon</i>, § 462", "traduction de <i>Girart de Roussillon</i>, § 462")
    files["OEBPS/Text/partie-05.xhtml"] = s.encode("utf-8")
    zout = zipfile.ZipFile(dst, "w")
    for item in zin.infolist():
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, files[item.filename])
    zout.close()
    print("Retouches : %d" % len(RETOUCHES))


if __name__ == "__main__":
    main()
