#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Passe sur les notes du t. III de Guillaume le Maréchal (maître relu, notes de bas de page de
l'introduction et de la traduction), à appliquer une fois au maître :

  python3 livres/guillaume-marechal-t3-notes.py epub/Guillaume_le_Marechal_T3-a-relire.epub sortie.epub

Les notes, en petit corps, sont la partie la plus mal lue par l'OCR de Google. Chaque note a été
alignée sur les deux autres lectures (ABBYY d'Internet Archive et Tesseract sur les images du DjVu) ;
les corrections ci-dessous sont celles où ces lectures s'accordent contre le texte, relues une à une,
et quelques fautes régulières des notes :
- guillemets lus « c », « t », « f », « < », « • » (ouvrants) et « i », « î », « > », « i> », « ■ »
  (fermants) : rétablis d'après l'équilibre des guillemets dans la note ; un guillemet de ligne
  répété dans une citation est retiré ;
- « n* », « n" », « a* » → « n° » ; « 2* partie » → « 2e partie » ; « xvi* » → « xvie » ;
  « Henri I" » → « Henri Ier » ; « air. » → « arr. » ; « Ch. -I. » → « Ch.-l. » ; « g 94 » → « § 94 » ;
- « li » et « 11 » pour « Il » en début de phrase, devant un verbe (« li mourut », « 11 figure ») ;
  « li » de l'ancien français cité (« li cuens ») reste.
Les corrections particulières sont cherchées telles quelles dans la note ; une correction qui ne
trouve plus son texte est signalée (déjà faite à la main ?) sans arrêter le script.
"""
import html
import re
import sys
import zipfile

VERBES_IL = r"(?:est|était|revient|faut|y|s'agit|avait|s'était|obtient|accompagna|mourut|combattit|composait|fut|" \
            r"devait|se|ne|n'est|figure|devait|nous|possédait|conte|contribua|périt|joint|dut|suit|devint|" \
            r"mourut|était|combattit|est|faut)"
MOIS = r"(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"

GENERIQUES = [
    (r"(?<![\w])[na][*\"'»1•]\s?(?=\d)", "n° "),                      # n* 75, n" 361, a* 428
    (r"\b(\d)\*\s(?=partie|éd\.|édit|série|vol)", r"\1e "),             # 2* partie
    (r"\b([xvi]+)\*(?= siècle)", r"\1e"),                               # xvi* siècle
    (r"\b(Henri|Richard|Raoul|Adam|Guillaume|Philippe|Giffard) I\"", r"\1 Ier"),
    (r"(?<=^\. )Ait\.", "Arr."), (r"\b(?:air|Ait)\.(?= de| des)", "arr."),
    (r"\bC[hb]\. ?-[Il1]\.", "Ch.-l."),
    (r"\b(Rigord|Breton|Roussillon), g (?=\d)", r"\1, § "), (r"\((?:g|S) (?=\d)", "(§ "), (r"\bS (?=97 et)", "§ "),
    (r"(?:(?<=^)|(?<=[.!?)] )|(?<=— ))(?:li|11|1 1)(?= %s\b)" % VERBES_IL, "Il"),        # début de phrase
    (r"(?<=[,;] )li(?= %s\b)" % VERBES_IL, "il"),
    (r"\b(où|et|car|dont|qui|mais|que) li(?= %s\b)" % VERBES_IL, r"\1 il"),
    (r"(?<=^\. )(?:11|li|1 1)(?= [a-zé])", "Il"),                      # « 3. 11 devait » (après le numéro)
    (r"\b1 1(?= %s)" % MOIS, "11"),
    (r"(?<=[.!?] )II(?= (?:y|[a-zé]{2,})\b)", "Il"),                     # « plus tard. II y a »
    (r"\bliberale\b", "liberate"),
]

# corrections particulières (lecture fautive → lecture des deux autres OCR, vérifiée)
PARTICULIERES = """King Henri II|King Henry II
King Henri 11|King Henry II
Henri 11 and|Henry II and
Henry il and|Henry II and
Je no connais|Je ne connais
edited hy|edited by
Truies|Troies
et Vin, 174|et VIII, 174
Métn.|Mém.
ad suatn|ad suam
i son peut|si on peut
j e ne sais|je ne sais
a dù être|a dû être
selon H. Round|selon M. Round
tlandevilte|Mandeville
H. Honey|M. Money
parlie,|partie,
Plani-names|Plant-names
â l'occasion|à l'occasion
Henri U,|Henri II,
c'eut été|c'eût été
no vêles|noveles
à H. Longnon|à M. Longnon
consecrations|consecrationis
c qni|« qui
sniv.,|suiv.,
Boucbet, Hut.|Bouchet, Hist.
Ihe first|the first
Laoo,|Laon,
XLVI1-XL1X|XLVII-XLIX
Sobertus|Robertus
UU&aire|littéraire
; bumero|; humero
aigui)|aiguë
acula)|acuta)
Rob. de l'or.|Rob. de Tor.
Bibt.,|Bibl.,
soeurs|sœurs
en posture|en pasture
Piusfolque|Plus fol que
Reinaut de l'ou ; or, l'ou,|Reinaut de Vou ; or, Vou,
De instructions principes|De instructione principis
(1I,|(II,
compulsas|compulsus
de t École|de l'École
reversas|reversus
du Haine|du Maine
(Il, 68)|(II, 68)
ac i s,|ac si,
scacc</i>. Nom.,|scacc</i>. Norm.,
ducs de Nom.,|ducs de Norm.,
Monas ttcon|Monasticon
vix annulas|vix annulus
Rex l'home|Rex Thome
de aile,|de gile,
; Esioire|; Estoire
Breweh|Brewer
i e nec|ei nec
prise d'Erreux|prise d'Évreux
Pkil.,|Phil.,
lopogr.|topogr.
doc. Tel.|doc. rel.
doc. r&.|doc. rel.
savoir i s,|savoir si,
plus tard, i s,|plus tard, si,
t e des rois|et des rois
pius prelio|plus pretio
Beawlemont|Beaudemont
entevée|enlevée
entevé|enlevé
entever|enlever
chasleU|chastels
christ iatia|christiana
Cantuarieno sem|Cantuariensem
Marescalium, comilem|Marescallum, comitem
(Delislc, Calât,|(Delisle, Catal.,
SI Edmund's|St Edmund's
de l'ôtes,|de Tôtes,
de Y Art|de l'Art
Monlfort|Montfort
d'ar — t gent|d'argent
mare tranc siturus|mare transiturus
Sfonasterium|Monasterium
Di Ceinnsealaigh|Ui Ceinnsealaigh
tantôt Hase|tantôt Hose
national mu.|national mss.
172 o,|172 a,
d'oeil|d'œil
témoin1 un|témoin à un
Prendelgasl.|Prendelgast.
Noos n'avons|Nous n'avons
s'ètant|s'étant
ma].,|maj.,
la Hoc belle|la Rochelle
Notum sil…|Notum sit…
Mit. des ducs|Hist. des ducs
Corc cellis|Corcellis
i s « Deus eam|si Deus eam
i e dederit|ei dederit
No€l|Noël
note du r. 15580|note du v. 15580
Douet d'Arcq|Douët d'Arcq
voy. J9ic|voy. Dict
Dict<. of|Dict. of
Lincoln â ce|Lincoln à ce
R. de Vend.,|R. de Wend.,
génial, de la maison|généal. de la maison
17S8). Ou|1788). On
anic mati|animati
qui longuement ot|qui longhement ot
Entas, v. 685|Eneas, v. 685
Ut dates|les dates
Mémoires présentes|Mémoires présentés
Magni roi. scacc.|Magni rot. scacc.
Lions-Ia-|Lions-la-
réfèrent an père|réfèrent au père
(Hanche,|(Manche,
la Hanche,|la Manche,
Stubbs, I, SI,|Stubbs, I, 51,
tome 111|tome III
Jean fil pour|Jean fit pour
cour do roi|cour du roi
. lis. <i>Glaskant|. Ms. <i>Glaskant
plus lard.|plus tard.
Louis, (ils de|Louis, fils de
de ses (ils,|de ses fils,
(Bot. chart.|(Rot. chart.
; DM. of.|; Dict. of
Maréchal ; joua|Maréchal y joua
qu'il ; avait|qu'il y avait
ou a peu près|ou à peu près
témoin a divers|témoin à divers
tenue a Oxford|tenue à Oxford
intercaler ça et là|intercaler çà et là
ducs (le Norm.|ducs de Norm.
note 1), on de sa terre|note 1), ou de sa terre
Monumental effigie »|Monumental effigies
tepultura|sepultura
adeo ofl'en — « dit eos|adeo offendit eos
Cakville|Canville
était i Westminster|était à Westminster
Chandeleur (ï février|Chandeleur (2 février
l'Irlande. A. Voir|l'Irlande. — 4. Voir
fuilc|fuite
reparaitra|reparaîtra
c0 innata|« O innata
Henri II i Tours|Henri II à Tours
Blanchejlewr|Blanchefleur
Simon de Harès|Simon de Marès
Il esta supposer|Il est à supposer
en 1W6,|en 1196,
mitls|misis
equites tot et taies|equites tot et tales
Aussy, Hut.|Aussy, Hist.
ki moul fu|ki mout fu
corpus sepulture)|corpus sepulturæ
Hues 11 c castelains|Hues li castelains
Defuncto o Richardo|Defuncto Richardo
arbi t trantur|arbitrantur
Roll f o the|Roll of the
Étienne. HI1|Étienne.
Norfolk. m3|Norfolk.
Henri III. m4|Henri III.
note 2. UI5|note 2.
le m6 jeune|le jeune
de France. Ul7|de France.
bien souvent. III 10|bien souvent.
date m 15 du|date du
qu'elle m16 déploya|qu'elle déploya
col. 1. m 17|col. 1.
tlie|the
tfte|the
llie|the
Hisiory|History
Hlstory|History
Victionary|Dictionary
Anarclty|Anarchy
thirleentfi|thirteenth
iliustrative|illustrative
exactemeot|exactement
quinlana|quintana
fragmenium|fragmentum
fiagmentum|fragmentum
Normannkv|Normanniæ
Normannùe|Normanniæ
Normanniaa|Normanniæ
Uém.|Mém.
Anliq.|Antiq.
ils'était|il s'était
sudouest|sud-ouest
nordouest|nord-ouest
nordest|nord-est
luimême|lui-même
Peter borougb|Peterborough
Mclun|Melun
Formcrie|Formerie
Beanvais|Beauvais
Mandcville|Mandeville
Chcsnc|Chesne
Doufit|Douët
Eusta chiusde|Eustachius de
d'Englelerre|d'Engleterre
(Esloire|(Estoire
fuerunl|fuerunt
concordix|concordiæ
seaee.|scacc.
scaee.|scacc.
Scaec.|Scacc.
Gexta|Gesta
Pont-del'Arche|Pont-de-l'Arche
Revoiution|Revolution
Lonqghamp|Longchamp
Mahescallus|Marescallus
facereot|facerent
persequcntium|persequentium
Columbac|Columbae
solilo|solito
reliquerec tur|relinqueretur
Hiss Norgate|Miss Norgate
aanctae|sanctae
Stapletoa|Stapleton
Huutingdon|Huntingdon
Notlingham|Nottingham
Engtand|England
colloqnerentur|colloquerentur
murnrum|murorum
iinpetum|impetum
Britanniee|Britanniæ
Pirtavcnsibus|Pictavensibus
esscl|esset
geutis|gentis
lournoier|tournoier
Rotuti|Rotuli
letleraria|letteraria
tidei|fidei
lenentes|tenentes
tiliis|filiis
tilii|filii
Sthongbow|Strongbow
Fitzpetbr|Fitzpeter
Christ-Cburcb|Christ-Church
Bothomag.|Rothomag.
XVHI|XVIII
XXUI|XXIII
Saint-Jcand'Acre|Saint-Jean-d'Acre
Saint-Jeand'Acre|Saint-Jean-d'Acre
Montfortl'Amaury|Montfort-l'Amaury
l'Ilede-France|l'Île-de-France
Newcastleupon-Tyne|Newcastle-upon-Tyne
vers le l'raoùt|vers le 1er août
Brian Uls du comte|Brian fils du comte
Wilts et de Hauts|Wilts et de Hants
nacti praconil|nacti præconii"""


def corriger_note(inner, compte):
    """Corrige le texte d'une note (XHTML intérieur du paragraphe) ; balises intactes."""
    morceaux = re.split(r"(<[^>]+>)", inner)
    textes = [i for i, m in enumerate(morceaux) if not m.startswith("<")]
    # 1. guillemets : jetons isolés, avec l'état ouvert / fermé de la note
    ouvert = False
    for i in textes:
        t = html.unescape(morceaux[i])
        t = re.sub(r"(?<![\w'])f (?=1[01]\d\d\b)", "† ", t)        # « f 1191 » : mort en 1191
        out = []
        for tok in re.split(r"(\s+)", t):
            nu = tok.strip()
            avant = "".join(out)
            debut_mot = not avant or avant[-1].isspace() or avant[-1] in "(["
            prec = avant.split()[-1] if avant.split() else ""
            if nu in ("c", "t", "f", "<", "•") and debut_mot and nu == tok and \
                    not re.fullmatch(r"[\dIVXLCivxlc]+[a-d]?,?|une?|le|la|l'|Une?", prec):   # « 78 c », « Une f est »
                # guillemet ouvrant mal lu (suivi d'un mot) ; dans une citation ouverte : guillemet de ligne
                if ouvert:
                    out.append("\x00")
                    compte["guillemets"] += 1
                    continue
                out.append("«")
                ouvert = True
                compte["guillemets"] += 1
                continue
            if nu in ("î", ">", "i>", "■", "i") and tok == nu and avant and not avant.rstrip().endswith(("«", "(")):
                if nu != "i" or ouvert and re.match(r"\s*(?:$|[A-ZÀ-Ý(\[.,;:]|(?:ou|dont|qui|à|et|mais|ce|est|"
                                                    r"c'est|dit|lisez|ne|que)\b)", t[len("".join(out)) + 1:]):
                    out.append("»")
                    ouvert = False
                    compte["guillemets"] += 1
                    continue
            ouvert = (ouvert or "«" in tok) and not ("»" in tok and tok.rfind("»") > tok.rfind("«"))
            out.append(tok)
        t = re.sub(r"\x00\s*", "", "".join(out))
        morceaux[i] = html.escape(t, quote=False)
    inner = "".join(morceaux)
    # 2. règles générales, sur le texte seulement
    morceaux = re.split(r"(<[^>]+>)", inner)
    for i, m in enumerate(morceaux):
        if m.startswith("<"):
            continue
        t = html.unescape(m)
        for pat, rep in GENERIQUES:
            t, k = re.subn(pat, rep, t)
            compte["règles"] += k
        morceaux[i] = html.escape(t, quote=False)
    return "".join(morceaux)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    zin = zipfile.ZipFile(src)
    part = [ligne.split("|", 1) for ligne in PARTICULIERES.split("\n") if ligne.strip()]
    trouve = {a: 0 for a, _ in part}
    compte = {"guillemets": 0, "règles": 0}
    zout = zipfile.ZipFile(dst, "w")
    notes = 0
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith(".xhtml") and not item.filename.endswith("partie-03.xhtml"):
            s = data.decode("utf-8")

            def note(m):
                nonlocal notes
                notes += 1
                # marques de relecture retirées des notes (la passe en tient lieu)
                inner = re.sub(r'<span class="a-verifier"[^>]*>(.*?)</span>', r"\1", m.group(2), flags=re.S)
                for a, b in part:                      # d'abord les corrections particulières
                    brut = "<i>" in a or "</i>" in a                    # motif écrit avec ses balises (« <i> »)
                    pat = re.escape(a if brut else html.escape(a, quote=False))
                    pat = pat.replace(r"\ ", "[ \u00a0]+").replace(r"\(", "[({]")
                    pat = (r"(?<!\w)" if re.match(r"\w", a) else "") + pat + (r"(?!\w)" if re.search(r"\w$", a) else "")
                    inner, k = re.subn(pat, (b if brut else html.escape(b, quote=False)).replace("\\", r"\\"), inner)
                    trouve[a] += k
                return m.group(1) + corriger_note(inner, compte) + "</p>"
            s = re.sub(r'(<p class="note"[^>]*>)(.*?)</p>', note, s, flags=re.S)
            data = s.encode("utf-8")
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    print("Notes : %d ; guillemets rétablis : %d ; règles générales : %d ; corrections particulières : %d"
          % (notes, compte["guillemets"], compte["règles"], sum(trouve.values())))
    absents = [a for a, n in trouve.items() if n == 0]
    if absents:
        print("Non trouvées (déjà corrigées ?) : " + " ; ".join(absents))


if __name__ == "__main__":
    main()
