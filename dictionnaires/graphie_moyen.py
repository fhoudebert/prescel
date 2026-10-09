# -*- coding: utf-8 -*-
"""
Règles d'orthographe du moyen français (XIVᵉ-XVᵉ siècles, Froissart), pour
epub_modernise.py --mode graphie --epoque moyen.

Chaque règle (motif, remplacement) s'applique à la forme écrite en minuscules ; une forme
n'est proposée que si le résultat est un mot de la liste de mots français (--wordlist),
après au plus trois règles enchaînées (« chasteaulx » : aulx → aux, s muet → châteaux).
Les règles marquées sûres donnent une correction appliquée d'office quand une seule forme
moderne est possible (ou une seule déjà présente dans le livre) ; les autres restent au
choix dans la liste TSV. PREFERE tranche les cas fréquents à deux formes (« nostre » :
notre / nôtre) ; « fust », « eust » (fut / fût, eut / eût) restent au choix : le
subjonctif y est fréquent.

Le remplacement None signifie « s muet devant consonne » : la voyelle qui précède prend
l'accent circonflexe, l'accent aigu (e) ou rien (« nostre » → « notre », « fist » →
« fit », « escrire » → « écrire »).
"""

RULES = [
    # (motif, remplacement, sûre ?)
    (r"y$", "i", True),                    # roy, luy, celluy, ay (party : voir epub_modernise)
    (r"ye(s?)$", r"ie\1", True),           # vye, mercye
    (r"ouls$", "oux", True),               # genouls
    (r"y(?=[^aeiouéèê])", "i", True),      # chevaulx… / « ycelle »
    (r"^ung(s?)$", r"un\1", True),
    (r"eu(?:lx|ls|l|x)$", "eux", True),     # euls, eulx, ceulx           # euls, eulx, ceulx
    (r"aulx$", "aux", True), (r"auls$", "aux", True), (r"aus$", "aux", False),
    (r"aul(?=[tsdpmf])", "au", True),      # hault, assault, faulse, daulphin, royaulme, saulf
    (r"oul(?=[tsdc])", "ou", True),        # oultre, doulce, poulsé, doulces
    (r"aul$", "al", False),
    (r"oi(?=(?:s|t|ent)$)", "ai", True),   # imparfaits (complète dictionnaires/verbes_oi.py)
    (r"és$", "ez", True),               # avés, savés ; vouliés → vouliez   # 2ᵉ personne : avés, sachiés
    (r"ié(s?)$", r"é\1", True), (r"iée(s?)$", r"ée\1", True),   # congié, traittié
    (r"ière", "ère", True), (r"ièrent$", "èrent", True),
    (r"ier$", "er", True),                # infinitifs picards : aidier, laissier, logier
    (r"ll", "l", True), (r"tt", "t", True), (r"ff", "f", True), (r"pp", "p", True),
    (r"mm", "m", True), (r"nn", "n", True), (r"ss", "s", False),
    (r"o[iu]?ngn", "ogn", True), (r"aingn", "agn", True), (r"aign", "agn", True),
    (r"oign", "ogn", True), (r"ingn", "ign", False),
    (r"aige(s?)$", r"age\1", True),        # héritaige, avantaige, lignaige
    (r"^dedens$", "dedans", True), (r"ens$", "ans", False),
    (r"ch(?=[eiéèêy])", "c", True),       # picard : merchy, courrouchié, avanchier
    (r"ch(?=on)", "ç", True),             # fachon, raenchon
    (r"ou(?=r)", "o", True), (r"ou(?=[nm])", "o", True),   # honnourable, voulenté
    (r"ou(?=r)", "eu", True),             # demourer → demeurer
    (r"mons", "mon", True),               # monstrer → montrer
    (r"eaue$", "eau", True),
    (r"ége", "ège", True),                 # orthographe de 1871 : siége, Liége, priviléges
    (r"^adv(?=[ie])", "av", True),         # advis, advisé (advenir reste)
    (r"oi(?=[eéè])", "oy", True),          # envoié, moien, soiés
    (r"^deff", "déf", True),               # deffendre, deffense, deffiances
    (r"pv", "v", True), (r"bt", "t", True),   # recepvoir, doubter, soubtil
    (r"pt(?=(?:e|es|s)?$)", "t", True),    # escript, escriptes
    (r"^infour", "infor", True), (r"^sç", "s", True), (r"sç", "ss", False),
    (r"^veoir$", "voir", True), (r"^encoires?$", "encore", True),
    (r"([aeiou])s(?=[bcdfgjklmnpqtv])", None, True),
    (r"^es", "é", True), (r"^es", "ex", False),
]

# Formes jamais touchées par les règles : vrais mots anciens qu'une règle changerait en un autre
# mot moderne (« ens » : dedans ≠ « ans » ; « lés » : près de ≠ « les »).
EXCEPTIONS = set("""
ens es ès lés delés mes ses les des est sus jus cil cel celle ains or ores si se moult
mie point oncques jà ja ne ny ni nul nulle tel telle quel quelle maint mainte
py guy oy
lache laches musle despendu despendre despendi volle vens celier estable sourt escrus
""".split())

# Cas à deux formes modernes tranchés d'avance (sens le plus fréquent chez Froissart)
PREFERE = {"sachiés": "sachez", "soiés": "soyez", "vueilliés": "veuillez", "veulliés": "veuillez",
           "nostre": "notre", "vostre": "votre", "nostres": "nos", "vostres": "vos", "fist": "fit",
           "chevallier": "chevalier", "chancellier": "chancelier", "moittié": "moitié"}
