# -*- coding: utf-8 -*-
"""
Ancien français (fin XIIᵉ - XIIIᵉ siècle : Chrétien de Troyes, Guillaume le Maréchal…) → formes modernes,
pour epub_modernise.py --mode vocab --epoque ancien. But : une lecture plus aisée, pas une traduction :
seuls les mots fréquents dont la forme moderne est sûre sont changés ; le reste demeure.

Les scriptae (dialectes écrits) donnent plusieurs formes du même mot ; on les met côte à côte :
  anglo-normand   ei pour oi (rei, aveir, esteit), u pour o (unques, sunt, dunt), -eals (beals)
  champenois      -aus / -iaus / -ax / -iax (chevaus, chevax, biaus, biax), ia (mialz), an pour en
                  (ansaigne, sanblant), cist / cil, jel, nel, ot / orent
  picard          jou, chou, cou (je, ce), -ch- pour -c- (franchois), -iu (liu, Diu)
Les mots des règles régulières (« aveit » → « avait », « parlérent » → « parlèrent ») relèvent de
dictionnaires/graphie_ancien.py (--mode graphie --epoque ancien) ; ceux du cas sujet (« li cuens »
→ « le comte ») de --mode cas.

ANCIEN_FRANCAIS : formes sûres (appliquées d'office, sauf si la forme est aussi un mot moderne).
FORCE : formes qui sont aussi un mot moderne (« out », « as ») mais presque toujours ce sens-ci.
CONTEXTE : deux formes modernes, choisies d'après les mots voisins (epub_modernise.choose_in_context) :
  « ja » : « jamais » près d'une négation (« ne ja », « ja ne »), sinon « déjà » ;
  « molt », « mout », « mult » : « beaucoup » devant un déterminant, un pronom ou une préposition
  (« aime molt son chevalier »), sinon « très » (« molt bons ») ;
  « cil » : « celui » devant « qui », « que », « dont » ; sinon laissé (« cil » sujet pluriel = « ceux »,
  ou pronom « il ») ;
  « grant », « granz » : grand / grande(s) selon le nom qui suit (comme en moyen français).
Base : formes les plus fréquentes des tomes I et II de Guillaume le Maréchal (éd. Meyer), compléments
champenois et picards, tableau du cas sujet de la branche modernisation (pièce jointe « modernisation »).
"""

