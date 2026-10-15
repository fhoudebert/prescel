# -*- coding: utf-8 -*-
"""
Faux amis : mots dont la forme a survécu mais dont le sens a changé. Une modernisation qui se contente
de l'orthographe les laisse, et le lecteur comprend de travers (« pucelle », « gentil », « dîner »,
« tôt », « vilain »). Ils sont remplacés par le mot moderne du sens ancien, quand ce sens est sûr chez
les auteurs traités ; les mots qui gardent les deux sens ne sont remplacés que sous condition.

Repérés avec bilingue_lexique.py (colonne « faux ami probable » : remplacement que la traduction en
regard n'emploie presque jamais) et d'après les principes rappelés par les traducteurs du français
médiéval : garder les archaïsmes compréhensibles, écarter les mots dont le sens n'est plus le même
(A. Berrie : preudome, serjant, vallet, disner).

Chargé par dictionnaires/ancien_francais.py (COMMUNS + ANCIEN) et dictionnaires/lisible_froissart.py
(COMMUNS + MOYEN). Clés en minuscules ; locutions permises ; CONTEXTE_* : « forme?condition|… »
(epub_modernise.conditional_choice).
"""

# formes modernisées, communes aux deux époques (après la passe d'orthographe)
COMMUNS = {
    'pucelle': 'jeune fille', 'pucelles': 'jeunes filles',
    'gentil homme': 'gentilhomme', 'gentils hommes': 'gentilshommes', 'gentilz hommes': 'gentilshommes',
    'gentil': 'noble', 'gentils': 'nobles',               # « le gentil comte » : noble
    'dîner': 'déjeuner',                                  # repas du milieu du jour ; le soir : souper
    'dîna': 'déjeuna', 'dînèrent': 'déjeunèrent', 'dîné': 'déjeuné', 'dînaient': 'déjeunaient',
    'dînait': 'déjeunait', 'vilain': 'paysan', 'vilains': 'paysans',
}

# ancien français (graphies d'origine : la passe de vocabulaire les voit avant toute autre)
ANCIEN = {
    'pucele': 'jeune fille', 'puceles': 'jeunes filles',
    'gentil hom': 'gentilhomme', 'gentil home': 'gentilhomme', 'gentiz hom': 'gentilhomme',
    'vaslet': 'jeune homme', 'vallet': 'jeune homme',
    'disner': 'déjeuner', 'al disner': 'au déjeuner',
    'tost': 'vite', 'si tost que': 'aussitôt que', 'tost aprés': 'aussitôt après', 'au plus tost': 'au plus vite',
    'querre': 'chercher', 'querant': 'cherchant',
    'enui': 'chagrin', 'anui': 'chagrin',
    'de chief en chief': "d'un bout à l'autre", 'a chief': 'à bout', 'al chief': 'au bout',
    'el chief': 'au bout', 'chief': 'tête',
    'le chief': 'la tête', 'del chief': 'de la tête', 'mon chief': 'ma tête', 'ton chief': 'ta tête',
    'son chief': 'sa tête', 'lor chief': 'leur tête', 'un chief': 'une tête', 'mal chief': 'mauvaise fin',
    'parlemant': 'entretien',
}

CONTEXTE_ANCIEN = {
    # « avoir mestier » : avoir besoin ; « son mestier » : son métier
    'mestier': 'besoin?prev=a,ot,out,aveit,avoit,avra,avreit,eüst,est,fu,fust,ert,iert,n,i,en,se,grant,ont,ai,as',
    'vilain': 'paysan?prev=le,li,un,uns,au,al,del,du,cil,cel,ce,cest',
    'vaslez': 'jeune homme?prev=li,le,un,uns,cil,ce,cist|jeunes gens',
    'vilains': 'paysans?prev=les,des,as,aux,ces,li,mes,ses',
}

# moyen français (Froissart), sur le texte à l'orthographe déjà modernisée
MOYEN = {}
CONTEXTE_MOYEN = {}
