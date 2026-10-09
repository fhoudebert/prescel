#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finitions du t. III de Guillaume le Maréchal après relecture (epub/Guillaume_le_Marechal_T3-a-relire.epub,
marques retirées), avant les fichiers Gutenberg :
- corrections faites à la main pendant la relecture, reportées sur les autres occurrences du même mot
  (« parait » → « paraît », « évéque » → « évêque », « Hisl. » → « Hist. ») ;
- mots coupés par une espace en fin de ligne de l'imprimé (« Angle terre », « plu sieurs », « Don né »)
  et traits d'union suivis ou précédés d'une espace (« Philippe- Auguste », « c'est-à -dire »,
  « Boulogne-sur -Mer ») ; les suffixes cités (« en -ter », « type -utus ») restent ;
- lectures fautives sûres relevées par epub_review.py (« l I » → « Il », « del' » → « de l' »,
  « DurTus » → « Duffus », « U96 » → « 1196 ») ;
- guillemets répétés en tête de ligne dans les citations (« Dame, on ne peut pas épe- « ronner ») retirés ;
- table alphabétique : l'article « Guillaume le Maréchal », coupé en paragraphes à chaque ligne de
  l'imprimé, est recollé (paragraphe sans ponctuation finale suivi d'une suite : nombre, minuscule ou
  nom après « de », « du », « à »…).
Chaque correction est comptée ; le script s'arrête si une correction attendue ne trouve plus rien
(texte déjà corrigé à la main : retirer la ligne).

  python3 livres/guillaume-marechal-t3-finitions.py t3-0.epub t3-f.epub