ANCIEN_FRANCAIS = {
    'seignor': 'seigneur', 'seignors': 'seigneurs', 'seignur': 'seigneur', 'seignurs': 'seigneurs',
    'consoil': 'conseil', 'anemi': 'ennemi', 'anemis': 'ennemis', 'vencu': 'vaincu',
    'iauz': 'yeux', 'iax': 'yeux', 'iaus': 'eux',
    # pronoms, articles contractés, conjonctions
    'e': 'et', 'ge': 'je', 'jo': 'je', 'jeo': 'je', 'jou': 'je', 'mei': 'moi', 'tei': 'toi', 'sei': 'soi',
    'lor': 'leur', 'lur': 'leur', 'lors': 'alors', 'quer': 'car', 'kar': 'car', 'ker': 'car', 'quar': 'car',
    'del': 'du', 'dou': 'du', 'ço': 'ce', 'çoe': 'ce', 'ceo': 'ce', 'chou': 'ce', 'cou': 'ce',
    'cele': 'celle', 'celes': 'celles', 'cels': 'ceux', 'ceus': 'ceux', 'cez': 'ces', 'els': 'eux',     'cui': 'qui', 'kui': 'qui', 'quei': 'quoi', 'ke': 'que', 'k': 'qu', 'dunt': 'dont',
    'tuit': 'tous', 'toz': 'tous', 'tote': 'toute', 'totes': 'toutes', 'tot': 'tout', 'trestuit': 'tous',
    'trestot': 'tout', 'trestoz': 'tous', 'nule': 'nulle', 'nus': 'nul', 'chascun': 'chacun', 'chascuns': 'chacun',
    'chascune': 'chacune', 'plusors': 'plusieurs', 'plusor': 'plusieurs', 'icil': 'celui',
    'icele': 'celle', 'icelui': 'celui', 'itel': 'tel', 'itant': 'tant', 'autresi': 'aussi',
    # adverbes, prépositions
    'unques': 'jamais', 'onques': 'jamais', 'unkes': 'jamais', 'onc': 'jamais', 'unc': 'jamais',
    'mès': 'mais', 'meis': 'mais', 'issi': 'ainsi', 'isi': 'ainsi', 'esi': 'ainsi', 'eissi': 'ainsi', 'ensi': 'ainsi',
    'asez': 'assez', 'mielz': 'mieux', 'mialz': 'mieux', 'mieuz': 'mieux', 'meins': 'moins',     'tantost': 'aussitôt', 'sor': 'sur', 'sus': 'sur', 'soz': 'sous', 'desoz': 'dessous', 'desor': 'dessus',
    'enz': 'dedans', 'od': 'avec', 'avoec': 'avec', 'ovec': 'avec', 'entor': 'autour',
    'anceis': 'auparavant', 'ainçois': 'auparavant', 'adonc': 'alors', 'idonc': 'alors', 'idonques': 'alors',
    'longement': 'longtemps', 'laienz': 'là-dedans', 'leenz': 'là-dedans', 'ileuc': 'là', 'iluec': 'là',
    'iloc': 'là', 'iloec': 'là', 'tost': 'tôt', 'trés': 'très', 'por': 'pour', 'pur': 'pour', 'porquoi': 'pourquoi',
    'puet': 'peut', 'pues': 'peux',     # être, avoir, faire, et quelques verbes fréquents
    'ert': 'était', 'érent': 'étaient', 'erent': 'étaient', 'esteit': 'était', 'esteient': 'étaient',
    'estoit': 'était', 'estoient': 'étaient', 'aveit': 'avait', 'aveient': 'avaient', 'avoit': 'avait',
    'avoient': 'avaient', 'aveir': 'avoir', 'saveir': 'savoir', 'poeir': 'pouvoir', 'voleir': 'vouloir',
    'veeir': 'voir', 'seit': 'soit', 'seient': 'soient', 'deit': 'doit', 'estre': 'être', 'estes': 'êtes',
    'ourent': 'eurent', 'orent': 'eurent', 'fist': 'fit', 'fet': 'fait', 'feire': 'faire', 'fere': 'faire',
    'distrent': 'dirent', 'pristrent': 'prirent', 'mistrent': 'mirent', 'vindrent': 'vinrent',
    'pout': 'put', 'porent': 'purent', 'sout': 'sut', 'sorent': 'surent', 'volt': 'voulut', 'vout': 'voulut',
    'fust': 'fût', 'eüst': 'eût', 'peüst': 'pût', 'deüst': 'dût', 'feïst': 'fît', 'oï': 'ouï', 'oïr': 'ouïr',
    'estut': 'fallut', 'estuet': 'faut', 'velt': 'veut', 'vuet': 'veut', 'voil': 'veux', 'vueil': 'veux',
    'sai': 'sais', 'sunt': 'sont', 'unt': 'ont', 'avint': 'advint', 'oiez': 'oyez', 'saciez': 'sachez',
    'sachiez': 'sachez', 'metre': 'mettre', 'querre': 'quérir', 'atendre': 'attendre', 'dona': 'donna',
    # noms et adjectifs très fréquents (formes du cas régime et formes sans cas)
    'rei': 'roi', 'reïne': 'reine', 'fei': 'foi', 'lei': 'loi', 'dreit': 'droit',
    'dreiz': 'droit', 'treis': 'trois', 'veie': 'voie', 'jor': 'jour', 'jors': 'jours', 'tens': 'temps',
    'enor': 'honneur', 'onor': 'honneur', 'cort': 'cour', 'poi': 'peu', 'genz': 'gens', 'boen': 'bon',
    'buen': 'bon', 'bone': 'bonne', 'bele': 'belle', 'beal': 'beau', 'bel': 'beau', 'biaus': 'beaux',
    'biax': 'beaux', 'beals': 'beaux', 'malveis': 'mauvais', 'mauvés': 'mauvais', 'halt': 'haut',
    'chival': 'cheval', 'chivalier': 'chevalier', 'chivaliers': 'chevaliers', 'chevaus': 'chevaux',
    'chevax': 'chevaux', 'chevals': 'chevaux', 'chastel': 'château', 'chastiaus': 'châteaux',
    'chastels': 'châteaux', 'oisiaus': 'oiseaux', 'oisel': 'oiseau', 'iex': 'yeux', 'ialz': 'yeux',
    'cuer': 'cœur', 'cors': 'corps', 'liu': 'lieu', 'leu': 'lieu', 'teste': 'tête', 'pére': 'père',
    'frére': 'frère', 'mére': 'mère', 'enfanz': 'enfants', 'anz': 'ans', 'filz': 'fils', 'ost': 'armée',
    'proz': 'preux', 'proece': 'prouesse', 'proesce': 'prouesse', 'corteis': 'courtois', 'cortois': 'courtois',
    'franceis': 'français', 'engleis': 'anglais', 'noveles': 'nouvelles', 'novele': 'nouvelle',
    'congié': 'congé', 'traïson': 'trahison', 'dolor': 'douleur', 'achaison': 'occasion', 'ochaison': 'occasion',
    'ovre': 'œuvre', 'uevre': 'œuvre', 'afaire': 'affaire', 'giemble': 'jeune',
    'juene': 'jeune', 'seint': 'saint', 'seinte': 'sainte', 'ariére': 'arrière',
    'maniére': 'manière', 'damoisele': 'demoiselle', 'pucele': 'pucelle',
    'Dex': 'Dieu', 'Deu': 'Dieu', 'Diu': 'Dieu', 'Damedeu': 'Dieu', 'Damnedeu': 'Dieu',
    'Engletere': 'Angleterre', 'Engleterre': 'Angleterre', 'Bretaigne': 'Bretagne', 'Normendie': 'Normandie',
    # cas sujet sans ambiguïté (le cas régime moderne est donné ; voir aussi --mode cas)
    'cuens': 'comte', 'quens': 'comte', 'ber': 'baron', 'hom': 'homme', 'enfes': 'enfant',
    'compains': 'compagnon', 'traïtres': 'traître', 'pastres': 'pasteur', 'lerres': 'larron',
    'empereres': 'empereur', 'sires': 'seigneur', 'niés': 'neveu',
}

