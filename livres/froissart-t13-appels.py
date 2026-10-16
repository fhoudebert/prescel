"""Corrections du tome 13 des Chroniques de Froissart (éd. Kervyn) pour scripts/epub_apparat_scan.py,
relues à vue sur la numérisation Internet Archive (pages de la numérisation = pages imprimées + 7).

VUES       vues de la numérisation hors de l'ordre des pages imprimées (vérifié par alignement du texte) :
           253 = p. 255, 255 = p. 253, 257 = doublon de la p. 254, 258 = p. 257, 259 = p. 258,
           286 = doublon de la p. 288 ; les pages imprimées 259 et 286 manquent à la numérisation.
DROP, ADD  appels relus à la main (planches --planche-appels) : appels détectés à écarter (rang 1.. dans
           l'ordre de détection) et appels manquants à ajouter (mot avant, mot après), par page imprimée.
PARTIAL    pages où un appel annoncé par l'apparat n'apparaît pas dans le texte imprimé.
EXPOSANTS  exposants des nombres romains lus sur la numérisation.
REMPLACEMENTS  retouches ponctuelles du texte.
"""
VUES = {253: 255, 255: 253, 257: None, 258: 257, 259: 258, 286: None}
DROP = {102: [1, 2, 3, 4], 148: [1], 196: [1, 2], 205: [5, 6], 208: [2], 307: [3, 4], 308: [1], 310: [6]}
ADD = {
    59: [("la", "venue")],
    107: [("Lighue", "en")],
    141: [("Bretaigne", "approcha")],
    198: [("Dame", "d"), ("Amont", "où")],
    199: [("Galice", "de"), ("parvenir", "à")],
    200: [("et", "l"), ("bon", "enscient"), ("enscient", "Et")],
    201: [("Guillemme", "de"), ("de", "Sethem"), ("Gladuvin", "messire"), ("de", "Struat"), ("Struat", None)],
    225: [("desconforteroient", None)],
    227: [("Abreton", "le")],
    232: [("départoit", "son")],
    237: [("accord", "dist"), ("recueillièrent", "Quant")],
    242: [("se", "daigna"), ("avoit", "prévu")],
    253: [("fois", "et")],
    256: [("retournée", "car")],
    278: [("despaisse", "de")],
    280: [("a", "meffait"), ("meffait", "Tant")],
    206: [("tout", "Trop")],
    316: [("temps", "de")],
}
# pages où un appel de l'apparat n'apparaît pas dans le texte imprimé : nombre d'appels réellement visibles
PARTIAL = {303: (5, "l'apparat annonce 5-6 ; l'appel 6 n'est pas visible sur la numérisation")}
# exposants lus sur la numérisation (vue, nombre, exposant, mot suivant) : exposant visible, souvent perdu ou mal lu par l'OCR
EXPOSANTS = [(17, "XII", "c", "lances"), (18, "IIII", "xx", "ans"), (24, "VI", "e", ""), (25, "III", "e", "jour"),
        (67, "IIII", "e", "seulement"), (72, "XIII", "e", "jour"), (76, "II", "c", "hommes"),
        (81, "IIII", "xx", "et"), (101, "VII", "m", "varlets"), (105, "VIII", "e", "jour"),
        (105, "XVI", "e", "jour"), (106, "XX", "e", "jour"), (133, "IIII", "xx", "et"), (135, "V", "c", "mille"),
        (139, "XXI", "e", "an"), (152, "IIII", "m", "combatans"), (155, "III", "c", "car"),
        (175, "VI", "xx", "Brabançons"), (178, "IIII", "xx", "et"), (182, "VII", "m", "lances"),
        (192, "VI", "e", ""), (201, "IIII", "xx", "et"), (215, "VIII", "m", "hommes"), (240, "IIII", "xx", "et"),
        (240, "XIX", "e", "jour"), (240, "XVIII", "c", "et"), (264, "IIII", "m", "hommes"),
        (274, "XXVII", "e", "de"), (278, "XXI", "e", "Et"), (289, "V", "c", "frans"), (309, "XX", "m", "frans"),
        (315, "IIII", "xx", "et"),
        (59, "XXII", "c", "frans"), (188, "XXV", "c", "tailleurs"), (369, "XXII", "e", "jour")]

# retouches relues sur la numérisation : (texte, remplacement) ou (motif, remplacement, "re") ;
# appliquées après les exposants, avant la levée des marques.
_M = r'<span class="a-verifier" title="[^"]*">'
_CHIFFRE = r'<span class="a-verifier" title="chiffre dans le récit[^"]*">(\d)</span>'
REMPLACEMENTS = [
    # mots collés par l'OCR dans un paragraphe rendu au corps
    ("Encespropresjoursquel'armée", "En ces propres jours que l'armée"),
    # p. 65 : « chastel de¹ Marqueil². » — « Et où est le conte daulphin… »
    (r"Mara que<sup class=\"var\">%s2</span></sup> il %ss</span>\.\xa0»-«" % (_M, _M),
     "Marqueil<sup class=\"var\">2</sup>.\xa0» — «", "re"),
    # p. 108, 119 : restes d'un guillemet ou d'un appel mal lus
    (r"recouvroit-%s'l'on" % _CHIFFRE, "recouvroit-l'on", "re"),
    (r"rompre %s\\ et" % _CHIFFRE, "rompre et", "re"),
    # p. 162 : « que nous ayons honneur »
    (r"nous %sn</span>\. yons" % _M, "nous ayons", "re"),
    # p. 200 : « l0 » = appel 10 mal lu
    (r"(ensemble<sup class=\"var\">10</sup>) %s%sl</span>0</span>," % (_M, _M), r"\1,", "re"),
    # p. 235 : guillemets de début de ligne lus « a », « n » ou perdus
    ("Si dist\xa0: Lindesée", "Si dist\xa0: «\xa0Lindesée"),
    (r"Qui estes-vous\xa0\? %sn</span> dist" % _M, "Qui estes-vous\xa0?\xa0» dist", "re"),
    # p. 244, 248 : guillemet de début de ligne lu « (1 »
    (r"conquer\(%s rai" % _CHIFFRE, "conquerrai", "re"),
    (r"\(%s (?=Et comment|Mal et laid)" % _CHIFFRE, "«\xa0", "re"),
    # p. 284 : « le sire de la Rivière, messire Guy de la Trimouille »
    (r"la %sI2ivièr</span> %se</span> messire Guy" % (_M, _M), "la Rivière, messire Guy", "re"),
    # p. 306 : « grandement⁵ les recueilly »
    (r"(grandement<sup class=\"var\">5</sup>) %sr</span>," % _M, r"\1", "re"),
    # p. 318-319 (dernière page, hors de la lecture de l'apparat) : mot de l'apparat dans « his-toire »,
    # appels de la p. 319 lus comme des chiffres, apparat de la p. 319 sans classe
    ("his-Clanvou.<a id=\"page-323\" /> toire", "his<a id=\"page-323\" />toire"),
    ("Grossoyée.-12-13 — 12-13 Convient.", "Grossoyée. — 12-13 Convient."),
    (r"(toire,|dira|clos je|m'ensonnyeray) %s" % _CHIFFRE, r'\1<sup class="var">\2</sup>', "re"),
    (r"<p>%s1</span>-%s2</span> Le me dire\. — %s3</span>-%s4</span> M'informeray\. m'ensongneray\.</p>" % ((_M,) * 4),
     "<p class=\"variantes\" title=\"p. 319\">1-2 Le me dire. — 3-4 M'informeray… m'ensongneray.</p>", "re"),
]