"""
import re
import sys
import zipfile

# Reports des corrections de la relecture : (motif, remplacement)
REPORTS = [
    (r"\bparait\b", "paraît"), (r"\breparait\b", "reparaît"), (r"\b(?:ainé|atné)\b", "aîné"),
    (r"\bévéque\b", "évêque"), (r"\bBenoit\b", "Benoît"), (r"\bCalai\b(?=[.,])", "Catal"),
    (r"\b(?:Hisl|Bist)\.", "Hist."), (r"\bl'Bisi\.", "l'Hist."), (r"\btète\b", "tête"),
    (r"\bl'Ile\b", "l'île"), (r"\bféte\b", "fête"), (r"\b(?:cetle|celte)\b", "cette"),
    (r"\bMarechal\b", "Maréchal"), (r"\bForét\b", "Forêt"), (r"\bDicl\b(?=[.,])", "Dict"),
    (r"\bélé\b", "été"), (r"\btlie\b", "the"), (r"\bfront Oie\b", "from the"), (r"\bcorn, 1099", "com, 1099"),
    (r"\bHais\b", "Mais"), (r"\blarda\b", "tarda"), (r"\bde libérale\b", "de liberate"), (r"\bflls\b", "fils"),
    (r"\bQuetieville\b", "Quetteville"), (r"\bMarescalius\b", "Marescallus"), (r"\bJebans\b", "Jehans"),
    (r"\bGraon\b", "Craon"), (r"\bGesla\b", "Gesta"), (r"\bFerilatem\b", "Feritatem"),
    (r"\bDclisle\b", "Delisle"), (r"\bCharMaries\b", "Chartularies"), (r"\bcuslos\b", "custos"),
    (r"\bofDermot\b", "of Dermot"), (r"\bBloet\b", "Bloët"),
]

# Mots coupés par une espace (ligne de l'imprimé) ; motif exact → mot
COUPES = """co mte|comte  Angle terre|Angleterre  Phi lippe|Philippe  mou rut|mourut  plu sieurs|plusieurs
Plu sieurs|Plusieurs  beau coup|beaucoup  ail leurs|ailleurs  entre vue|entrevue  toute fois|toutefois
Toute fois|Toutefois  long temps|longtemps  main tenant|maintenant  Poi tou|Poitou  Don né|Donné
bien tôt|bientôt  r egis|regis  trou ver|trouver  chance lier|chancelier  rai son|raison  pré sent|présent
cher cher|chercher  con sentit|consentit  mes sage|message  Mal gré tous|Malgré tous  pou voir|pouvoir
for tune|fortune  For tune|Fortune  As siège|Assiège  don nées|données  ré volte|révolte
entre prise|entreprise  con naître|connaître  cor rompu|corrompu  con venait|convenait  pré paraît|préparait
pro duit|produit  sen tant|sentant  or donne|ordonne  assis tait|assistait
entre prenant|entreprenant  pro mis|promis  Cher bourg|Cherbourg  cour roux|courroux  Quelque fois|Quelquefois
plan tain|plantain  Harden court|Hardencourt  dé livre|délivre  Pré tend|Prétend
tac tique|tactique  pré valut|prévalut  inter rompue|interrompue  contre balancer|contrebalancer
main tient|maintient  pro jet|projet  pro testa|protesta  rem parts|remparts  ré clamé|réclamé
con tenus|contenus  De vient|Devient  au près|auprès  ré tif|rétif  ras semble|rassemble  Beau vais|Beauvais
Man tes|Mantes  do nation|donation  bel le lum|bellum  parti sans du|partisans du  par donne|pardonne
prison nier|prisonnier  Il en voie|Il envoie  l'ai de donnée|l'aide donnée  Henri I I|Henri II
X XX I I|XXXII  an nées|années  plu part|plupart  sen tir|sentir  ras sembla|rassembla
atten dez|attendez  per sonne|personne  rem plaça|remplaça  sauf-con duit|sauf-conduit  Voirp.8|Voir p. 8  (t cueiu|li cuens  Bonnevillesur|Bonneville-sur  Worcesteravec|Worcester avec"""
COUPES = [x for x in re.split(r"\s{2,}|\n", COUPES) if x.strip()]

# Lectures fautives sûres : (motif, remplacement)
OCR = [
    (r"\{", "("), (r"\}", ")"),                       # parenthèses lues en accolades (« {Rot. chart. »)
    (r"\bdel'", "de l'"), (r"(?<![\w'])l I\b", "Il"), (r"\blévêque\b", "l'évêque"), (r"\bI I\b", "II"),
    (r"(?<=[.!?] )II (?=[a-zé])", "Il "), (r"\b11y a\b", "Il y a"), (r"\bIlyadans\b", "Il y a dans"),
    (r"\bformequi\b", "forme qui"),
    (r"\béd\. FOrster\b", "éd. Förster"), (r"\bCambrUe\b", "Cambriæ"), (r"\bqueLavostre\b", "que La vostre"),
    (r"\bDurTus\b", "Duffus"), (r"\bannoUted\b", "annotated"), (r"\bHistorUv anglicanx\b", "Historiæ anglicanæ"),
    (r"\bCotL charters\b", "Cott. charters"), (r"\bVVigani\b", "Wigani"), (r"\bOfQcium\b", "Officium"),
    (r"\bNormannUe\b", "Normanniæ"), (r"\bVArchxologia\b", "l'Archæologia"), (r"\blUntrartum Ricardl\b",
    "Itinerarium Ricardi"), (r"\bdeLongchamp\b", "de Longchamp"), (r"\bl'IIe-aux-Bœufs", "l'Île-aux-Bœufs"),
    (r"\bVHLst\.", "l'Hist."), (r"\bjuxtaWarrham\b", "juxta Warrham"), (r"\bWareAam\b", "Wareham"),
    (r"\bVUleloin\b", "Villeloin"), (r"\bVExpugnatio\b", "l'Expugnatio"), (r"\bCaL of\b", "Cal. of"),
    (r"\bRot\. (?:tiU|lUt)\. (?:clans|elaus)\.", "Rot. litt. claus."), (r"\brot\. scacc\. TVorm\.", "rot. scacc. Norm."),
    (r"\bannée U96\b", "année 1196"), (r"\bI, H58\b", "I, 1158"), (r"\b12 juin H89\b", "12 juin 1189"),
    (r"Poitevins\(H68\)", "Poitevins (1168)"), (r"Boutavant\(l197\)", "Boutavant (1197)"),
    (r"\bxiii0 siècle", "xiiie siècle"), (r"\b8ir John Sa vile\b", "Sir John Savile"),
    (r"\bSir Henry 8a vile\b", "Sir Henry Savile"), (r"\b(Howden|Hardy|Robert), 11I\b", r"\1, III"),
    (r"\bRobert 11I\b", "Robert III"), (r"\bDicet, 1I\b", "Dicet, II"), (r"\bLe([24]) (juillet|septembre)\b",
    r"Le \1 \2"), (r"\bl e8 décembre 1 174\b", "le 8 décembre 1174"), (r"\bl e1 octobre\b", "le 1er octobre"),
    (r"\bedited by6\. H\. Orpen\b", "edited by G. H. Orpen"), (r"\bFils 6erout\b", "Fils Gerout"),
    (r"\b8imonde\b", "Simonde"), (r"\bFreemantleI\b", "Freemantle"), (r"\bMar[éê]chai\b", "Maréchal"),
]

# Remplacements dans le XHTML (à cheval sur une balise ou un paragraphe), vérifiés sur le DjVu
BRUT = [
    ("Hou <i>sehold", "<i>Household"),
    ("Il se amèrement de ses fils,</p>\n<p>Slaint 198, 8269. Se rend au Dorât",       # p. 284 de la table
     "Il se plaint amèrement de ses fils, 8198, 8269. Se rend au Dorat"),
    ('[224<sup><a href="#note-4-4" id="appel-4-4">4</a></sup>] *.',                 # p. 4 : « [224]⁴. »
     '[224]<sup><a href="#note-4-4" id="appel-4-4">4</a></sup>.'),
    ("<p>4729. Jean, quatrième fils", "<p>4729.</p>\n<p>Jean, quatrième fils"),          # nouvel article
]

# Traits d'union isolés par une espace
TRAITS = [
    (r"\b(Saint|Sainte|Philippe|Château|Sans|Aiguës|sur|le)- (?=[A-ZÉ])", r"\1-"),
    (r"\b(Philippe|sur|Pont) -(?=[A-ZÉ])", r"\1-"), (r"\bà -dire\b", "à-dire"),
    (r"\bt -(il|on|elle)\b", r"t-\1"), (r"\b([Cc]i)[- ] ?-?(après|dessus|dessous)\b", r"\1-\2"),
    (r"\bAllez- vous-en\b", "Allez-vous-en"), (r"(?<![\d,])\b(\d+)- (\d+)\b", r"\1-\2"),
    (r"(?<![\d,])\b(\d+) -(\d+)\b", r"\1-\2"),
]


def sur_le_texte(s, fn):
    """Applique fn aux morceaux de texte, pas aux balises."""
    return "".join(p if p.startswith("<") else fn(p) for p in re.split(r"(<[^>]+>)", s))


SENTINELLE = "\ue000"
PRONOMS = set("moi toi vous nous lui leur le la les en y je tu il elle on ils elles ce t".split())


def guillemets_de_ligne(s, vocab):
    """L'imprimé répète « en tête de chaque ligne d'une citation ; dans un paragraphe ouvert par « (ou qui
    continue une citation du paragraphe précédent), un « qui n'est pas en tête de paragraphe est un de ces
    guillemets de ligne : retiré. Un mot coupé à cet endroit (« épe- « ronner ») est recollé, avec son
    trait d'union s'il en a un ailleurs dans le livre (« par-dessus »)."""
    ouvert, n = False, 0

    def para(m):
        nonlocal ouvert, n
        morceaux = re.split(r"(<[^>]+>)", m.group(0))
        debut = True
        for i, t in enumerate(morceaux):
            if t.startswith("<"):
                continue
            out = []
            for c in t:
                if c == "«":
                    if ouvert and not debut:
                        out.append(SENTINELLE)
                        n += 1
                    else:
                        out.append(c)
                    ouvert = True
                elif c == "»":
                    out.append(c)
                    ouvert = False
                else:
                    out.append(c)
                if not c.isspace():
                    debut = False
            morceaux[i] = "".join(out)
        return "".join(morceaux)
    s = re.sub(r"<p\b[^>]*>.*?</p>", para, s, flags=re.S)

    def coupe(m):
        a, b = m.group(1), m.group(2)
        if (a + "-" + b).lower() in vocab or b.lower() in PRONOMS:      # « Désarmez-vous », « dit-il »
            return a + "-" + b
        return a + b
    s = re.sub(r"(\w+)- ?%s[\s\u00a0]*(\w+)" % SENTINELLE, coupe, s)
    s = re.sub(SENTINELLE + r"[ \u00a0]?", "", s)
    return s, n


# début d'une phrase qui continue un long article de la table (« Guillaume le Maréchal », « Henri II »)
SUITE = re.compile(r"(?:Il|Ils|Ses|Son|Sa|Se|S'|Au|Aux|Avec|Puis|On|Ces|Contrairement|Fait|Envoie|Envoyé|Armé|Revient"
                   r"|Retourne|Reste|Joue|Devient|Est|Lui|Cependant|Celui-ci|Prend|Assiège|Va|Vient|Passe|Donne|Attaque"
                   r"|Chevauche|Fortifie|Couronné|Rencontre|Fait duc|Prise de|Malade|Meurt|Mort|Trois jours|Louis parti|Jean revenu|Tombe"
                   r"|Le (?:Maréchal|comte|roi|grand|cardinal)|La (?:paix|flotte|nouvelle)|Les deux)\b")


PARTICULES = set("de du des le la les of sur sous lès aux au et".split())


def phrase(t):
    """« Chemin faisant, il… », « Ces deux comtes… », « Tombe à l'eau… » : une phrase, pas un nom d'article
    (« Alain Basset 10761 », « Hubert du Bourg (Bure) », « Jean, quatrième fils… »)."""
    m = re.match(r"([A-ZÀ-Ý][\w'’-]*) ([a-zà-ÿ][a-zà-ÿ'’-]*)(?=[\s,])", t)
    return bool(m) and m.group(2) not in PARTICULES


def recoller_table(s):
    """Table : un paragraphe est rattaché au précédent quand celui-ci n'a pas de ponctuation finale (coupure
    de ligne de l'imprimé), ou quand il commence une phrase d'un long article (mot hors de l'ordre
    alphabétique de la table, ou début de phrase de SUITE)."""
    morceaux = re.split(r"(<p>(?:(?!</p>).)*?</p>)", s, flags=re.S)
    n, prec = 0, None                     # prec : indice du dernier paragraphe <p> gardé
    for i, m in enumerate(morceaux):
        if not m.startswith("<p>"):
            if m.strip():
                prec = None                          # titre, autre bloc : pas de recollage par-dessus
            continue
        b = m[3:-4]
        tb = re.sub(r"<[^>]+>", "", b).strip()
        if prec is not None and tb and not tb.startswith("—"):
            a = morceaux[prec][3:-4]
            ta = re.sub(r"<[^>]+>", "", a).strip()
            fin = re.search(r"[.;:!?)»\]]$", ta) and not ta.endswith("voy.")
            joindre = False
            if not fin:
                joindre = not (ta.endswith(",") and not re.match(r"[\d(\[]", tb))   # « Dammartin, … »
            else:
                joindre = (re.search(r"\d\.$|\(note\)\.$", ta) and bool(SUITE.match(tb))) or phrase(tb)
            if joindre:
                sep = "" if ta.endswith("-") else " "
                morceaux[prec] = "<p>%s%s%s</p>" % (a.rstrip(), sep, b.lstrip())
                morceaux[i] = ""
                if i > 0 and not morceaux[i - 1].strip():
                    morceaux[i - 1] = ""
                n += 1
                continue
        prec = i
    return "".join(morceaux), n


def main():
    src, dst = sys.argv[1], sys.argv[2]
    zin = zipfile.ZipFile(src)
    regles = [(re.compile(p), r, "report") for p, r in REPORTS]
    regles += [(re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)"), b.replace("\\", r"\\"), "coupure")
               for a, b in (x.strip().split("|") for x in COUPES if x.strip())]
    regles += [(re.compile(p), r, "ocr") for p, r in OCR] + [(re.compile(p), r, "trait") for p, r in TRAITS]
    compte = {p.pattern: 0 for p, _, _ in regles}
    sortie = {}
    recolles = retires = 0
    compte_brut = {}
    tout = " ".join(re.sub(r"<[^>]+>", " ", zin.read(n).decode("utf-8")) for n in zin.namelist()
                    if n.endswith(".xhtml"))
    vocab = {w.lower() for w in re.findall(r"\w+(?:-\w+)+", tout)}
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith(".xhtml"):
            s = data.decode("utf-8")
            for a, b in BRUT:
                k = s.count(a)
                s = s.replace(a, b)
                compte_brut[a] = compte_brut.get(a, 0) + k
            if re.search(r"partie-0[245]\.xhtml$", item.filename):          # prose (pas la chronologie, la table)
                s, k = guillemets_de_ligne(s, vocab)
                retires += k
            i = s.index("<body")

            def fn(t):
                for p, r, _ in regles:
                    t, k = p.subn(r, t)
                    compte[p.pattern] += k
                return t
            s = s[:i] + sur_le_texte(s[i:], fn)
            if item.filename.endswith("partie-06.xhtml"):
                s, recolles = recoller_table(s)
            data = s.encode("utf-8")
        sortie[item.filename] = (item, data)
    vides = [p for p, k in list(compte.items()) + list(compte_brut.items()) if k == 0]
    if vides:
        sys.exit("Corrections sans effet (déjà faites ?) :\n  " + "\n  ".join(vides))
    zout = zipfile.ZipFile(dst, "w")
    for name, (item, data) in sortie.items():
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    par = {}
    for p, _, genre in regles:
        par[genre] = par.get(genre, 0) + compte[p.pattern]
    print("Reports de la relecture : %(report)d ; mots recollés : %(coupure)d ; lectures corrigées : %(ocr)d ; "
          "traits d'union : %(trait)d" % par)
    print("Guillemets de ligne retirés : %d ; table : %d paragraphes recollés" % (retires, recolles))


if __name__ == "__main__":
    main()