# Champenois (Chrétien de Troyes, copie de Guiot : BnF fr. 794) : formes fréquentes relevées sur le
# Chevalier de la charrette avec bilingue_lexique.py et contrôlées sur une traduction en regard (an pour
# en, -mant pour -ment, ei pour ai, oi pour ei, ot / fu, ele, sui, vialt, voel…). Seuls les mots ; les
# graphies régulières (-mant → -ment) sont aussi dans dictionnaires/graphie_ancien.py.
ANCIEN_FRANCAIS.update({
    'ele': 'elle', 'eles': 'elles', 'sui': 'suis', 'nel': 'ne le', 'jel': 'je le', 'celi': 'celle', 'tex': 'tels',
    'quex': 'quels', 'quele': 'quelle', 'queles': 'quelles', 'moie': 'mienne', 'soe': 'sienne', 'suens': 'siens',
    'suen': 'sien', "quanqu'": "tout ce qu'", 'quanque': 'tout ce que', 'orandroit': 'maintenant', 'orendroit': 'maintenant',
    'atant': 'alors', 'ez vos': 'voici', 'atant ez vos': 'alors voici', 'comant': 'comment', 'aprés': 'après',
    'pres': 'près', 'prez': 'près', 'delez': 'auprès de', 'de lez': 'à côté de', 'ansanble': 'ensemble',
    'ensanble': 'ensemble', 'asanble': 'ensemble', 'dedanz': 'dedans', 'defors': 'dehors', 'desus': 'dessus',
    'ceanz': 'ici', 'leanz': 'là-dedans', 'antor': 'autour', 'anviron': 'environ', 'enmi': 'au milieu de',
    'loing': 'loin', 'arriers': 'arrière', 'arriere': 'arrière', 'adés': 'toujours', 'jamés': 'jamais', 'ancor': 'encore',
    'encor': 'encore', 'ancore': 'encore', 'donques': 'donc', 'neporquant': 'pourtant', 'totevoie': 'toutefois',
    'ausi': 'aussi', 'un po': 'un peu', 'po': 'peu', 'eneslepas': 'aussitôt', 'isnelemant': 'rapidement',
    'lués': 'aussitôt', 'derechief': 'de nouveau', 'aillors': 'ailleurs', 'enuit': 'cette nuit', 'sanz': 'sans',
    'neïs': 'même', 'trestote': 'toute', 'trestotes': 'toutes', 'ainz que': 'avant que', 'einz que': 'avant que',
    'ençois que': 'avant que', 'einçois que': 'avant que', 'ainçois que': 'avant que', 'maugré': 'malgré',
    'premieremant': 'premièrement', 'longuemant': 'longuement', 'autremant': 'autrement', 'seulemant': 'seulement',
    'duremant': 'durement', 'certainnemant': 'certainement', 'seüremant': 'sûrement', 'léaumant': 'loyalement',
    'vilmant': 'vilement', 'laidemant': 'laidement', 'lieemant': 'joyeusement', 'delivremant': 'librement',
    'ot': 'eut', 'fu': 'fut', 'somes': 'sommes', 'sevent': 'savent', 'vialt': 'veut', 'viaut': 'veut', 'vialz': 'veux',
    'voel': 'veux', 'vuel': 'veux', 'uel': 'veux', 'volsist': 'voulût', 'voldroie': 'voudrais', 'voldroit': 'voudrait',
    'voldrai': 'voudrai', 'voldront': 'voudront', 'valt': 'vaut', 'valdroit': 'vaudrait', 'vost': 'voulut',
    'pueent': 'peuvent', 'poez': 'pouvez', 'pooit': 'pouvait', 'porroit': 'pourrait', 'porroie': 'pourrais',
    'porrai': 'pourrai', 'porras': 'pourras', 'porroiz': 'pourrez', 'respont': 'répond', 'dient': 'disent',
    'die': 'dise', 'di': 'dis', 'plest': 'plaît', 'pleisoit': 'plaisait', 'pleüst': 'plût', 'pleira': 'plaira',
    'mainne': 'mène', 'mainnent': 'mènent', 'manrai': 'mènerai', 'vienent': 'viennent', 'tienent': 'tiennent',
    'tieng': 'tiens', 'taigne': 'tienne', 'prant': 'prend', 'praing': 'prends', 'praigne': 'prenne', 'prandre': 'prendre',
    'randre': 'rendre', 'rant': 'rend', 'randrai': 'rendrai', 'quiert': 'cherche', 'quier': 'cherche', 'trueve': 'trouve',
    'truevent': 'trouvent', 'truis': 'trouve', 'truisse': 'trouve', 'trova': 'trouva', 'trové': 'trouvé',
    'trover': 'trouver', 'trovez': 'trouvez', 'vet': 'va', 'alast': 'allât', 'aler': 'aller',
    'veez': 'voyez', 'voi': 'vois', 'croi': 'crois', 'pri': 'prie', 'doi': 'dois', 'doie': 'doive', 'doint': 'donne',
    'gart': 'garde', 'aïst': 'aide', 'aït': 'aide', 'het': 'hait', 'ainme': 'aime', 'covient': 'convient',
    'covint': 'convint', 'fiert': 'frappe', 'fierent': 'frappent', 'chiet': 'tombe', 'cheoir': 'tomber',
    'cheü': 'tombé', 'cheüz': 'tombés', 'gist': 'gît', 'remaint': 'reste', 'remenoir': 'rester', 'remés': 'resté',
    'demore': 'demeure', 'sejorne': 'séjourne', 'otroie': 'accorde', 'otroit': 'accorde', 'comande': 'commande',
    'comandé': 'commandé', 'comanda': 'commanda', 'comandez': 'commandez', 'comança': 'commença', 'comance': 'commence',
    'done': 'donne', 'doné': 'donné', 'donast': 'donnât', 'doner': 'donner', 'esgarde': 'regarde', 'esgarder': 'regarder',
    'apele': 'appelle', 'conut': 'connut', 'conoisse': 'connaisse', 'treire': 'tirer', 'treite': 'tirée',
    'ocirre': 'tuer', 'conbatre': 'combattre', 'desfandre': 'défendre', 'morir': 'mourir', 'sofrir': 'souffrir',
    'lessiez': 'laissez', 'lessié': 'laissé', 'lesse': 'laisse', 'leisse': 'laisse', 'ist': 'sort', 'mete': 'mette',
    'metent': 'mettent', 'eüsse': 'eusse', 'feïsse': 'fisse', 'feïssent': 'fissent', 'meïst': 'mît', 'meïssent': 'missent',
    'veïst': 'vît', 'venist': 'vînt', 'seüst': 'sût', 'avra': 'aura', 'avrai': 'aurai', 'avroie': 'aurais',
    'avroiz': 'aurez', 'savra': 'saura', 'savroiz': 'saurez', 'verroiz': 'verrez', 'seroiz': 'serez', 'feroie': 'ferais',
    'faz': 'fais', 'feisoit': 'faisait', 'feite': 'faite', 'feites': 'faites', 'afeire': 'affaire', 'tindrent': 'tinrent',
    'requerre': 'requérir', 'conquerre': 'conquérir', 'amander': 'amender', 'chacier': 'chasser', 'chacié': 'chassé',
    'retorner': 'retourner', 'retorne': 'retourne', 'torner': 'tourner', 'torne': 'tourne', 'tornent': 'tournent',
    'antrer': 'entrer', 'antrez': 'entrez', 'antendre': 'entendre', 'anvoie': 'envoie', 'atandre': 'attendre',
    'prometre': 'promettre', 'corre': 'courir', 'mantir': 'mentir', 'joer': 'jouer', 'eidier': 'aider', 'herbergier': 'héberger',
    'acorde': 'accorde', 'aproche': 'approche', 'aparçoit': 'aperçoit', 'desarmez': 'désarmés', 'vaincuz': 'vaincus',
    'perduz': 'perdus', 'esperduz': 'éperdus', 'venuz': 'venus', 'mosterrai': 'montrerai', 'desirre': 'désire',
    'mercie': 'remercie', 'toche': 'touche', 'hurte': 'heurte', 'dameisele': 'demoiselle', 'dameiseles': 'demoiselles',
    'tor': 'tour', 'cos': 'coups', 'cop': 'coup', 'servise': 'service', 'piez': 'pieds', 'pié': 'pied',
    'preuz': 'preux', 'seneschal': 'sénéchal', 'seneschax': 'sénéchal', 'réaume': 'royaume', 'chanbre': 'chambre',
    'beles': 'belles', 'boene': 'bonne', 'espee': 'épée', 'espees': 'épées', 'sanc': 'sang', 'monseignor': 'monseigneur',
    'pere': 'père', 'peres': 'pères', 'frere': 'frère', 'pes': 'paix', 'braz': 'bras', 'painne': 'peine',
    'poinne': 'peine', 'conpaignie': 'compagnie', 'conpaignons': 'compagnons', 'orguel': 'orgueil', 'hiaume': 'heaume',
    'hiaumes': 'heaumes', 'amor': 'amour', 'vavasor': 'vavasseur', 'vavasors': 'vavasseurs', 'meillor': 'meilleur',
    'avanture': 'aventure', 'fame': 'femme', 'enors': 'honneurs', 'aleüre': 'allure', 'andeus': 'tous deux',
    'anbedeus': 'tous deux', 'andui': 'tous deux', 'anbedui': 'tous deux', 'peor': 'peur', 'volanté': 'volonté',
    'volenté': 'volonté', 'chevox': 'cheveux', 'letres': 'lettres', 'hardemant': 'hardiesse', 'proiere': 'prière',
    'torz': 'torts', 'pree': 'prairie', 'malvés': 'mauvais', 'mantel': 'manteau', 'meniere': 'manière', 'mervoille': 'merveille',
    'mervoilles': 'merveilles', 'meslee': 'mêlée', 'anel': 'anneau', 'felenie': 'félonie', 'frain': 'frein',
    'forfet': 'forfait', 'mesfet': 'méfait', 'contree': 'contrée', 'justise': 'justice', 'escuier': 'écuyer',
    'escuz': 'écus', 'aïe': 'aide', 'mançonge': 'mensonge', 'pechié': 'péché', 'sairemant': 'serment', 'nuiz': 'nuits',
    'jeus': 'jeux', 'diax': 'deuil', 'haubers': 'hauberts', 'color': 'couleur', 'mesprison': 'faute', 'tonbes': 'tombes',
    'dolçor': 'douceur', 'retor': 'retour', 'haïne': 'haine', 'bontez': 'bontés', 'joiant': 'joyeux', 'païs': 'pays',
    'foiz': 'fois', 'voz': 'vos', 'noz': 'nos', 'reison': 'raison', 'eise': 'aise', 'chanp': 'champ', 'desdaing': 'dédain',
    'corteisie': 'courtoisie', 'essil': 'exil', 'perilleus': 'périlleux', 'enprise': 'entreprise', 'presant': 'présent',
    'cinc': 'cinq', 'pleisir': 'plaisir', 'chace': 'chasse', 'orguelleus': 'orgueilleux', 'tranchanz': 'tranchants',
    'hardiz': 'hardis', 'dolante': 'affligée', 'leisir': 'loisir', 'destre': 'droite', 'senestre': 'gauche',
    'veüe': 'vue', 'veü': 'vu', 'covant': 'engagement', 'guerredon': 'salaire', 'covertor': 'couvre-lit',
    'delez le': 'auprès du', 'delez les': 'auprès des', 'enmi le': 'au milieu du', 'enmi les': 'au milieu des',
    'delez lui': 'auprès de lui', 'delez li': "auprès d'elle",
})

FORCE = {
    'estes vos': 'voici', 'es vos': 'voici',   # « Estes vos le conte » : voici le comte
    'out': 'eut', 'as': 'aux', 'al': 'au', 'reis': 'roi', 'nient': 'rien', 'com': 'comme',
    'cum': 'comme', 'come': 'comme', 'om': 'on', 'l\'om': 'l\'on', 'onques': 'jamais', 'oncques': 'jamais',
    'li dui': 'les deux', 'li trei': 'les trois', 'li troi': 'les trois', 'li plusor': 'la plupart',
    'li plosor': 'la plupart', 'li plusors': 'la plupart', 'dui': 'deux', 'trei': 'trois', 'troi': 'trois',
    's\'an': 's\'en', 'n\'an': 'n\'en', 'Mareschals': 'Maréchal', 'mareschals': 'maréchal',
}

CONTEXTE = {
    'ja': 'déjà|jamais',
    'molt': 'très|beaucoup', 'mout': 'très|beaucoup', 'mult': 'très|beaucoup', 'moult': 'très|beaucoup',
    'cil': 'celui|cil',
    'grant': 'grand|grande',
    'quant': 'quand|quant',
    'mes': 'mais|mes',
    'mie': 'pas|mie',                       # « la mie del pain » : la mie
    'jorz': 'jour|jours', 'jors': 'jour|jours',                      # « mes il » : mais ; « mes chevaus » : mes
    # cas sujet singulier ou cas régime pluriel (« li chevaus » / « les chevaus ») : pluriel après
    # « les », « ses », « des »… ou devant un nom au pluriel, singulier sinon ; « li chevaus »,
    # « li biax chevaliers » sont déjà traités par --mode cas
    'biaus': 'beau|beaux', 'biax': 'beau|beaux', 'biaux': 'beau|beaux', 'beals': 'beau|beaux',
    'chevaus': 'cheval|chevaux', 'chevax': 'cheval|chevaux', 'chevals': 'cheval|chevaux',
    'oisiaus': 'oiseau|oiseaux', 'chastiaus': 'château|châteaux', 'chastels': 'château|châteaux',
    'boens': 'bon|bons', 'buens': 'bon|bons', 'granz': 'grand|grands',
    # champenois : formes à double sens, remplacées seulement quand le contexte tranche (« forme?condition »,
    # voir epub_modernise.conditional_choice) ; sinon gardées
    'aus': 'eux?prev=avoec,avuec,avec,a,à,de,por,pour,sor,sur,entre,o,contre,vers,devant,par,d,qu,que,fors',
    'ainz': 'mais?neg', 'einz': 'mais?neg', 'ençois': 'mais?neg', 'einçois': 'mais?neg', 'ainçois': 'mais?neg',
    'tret': 'tiré?aux|tire',
    'eve': "eau?prev=l,la,d,de,une,en,par,a,à,cele,grant,parfonde,bele,lor,sor,sus",   # « Eve » : le prénom reste
    'alez': 'allé?aux|allez',               # « s'en est alez » : allé ; « alez vos an » : allez
    'preu': 'profit?prev=mon,ton,son,vostre,nostre,lor,vos,nos,votre,notre,leur|preux',
}

# Mots remplacés par leur sens moderne (le mot ancien n'existe plus ou a changé de sens), pour une
# lisibilité accrue : appliqués d'office par --mode vocab, sauf quand la forme ancienne est aussi un mot
# moderne (« faix », « lais », « lobe », « desserte », « fournier ») : alors au choix dans la liste.
# Les verbes sont donnés aux formes rencontrées dans les textes (anglo-normand et francien).
LEXIQUE = {
    # chevance : richesse ; bachelerie : jeunesse ; arroi : ordre ; coulpe : faute
    'chevance': 'richesse', 'chevances': 'richesses', 'chevaunce': 'richesse',
    'bachelerie': 'jeunesse', 'bachellerie': 'jeunesse', 'bacheleries': 'jeunesses',
    'arroi': 'ordre', 'arroy': 'ordre', 'arrois': 'ordres', 'arroiz': 'ordres',
    'coulpe': 'faute', 'coulpes': 'fautes', 'colpe': 'faute', 'colpes': 'fautes', 'culpe': 'faute',
    # cuidier : penser
    'cuidier': 'penser', 'cuider': 'penser', 'quidier': 'penser', 'quider': 'penser',
    'cuit': 'pense', 'cuid': 'pense', 'quid': 'pense', 'cuide': 'pense', 'quide': 'pense',
    'cuides': 'penses', 'cuidons': 'pensons', 'quidons': 'pensons', 'cuidiez': 'pensez', 'quidiez': 'pensez',
    'cuident': 'pensent', 'quident': 'pensent',
    'cuidoie': 'pensais', 'quidoie': 'pensais', 'cuidoe': 'pensais', 'quidoe': 'pensais',
    'cuidout': 'pensait', 'quidout': 'pensait', 'cuidot': 'pensait', 'cuidoit': 'pensait',
    'quidoit': 'pensait', 'cuideit': 'pensait', 'quideit': 'pensait',
    'cuidoent': 'pensaient', 'quidoent': 'pensaient', 'cuidoient': 'pensaient', 'cuideient': 'pensaient',
    'cuida': 'pensa', 'quida': 'pensa', 'cuidai': 'pensai', 'quidai': 'pensai',
    'cuidérent': 'pensèrent', 'quidérent': 'pensèrent', 'cuidierent': 'pensèrent', 'cuidièrent': 'pensèrent',
    'cuidast': 'pensât', 'quidast': 'pensât', 'cuidasse': 'pensasse', 'cuidassent': 'pensassent',
    'cuidié': 'pensé', 'cuidé': 'pensé', 'quidié': 'pensé',
    'cuidereie': 'penserais', 'quidereie': 'penserais', 'quiderraie': 'penserais', 'cuidereit': 'penserait',
    'quidereit': 'penserait',
    # faix : poids ; gaite : sentinelle
    'faix': 'poids', 'gaite': 'sentinelle', 'gaites': 'sentinelles', 'guaite': 'sentinelle',
    'gaitent': 'veillent',
    # issir : sortir (pas « issi », « eissi », qui sont surtout « ainsi » en anglo-normand)
    'issir': 'sortir', 'eissir': 'sortir', 'oissir': 'sortir', 'issirent': 'sortirent', 'eissirent': 'sortirent',
    'issent': 'sortent', 'eissent': 'sortent', 'isseit': 'sortait', 'issoit': 'sortait', 'issoient': 'sortaient',
    'eissist': 'sortît', 'issist': 'sortît', 'eissu': 'sorti', 'eissue': 'sortie', 'eissuz': 'sortis',
    # lais : testament ; lobe : raillerie ; maisnie : suite
    'lais': 'testament', 'lobe': 'raillerie', 'lobes': 'railleries', 'lober': 'railler',
    'maisnie': 'suite', 'maisniee': 'suite', 'maisniée': 'suite', 'mesnie': 'suite', 'maisnies': 'suites',
    'mesnies': 'suites', 'mainie': 'suite',
    # menoison : dysenterie ; meschief : malheur
    'menoison': 'dysenterie', 'menison': 'dysenterie',
    'meschief': 'malheur', 'meschiefs': 'malheurs', 'meschiés': 'malheurs', 'mescheance': 'malheur',
    'meschaance': 'malheur',
    # navier : naviguer ; mesiaus : lépreux ; eschamel : escabeau
    'navier': 'naviguer', 'navia': 'navigua', 'navierent': 'naviguèrent', 'naviérent': 'naviguèrent',
    'mesiaus': 'lépreux', 'mesiax': 'lépreux', 'meseaus': 'lépreux', 'mesel': 'lépreux', 'mesels': 'lépreux',
    'mezel': 'lépreux', 'mezels': 'lépreux', 'mesele': 'lépreuse',
    'eschamel': 'escabeau', 'eschamels': 'escabeaux', 'eschamiaus': 'escabeaux', 'eschamaus': 'escabeaux',
    # chaloir : se soucier (impersonnel « ne li chaut » : ne lui importe)
    'chaloir': 'se soucier', 'chaleir': 'se soucier', 'chaut': 'importe', 'chalt': 'importe',
    'chaleit': 'importait', 'chaloit': 'importait', 'challoit': 'importait', 'chalut': 'importa',
    'chausist': 'importât', 'chalsist': 'importât',
    # barguignier : marchander ; assemer : parer ; aticier : exciter
    'barguignier': 'marchander', 'barguigner': 'marchander', 'barguigna': 'marchanda',
    'barguignent': 'marchandent', 'barguignoit': 'marchandait',
    'assemer': 'parer', 'assemé': 'paré', 'assemée': 'parée', 'assemez': 'parés', 'assemés': 'parés',
    'atticier': 'exciter', 'aticier': 'exciter', 'atisier': 'exciter', 'atiça': 'excita', 'aticié': 'excité',
    'aticiez': 'excités', 'atice': 'excite',
    # berrie : plaine ; costement : coût ; corine : haine
    'berrie': 'plaine', 'berries': 'plaines',
    'costement': 'coût', 'costemens': 'coûts', 'costemenz': 'coûts', 'coustement': 'coût',
    'corine': 'haine', 'courine': 'haine', 'curine': 'haine',
    # créanter : promettre ; darrains : derniers ; desserte : mérite
    'creanter': 'promettre', 'créanter': 'promettre', 'creantier': 'promettre', 'creanta': 'promit',
    'créanta': 'promit', 'creanterent': 'promirent', 'creantérent': 'promirent', 'creante': 'promet', 'creantent': 'promettent', 'creanté': 'promis', 'créanté': 'promis', 'creantez': 'promis',
    'darrain': 'dernier', 'darrains': 'derniers', 'darraine': 'dernière', 'derrain': 'dernier',
    'derrains': 'derniers', 'derraine': 'dernière', 'darreniers': 'derniers',
    'desserte': 'mérite', 'dessertes': 'mérites',
    # desvé : enragé ; eshidé : épouvanté ; estorer : fonder ; estoirer : approvisionner
    'desvé': 'enragé', 'desvez': 'enragés', 'desvée': 'enragée', 'desvés': 'enragés', 'dervé': 'enragé',
    'eshidé': 'épouvanté', 'eshidez': 'épouvantés', 'eshidée': 'épouvantée', 'eshidés': 'épouvantés',
    'estorer': 'fonder', 'estora': 'fonda', 'estoré': 'fondé', 'estorée': 'fondée',
    'estoirer': 'approvisionner', 'estoiré': 'approvisionné', 'estoirée': 'approvisionnée',
    'estoirez': 'approvisionnés',
    # fournier : boulanger ; mezelerie : lèpre ; oirre : voyage ; pec : émotion
    'fournier': 'boulanger', 'forniers': 'boulangers', 'fornier': 'boulanger',
    'mezelerie': 'lèpre', 'meselerie': 'lèpre', 'mesellerie': 'lèpre',
    'oirre': 'voyage', 'oirres': 'voyages',
    'pec': 'émotion',
    # pooir : pouvoir ; remanant : reste ; relenquir : abandonner
    'pooir': 'pouvoir', 'pooirs': 'pouvoirs',
    'remanant': 'reste', 'remenant': 'reste', 'remanans': 'restes',
    'relenquir': 'abandonner', 'relinquir': 'abandonner', 'relenqui': 'abandonna', 'relenquist': 'abandonna',
    'relenquie': 'abandonnée', 'relinqui': 'abandonna',
}

# Mots dont le sens a changé : jamais appliqués à une lecture modernisée (version reformulée seulement)
VERSION_MODERNE = {
    'nonchaleir': 'insouciance',
    'mesestance': 'malheur', 'ainz': 'mais, plutôt', 'einz': 'mais, plutôt', 'fors': 'hors, sauf',
    'or': 'maintenant', 'si': 'ainsi, et', 'cist': 'ce, celui-ci', 'cest': 'ce, cet',
}

# Cas sujet : nom (forme du cas sujet singulier) → forme moderne, pour --mode cas ; le tableau
# régulier (« li chevaliers » → « le chevalier ») est calculé : -s / -z ôté si le reste est un mot moderne.
CAS_SUJET = { "sires": "seigneur", "jorz": "jour", "jors": "jour", "chevax": "cheval", "chevaux": "cheval",
    "cors": "corps", "proz": "preux", "pros": "preux", "mielz": "mieux", "mialz": "mieux",
    'cuens': 'comte', 'quens': 'comte', 'reis': 'roi', 'rois': 'roi', 'sire': 'seigneur', 'ber': 'baron',
    'hom': 'homme', 'enfes': 'enfant', 'compains': 'compagnon', 'traïtres': 'traître', 'pastres': 'pasteur',
    'lerres': 'larron', 'empereres': 'empereur', 'niés': 'neveu', 'filz': 'fils', 'fiz': 'fils',
    'Mareschals': 'Maréchal', 'mareschals': 'maréchal', 'chevals': 'cheval', 'chevaus': 'cheval',
    'oisiaus': 'oiseau', 'biaus': 'beau', 'biax': 'beau', 'beals': 'beau', 'boens': 'bon', 'buens': 'bon',
    'bons': 'bon', 'granz': 'grand', 'genz': 'gent', 'anemis': 'ennemi', 'amis': 'ami',
}


# Faux amis (dictionnaires/faux_amis.py) : « pucele » → jeune fille, « tost » → vite, « gentil » → noble…
# Ajoutés à FORCE (appliqués même quand la forme existe en français moderne) et à CONTEXTE.
def _faux_amis():
    import os
    import runpy
    fa = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "faux_amis.py"))
    sure = dict(fa["COMMUNS"], **fa["ANCIEN"])
    return {k: v for k, v in sure.items() if k not in fa["CONTEXTE_ANCIEN"]}, fa["CONTEXTE_ANCIEN"]


_fa_force, _fa_contexte = _faux_amis()
FORCE.update(_fa_force)
CONTEXTE.update(_fa_contexte)
