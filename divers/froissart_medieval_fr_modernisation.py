"""Première base de modernisation du français médiéval (XIVe siècle), orientée Froissart.

Les formes SAFE sont des substitutions lexicales/orthographiques prudentes.
CONTEXT contient les formes ambiguës : elles ne doivent pas être remplacées sans analyse.
"""

SAFE = {}

# graphies

SAFE['anglois'] = 'anglais'
SAFE['angloise'] = 'anglaise'
SAFE['arcevesque'] = 'archevêque'
SAFE['armee'] = 'armée'
SAFE['beaulte'] = 'beauté'
SAFE['beauté'] = 'beauté'
SAFE['bourgois'] = 'bourgeois'
SAFE['bretaigne'] = 'Bretagne'
SAFE['castel'] = 'château'
SAFE['castelz'] = 'châteaux'
SAFE['chapelain'] = 'chapelain'
SAFE['chastel'] = 'château'
SAFE['chastelain'] = 'châtelain'
SAFE['chastelaine'] = 'châtelaine'
SAFE['chastels'] = 'châteaux'
SAFE['chastiau'] = 'château'
SAFE['chastiaus'] = 'châteaux'
SAFE['chevauchie'] = 'chevauchée'
SAFE['chevaulx'] = 'chevaux'
SAFE['chevaus'] = 'chevaux'
SAFE['compagnon'] = 'compagnon'
SAFE['compaignie'] = 'compagnie'
SAFE['compaignies'] = 'compagnies'
SAFE['compaignon'] = 'compagnon'
SAFE['compaignons'] = 'compagnons'
SAFE['conqueste'] = 'conquête'
SAFE['conquestes'] = 'conquêtes'
SAFE['defaite'] = 'défaite'
SAFE['escos'] = 'écossais'
SAFE['escoçois'] = 'écossais'
SAFE['escu'] = 'écu'
SAFE['escus'] = 'écus'
SAFE['escut'] = 'écu'
SAFE['escuz'] = 'écus'
SAFE['espee'] = 'épée'
SAFE['espees'] = 'épées'
SAFE['espée'] = 'épée'
SAFE['eveschié'] = 'évêché'
SAFE['evesque'] = 'évêque'
SAFE['evesques'] = 'évêques'
SAFE['faubourg'] = 'faubourg'
SAFE['faubourgs'] = 'faubourgs'
SAFE['feal'] = 'féal'
SAFE['feaus'] = 'féaux'
SAFE['fontaine'] = 'fontaine'
SAFE['forest'] = 'forêt'
SAFE['forestz'] = 'forêts'
SAFE['foy'] = 'foi'
SAFE['foys'] = 'fois'
SAFE['francois'] = 'français'
SAFE['francoise'] = 'française'
SAFE['françois'] = 'français'
SAFE['françoise'] = 'française'
SAFE['hostel'] = 'hôtel'
SAFE['hostels'] = 'hôtels'
SAFE['loial'] = 'loyal'
SAFE['loiaul'] = 'loyal'
SAFE['loy'] = 'loi'
SAFE['loys'] = 'lois'
SAFE['marchans'] = 'marchands'
SAFE['marchant'] = 'marchand'
SAFE['meson'] = 'maison'
SAFE['mesons'] = 'maisons'
SAFE['mestier'] = 'métier'
SAFE['mestiers'] = 'métiers'
SAFE['montaigne'] = 'montagne'
SAFE['montaignes'] = 'montagnes'
SAFE['moustier'] = 'monastère'
SAFE['moustiers'] = 'monastères'
SAFE['ostel'] = 'hôtel'
SAFE['ostels'] = 'hôtels'
SAFE['prestre'] = 'prêtre'
SAFE['prestres'] = 'prêtres'
SAFE['pretre'] = 'prêtre'
SAFE['puiz'] = 'puits'
SAFE['puys'] = 'puits'
SAFE['riviere'] = 'rivière'
SAFE['rivières'] = 'rivières'
SAFE['roial'] = 'royal'
SAFE['roiaul'] = 'royal'
SAFE['roiaume'] = 'royaume'
SAFE['roiaumes'] = 'royaumes'
SAFE['roiaus'] = 'royaux'
SAFE['roy'] = 'roi'
SAFE['roys'] = 'rois'
SAFE['seignor'] = 'seigneur'
SAFE['seignorie'] = 'seigneurie'
SAFE['siege'] = 'siège'
SAFE['traictiez'] = 'traités'
SAFE['traicté'] = 'traité'

# verbes

SAFE['ala'] = 'alla'
SAFE['alerent'] = 'allèrent'
SAFE['aloient'] = 'allaient'
SAFE['aloit'] = 'allait'
SAFE['alèrent'] = 'allèrent'
SAFE['aroient'] = 'auraient'
SAFE['aroit'] = 'aurait'
SAFE['assambla'] = 'assembla'
SAFE['assamblerent'] = 'assemblèrent'
SAFE['auroient'] = 'auraient'
SAFE['aviez'] = 'aviez'
SAFE['avindrent'] = 'advint'
SAFE['avint'] = 'advint'
SAFE['avoient'] = 'avaient'
SAFE['avoit'] = 'avait'
SAFE['combati'] = 'combattit'
SAFE['combattirent'] = 'combattirent'
SAFE['conta'] = 'raconta'
SAFE['conterent'] = 'racontèrent'
SAFE['cria'] = 'cria'
SAFE['crierent'] = 'crièrent'
SAFE['defendi'] = 'défendit'
SAFE['defendirent'] = 'défendirent'
SAFE['demanda'] = 'demanda'
SAFE['demanderent'] = 'demandèrent'
SAFE['demeura'] = 'demeura'
SAFE['demoura'] = 'demeura'
SAFE['demourer'] = 'demeurer'
SAFE['demourerent'] = 'demeurèrent'
SAFE['deuoient'] = 'devaient'
SAFE['deuoit'] = 'devait'
SAFE['devoient'] = 'devaient'
SAFE['devoit'] = 'devait'
SAFE['dirent'] = 'dirent'
SAFE['disoient'] = 'disaient'
SAFE['disoit'] = 'disait'
SAFE['dist'] = 'dit'
SAFE['ensui'] = 'ensuivit'
SAFE['ensuivirent'] = 'ensuivirent'
SAFE['entra'] = 'entra'
SAFE['entrerent'] = 'entrèrent'
SAFE['envoya'] = 'envoya'
SAFE['envoyerent'] = 'envoyèrent'
SAFE['estoi'] = 'étais'
SAFE['estoient'] = 'étaient'
SAFE['estoies'] = 'étais'
SAFE['estoit'] = 'était'
SAFE['faisoient'] = 'faisaient'
SAFE['faisoit'] = 'faisait'
SAFE['ferma'] = 'ferma'
SAFE['fermerent'] = 'fermèrent'
SAFE['feroient'] = 'feraient'
SAFE['feroit'] = 'ferait'
SAFE['fu'] = 'fut'
SAFE['fui'] = 'fus'
SAFE['fuirent'] = 'fuirent'
SAFE['fuist'] = 'fuit'
SAFE['fumes'] = 'fûmes'
SAFE['fus'] = 'fus'
SAFE['fustes'] = 'fûtes'
SAFE['fuy'] = 'fuit'
SAFE['gagna'] = 'gagna'
SAFE['gagnerent'] = 'gagnèrent'
SAFE['habita'] = 'habita'
SAFE['jurerent'] = 'jurèrent'
SAFE['jurra'] = 'jura'
SAFE['laissa'] = 'laissa'
SAFE['laisserent'] = 'laissèrent'
SAFE['manda'] = 'manda'
SAFE['manderent'] = 'mandèrent'
SAFE['mist'] = 'mit'
SAFE['mistrent'] = 'mirent'
SAFE['monstra'] = 'montra'
SAFE['montrerent'] = 'montrèrent'
SAFE['mouroient'] = 'mouraient'
SAFE['mouroit'] = 'mourait'
SAFE['occirent'] = 'occirent'
SAFE['occist'] = 'occit'
SAFE['occupèrent'] = 'occupèrent'
SAFE['ordonna'] = 'ordonna'
SAFE['ordonnerent'] = 'ordonnèrent'
SAFE['orent'] = 'eurent'
SAFE['ot'] = 'eut'
SAFE['ouvri'] = 'ouvrit'
SAFE['ouvrirent'] = 'ouvrirent'
SAFE['parla'] = 'parla'
SAFE['parlerent'] = 'parlèrent'
SAFE['perdi'] = 'perdit'
SAFE['perdirent'] = 'perdirent'
SAFE['pleuroit'] = 'pleurait'
SAFE['ploura'] = 'pleura'
SAFE['plourerent'] = 'pleurèrent'
SAFE['plouroit'] = 'pleurait'
SAFE['pouoient'] = 'pouvaient'
SAFE['pouoit'] = 'pouvait'
SAFE['pourroient'] = 'pourraient'
SAFE['pourroit'] = 'pourrait'
SAFE['poursuivi'] = 'poursuivit'
SAFE['poursuivirent'] = 'poursuivirent'
SAFE['povoient'] = 'pouvaient'
SAFE['povoit'] = 'pouvait'
SAFE['prindrent'] = 'prirent'
SAFE['prist'] = 'prit'
SAFE['promirent'] = 'promirent'
SAFE['promist'] = 'promit'
SAFE['receurent'] = 'reçurent'
SAFE['receut'] = 'reçut'
SAFE['respondi'] = 'répondit'
SAFE['respondirent'] = 'répondirent'
SAFE['respondit'] = 'répondit'
SAFE['retourna'] = 'retourna'
SAFE['retournerent'] = 'retournèrent'
SAFE['rioit'] = 'riait'
SAFE["s'en ala"] = "s'en alla"
SAFE["s'en alerent"] = "s'en allèrent"
SAFE['saroit'] = 'saurait'
SAFE['savoient'] = 'savaient'
SAFE['savoit'] = 'savait'
SAFE['seroient'] = 'seraient'
SAFE['seroit'] = 'serait'
SAFE['suivi'] = 'suivit'
SAFE['suivirent'] = 'suivirent'
SAFE['tenoient'] = 'tenaient'
SAFE['tenoit'] = 'tenait'
SAFE['trouva'] = 'trouva'
SAFE['trouverent'] = 'trouvèrent'
SAFE['tua'] = 'tua'
SAFE['tuerent'] = 'tuèrent'
SAFE['vainqui'] = 'vainquit'
SAFE['vainquirent'] = 'vainquirent'
SAFE['venoient'] = 'venaient'
SAFE['venoit'] = 'venait'
SAFE['verroient'] = 'verraient'
SAFE['verroit'] = 'verrait'
SAFE['vindrent'] = 'vinrent'
SAFE['vint'] = 'vint'
SAFE['vintrent'] = 'vinrent'
SAFE['vouloient'] = 'voulaient'
SAFE['vouloit'] = 'voulait'

# pronoms

SAFE['autel'] = 'tel'
SAFE['autels'] = 'tels'
SAFE['cest'] = 'ce'
SAFE['ceste'] = 'cette'
SAFE['cestes'] = 'ces'
SAFE['cesti'] = 'celui-ci'
SAFE['cestui'] = 'celui-ci'
SAFE['cestuy'] = 'celui-ci'
SAFE['cestuy-ci'] = 'celui-ci'
SAFE['cestuy-là'] = 'celui-là'
SAFE['ceulx'] = 'ceux'
SAFE['ceulz'] = 'ceux'
SAFE['ceus'] = 'ceux'
SAFE['chascun'] = 'chacun'
SAFE['chascune'] = 'chacune'
SAFE['chascunes'] = 'chacune'
SAFE['chascuns'] = 'chacun'
SAFE['icel'] = 'celui-ci'
SAFE['icelle'] = 'celle-ci'
SAFE['icelles'] = 'celles-ci'
SAFE['icels'] = 'ceux-ci'
SAFE['icelui'] = 'celui-ci'
SAFE['iceulx'] = 'ceux-ci'
SAFE['iceus'] = 'ceux-ci'
SAFE['meismes'] = 'mêmes'
SAFE['mesme'] = 'même'
SAFE['mesmes'] = 'mêmes'
SAFE['nulle'] = 'nulle'
SAFE['nulles'] = 'nulles'
SAFE['nulz'] = 'nuls'
SAFE['quans'] = 'combien de'
SAFE['quantes'] = 'combien de'
SAFE['queles'] = 'quelles'
SAFE['quelz'] = 'quels'
SAFE['toutefoiz'] = 'toutefois'
SAFE['toutesfoiz'] = 'toutefois'

# adverbes

SAFE['adonc'] = 'alors'
SAFE['adoncques'] = 'alors'
SAFE['adont'] = 'alors'
SAFE['apres'] = 'après'
SAFE['aprés'] = 'après'
SAFE['cependant'] = 'cependant'
SAFE['dedenz'] = 'dedans'
SAFE['derriere'] = 'derrière'
SAFE['dessoubz'] = 'dessous'
SAFE['devers'] = 'vers'
SAFE['encor'] = 'encore'
SAFE['encores'] = 'encore'
SAFE['ensemblement'] = 'ensemble'
SAFE['ensement'] = 'également'
SAFE['entour'] = 'autour'
SAFE['entrementes'] = 'entre-temps'
SAFE['entremy'] = 'parmi'
SAFE['environ'] = 'autour de'
SAFE['especialement'] = 'spécialement'
SAFE['especialment'] = 'spécialement'
SAFE['finalment'] = 'finalement'
SAFE['ja'] = 'déjà'
SAFE['jusques'] = "jusqu'à"
SAFE['jusques à'] = "jusqu'à"
SAFE['molt'] = 'beaucoup'
SAFE['moult'] = 'beaucoup'
SAFE['mout'] = 'beaucoup'
SAFE['onc'] = 'jamais'
SAFE['oncques'] = 'jamais'
SAFE['ore'] = 'maintenant'
SAFE['orendroit'] = 'à présent'
SAFE['ores'] = 'désormais'
SAFE['parmy'] = 'parmi'
SAFE['pour tant'] = 'pourtant'
SAFE['premierement'] = 'premièrement'
SAFE['selonc'] = 'selon'
SAFE['tantost'] = 'aussitôt'
SAFE['tost'] = 'tôt'
SAFE['volentiers'] = 'volontiers'
SAFE['vraiement'] = 'vraiment'
SAFE['çà'] = 'ici'

# lexique_courant

SAFE['accord'] = 'accord'
SAFE['alliance'] = 'alliance'
SAFE['an'] = 'an'
SAFE['annee'] = 'année'
SAFE['annees'] = 'années'
SAFE['ans'] = 'ans'
SAFE['anuit'] = 'la nuit'
SAFE['arme'] = 'arme'
SAFE['armes'] = 'armes'
SAFE['armure'] = 'armure'
SAFE['assaus'] = 'assauts'
SAFE['assaut'] = 'assaut'
SAFE['bataille'] = 'bataille'
SAFE['biau'] = 'beau'
SAFE['biaus'] = 'beaux'
SAFE['biaute'] = 'beauté'
SAFE['bois'] = 'bois'
SAFE['bouclier'] = 'bouclier'
SAFE['bourg'] = 'bourg'
SAFE['bourgs'] = 'bourgs'
SAFE['chambre'] = 'chambre'
SAFE['chemin'] = 'chemin'
SAFE['cheval'] = 'cheval'
SAFE['compaignon'] = 'compagnon'
SAFE['cour'] = 'cour'
SAFE['cours'] = 'cours'
SAFE['cuirasse'] = 'cuirasse'
SAFE['derniere'] = 'dernière'
SAFE['destrier'] = 'destrier'
SAFE['enfans'] = 'enfants'
SAFE['enfantz'] = 'enfants'
SAFE['escarmouche'] = 'escarmouche'
SAFE['filz'] = 'fils'
SAFE['fiz'] = 'fils'
SAFE['foible'] = 'faible'
SAFE['foibles'] = 'faibles'
SAFE['franc'] = 'franc'
SAFE['frans'] = 'francs'
SAFE['frere'] = 'frère'
SAFE['freres'] = 'frères'
SAFE['grans'] = 'grands'
SAFE['grant'] = 'grand'
SAFE['guerre'] = 'guerre'
SAFE['harnas'] = 'harnais'
SAFE['harnois'] = 'harnais'
SAFE['hauberc'] = 'haubert'
SAFE['havre'] = 'havre'
SAFE['heaume'] = 'heaume'
SAFE['host'] = 'armée'
SAFE['jour'] = 'jour'
SAFE['jours'] = 'jours'
SAFE['jument'] = 'jument'
SAFE['lance'] = 'lance'
SAFE['lendemain'] = 'lendemain'
SAFE['loingtain'] = 'lointain'
SAFE['matin'] = 'matin'
SAFE['mer'] = 'mer'
SAFE['mere'] = 'mère'
SAFE['meres'] = 'mères'
SAFE['mieulx'] = 'mieux'
SAFE['mois'] = 'mois'
SAFE['mont'] = 'mont'
SAFE['monts'] = 'monts'
SAFE['muraille'] = 'muraille'
SAFE['murailles'] = 'murailles'
SAFE['nepveu'] = 'neveu'
SAFE['nepveus'] = 'neveux'
SAFE['niepce'] = 'nièce'
SAFE['niepces'] = 'nièces'
SAFE['nouveaul'] = 'nouveau'
SAFE['nouveaux'] = 'nouveaux'
SAFE['nouvel'] = 'nouveau'
SAFE['nuit'] = 'nuit'
SAFE['ost'] = 'armée'
SAFE['ouste'] = 'armée'
SAFE['paix'] = 'paix'
SAFE['palais'] = 'palais'
SAFE['palefroi'] = 'palefroi'
SAFE['pere'] = 'père'
SAFE['plaine'] = 'plaine'
SAFE['port'] = 'port'
SAFE['porte'] = 'porte'
SAFE['portes'] = 'portes'
SAFE['povre'] = 'pauvre'
SAFE['povres'] = 'pauvres'
SAFE['premier'] = 'premier'
SAFE['prochain'] = 'prochain'
SAFE['route'] = 'route'
SAFE['sale'] = 'salle'
SAFE['salles'] = 'salles'
SAFE['secont'] = 'second'
SAFE['semaine'] = 'semaine'
SAFE['sentier'] = 'sentier'
SAFE['soeur'] = 'sœur'
SAFE['soeurs'] = 'sœurs'
SAFE['soir'] = 'soir'
SAFE['tour'] = 'tour'
SAFE['tours'] = 'tours'
SAFE['traité'] = 'traité'
SAFE['treuve'] = 'trouve'
SAFE['treves'] = 'trêves'
SAFE['val'] = 'val'
SAFE['vallée'] = 'vallée'
SAFE['vaulx'] = 'vallées'
SAFE['veille'] = 'veille'
SAFE['victoire'] = 'victoire'
SAFE['vieil'] = 'vieux'
SAFE['vieus'] = 'vieux'
SAFE['voie'] = 'voie'
SAFE['voies'] = 'voies'

# societe

SAFE['argent'] = 'argent'
SAFE['baillif'] = 'bailli'
SAFE['baillis'] = 'baillis'
SAFE['banneret'] = 'banneret'
SAFE['bannerets'] = 'bannerets'
SAFE['baron'] = 'baron'
SAFE['barons'] = 'barons'
SAFE['bourgeois'] = 'bourgeois'
SAFE['bourgeoise'] = 'bourgeoise'
SAFE['chambellan'] = 'chambellan'
SAFE['chevalerie'] = 'chevalerie'
SAFE['chevalier'] = 'chevalier'
SAFE['chevaliers'] = 'chevaliers'
SAFE['comte'] = 'comte'
SAFE['connestable'] = 'connétable'
SAFE['connestables'] = 'connétables'
SAFE['conte'] = 'comte'
SAFE['contes'] = 'comtes'
SAFE['denier'] = 'denier'
SAFE['deniers'] = 'deniers'
SAFE['duc'] = 'duc'
SAFE['duchesse'] = 'duchesse'
SAFE['ducs'] = 'ducs'
SAFE['escot'] = 'écot'
SAFE['escuier'] = 'écuyer'
SAFE['escuierie'] = 'écuyerie'
SAFE['heraulx'] = 'hérauts'
SAFE['heraut'] = 'héraut'
SAFE['marchans'] = 'marchands'
SAFE['marchant'] = 'marchand'
SAFE['marché'] = 'marché'
SAFE['mareschal'] = 'maréchal'
SAFE['mareschaulx'] = 'maréchaux'
SAFE['marquis'] = 'marquis'
SAFE['marquise'] = 'marquise'
SAFE['mestier'] = 'métier'
SAFE['office'] = 'office'
SAFE['or'] = 'or'
SAFE['prevost'] = 'prévôt'
SAFE['prevosts'] = 'prévôts'
SAFE['rente'] = 'rente'
SAFE['seneschal'] = 'sénéchal'
SAFE['seneschaux'] = 'sénéchaux'
SAFE['sergens'] = 'sergents'
SAFE['serjant'] = 'sergent'
SAFE['service'] = 'service'
SAFE['sol'] = 'sou'
SAFE['sols'] = 'sous'
SAFE['varlet'] = 'valet'
SAFE['varlez'] = 'valets'

# Expressions longues : appliquer avant les mots isolés.
EXPRESSIONS = {
    "si s'en partirent": 'ils partirent alors',
    'par celle maniere': 'de cette manière',
    'le jour ensuivant': 'le jour suivant',
    'en celle maniere': 'de cette manière',
    'quant ils orent': 'quand ils eurent',
    'si se partirent': 'ils partirent alors',
    'en tel maniere': 'de cette manière',
    'en ce temps là': 'à cette époque',
    'de là en avant': 'à partir de là',
    'de cy en avant': 'à partir de maintenant',
    'de ci en avant': 'à partir de maintenant',
    'le jour devant': 'la veille',
    'quant et quant': 'en même temps',
    'si tost comme': 'aussitôt que',
    'quant elle ot': 'quand elle eut',
    'de long temps': 'depuis longtemps',
    'tout ensemble': 'ensemble',
    "à l'endemain": 'le lendemain',
    'si tost que': 'aussitôt que',
    'tantost que': 'aussitôt que',
    'quant il ot': 'quand il eut',
    'si respondy': 'il répondit alors',
    "si s'en ala": "il s'en alla alors",
    'en ce temps': 'à cette époque',
    'pour ce que': 'parce que',
    'toutesfoiz': 'toutefois',
    'par ma foy': 'par ma foi',
    'sur ma foy': 'sur ma foi',
    'et quant': 'et quand',
    'puis que': 'puisque',
    'si fist': 'il fit alors',
    'si dist': 'il dit alors',
    'et lors': 'et alors',
    'ainçois': 'mais',
}

CONTEXT = {
    'ains': ['mais', 'plutôt', 'ainsi'],
    'or': ['or', 'maintenant', 'à présent'],
    'si': ['si', 'ainsi', 'alors'],
    'ja': ['déjà', 'jamais', 'désormais'],
    'moult': ['beaucoup', 'très'],
    'tantost': ['aussitôt', 'bientôt'],
    'devers': ['vers', 'du côté de'],
    'entour': ['autour', 'environ'],
    'maint': ['maint', 'plusieurs', 'beaucoup de'],
    'gent': ['gens', 'nation', 'peuple'],
    'ost': ['armée', 'ost'],
    'host': ['armée', 'hôte'],
    'mes': ['mes', 'mais'],
    'se': ['se', 'si'],
    'comme': ['comme', 'comment'],
    'fort': ['fort', 'très'],
    'bien': ['bien', 'beaucoup'],
    'tel': ['tel', 'si grand'],
    'pour ce que': ['parce que', 'pour ce que'],
}

KEEP = {
    'arrière-ban',
    'bailli',
    'ban',
    'banneret',
    'chevalerie',
    'châtellenie',
    'connétable',
    'denier',
    'destrier',
    'fief',
    'harnois',
    'haubert',
    'hommage',
    'héraut',
    'joute',
    'livre',
    'ost',
    'palefroi',
    'prévôt',
    'seigneur',
    'seigneurie',
    'sou',
    'sénéchal',
    'tournoi',
    'vassal',
    'vassalité',
    'écu',
    'écuyer',
}

# Compléments fréquents du XIVe siècle
_EXTRA = {
"dame":"dame","damoisel":"damoseau","damoiselle":"demoiselle","damoyselle":"demoiselle","demoiselle":"demoiselle","pucelle":"jeune fille","pucele":"jeune fille","fille":"fille","fils":"fils","mariage":"mariage","marier":"marier","espousa":"épousa","espouserent":"épousèrent","espouse":"épouse","espousée":"épousée","naistre":"naître","naitre":"naître","nascence":"naissance","naissance":"naissance","morir":"mourir","mourut":"mourut","moururent":"moururent","morut":"mourut","vivre":"vivre","vivoit":"vivait","vivoient":"vivaient","vesqui":"vécut","vesquit":"vécut","vesquirent":"vécurent","sceu":"su","sceut":"sut","sçavoit":"savait","sçavoir":"savoir","sçut":"sut","sçurent":"surent","cognoistre":"connaître","cognoissoit":"connaissait","cognoissoient":"connaissaient","congnurent":"connurent","congneut":"connut","congneu":"connu","conoistre":"connaître","apparut":"apparut","apparurent":"apparurent","apparoit":"apparaissait","sembloit":"semblait","sembloient":"semblaient","semblerent":"semblèrent","sembla":"sembla","creoit":"croyait","creoient":"croyaient","croire":"croire","creu":"cru","creut":"crut","creurent":"crurent","pensoient":"pensaient","pensoit":"pensait","pensa":"pensa","penserent":"pensèrent","entendoit":"entendait","entendoient":"entendaient","entendi":"entendit","entendirent":"entendirent","ouy":"oui","oy":"oui","oïr":"ouïr","oir":"ouïr","ouyt":"entendit","entendirent":"entendirent","regnoit":"régnait","regnoient":"régnaient","regner":"régner","regna":"régna","gouvernoit":"gouvernait","gouvernoient":"gouvernaient","gouverner":"gouverner","gouverna":"gouverna","commandoit":"commandait","commandoient":"commandaient","commanderent":"commandèrent","obey":"obéir","obeirent":"obéirent","obeissoit":"obéissait","obeissoient":"obéissaient","desir":"désir","desirait":"désirait","desiroit":"désirait","espoir":"espoir","esperance":"espérance","esperoit":"espérait","espererent":"espérèrent","doubte":"doute","doubtoit":"doutait","douterent":"doutèrent","paour":"peur","paour de mort":"peur de mort","ire":"colère","courroux":"colère","courroucé":"courroucé","haine":"haine","hayr":"haïr","amoit":"aimait","amoient":"aimaient","aimerent":"aimèrent","amer":"aimer","donna":"donna","donnerent":"donnèrent","donnoit":"donnait","donnoient":"donnaient","porta":"porta","porterent":"portèrent","portoit":"portait","portant":"portant","apporta":"apporta","apporterent":"apportèrent","leva":"leva","leverent":"levèrent","levoit":"levait","levoient":"levaient","sauva":"sauva","sauverent":"sauvèrent","sauvé":"sauvé","garda":"garda","garderent":"gardèrent","gardoit":"gardait","gardèrent":"gardèrent","prenoit":"prenait","prenoient":"prenaient","prendre":"prendre","pris":"pris","tenoit":"tenait","tenir":"tenir","tint":"tint","tinrent":"tinrent","porta":"porta","mena":"mena","menerent":"menèrent","menoit":"menait","conduisoit":"conduisait","conduisoient":"conduisaient","conduisit":"conduisit","conduisirent":"conduisirent","suivoit":"suivait","suivoient":"suivaient","ensuivi":"suivi","ensuivant":"suivant","poursuivoit":"poursuivait","poursuivoient":"poursuivaient","faisoient":"faisaient","oeuvre":"œuvre","euvre":"œuvre","ouvraige":"ouvrage","ouvrages":"ouvrages","besoing":"besoin","besoins":"besoins","mestier":"métier","affaire":"affaire","affaires":"affaires","chose":"chose","choses":"choses","maniere":"manière","manieres":"manières","raison":"raison","raisons":"raisons","parole":"parole","paroles":"paroles","nouvelle":"nouvelle","nouvelles":"nouvelles","aventure":"aventure","aventures":"aventures","fortune":"fortune","fortunes":"fortunes","hazard":"hasard","hazars":"hasards","occasion":"occasion","occasions":"occasions","besoigne":"besogne","besongne":"besogne","povoir":"pouvoir","volonté":"volonté","volente":"volonté","entencion":"intention","intention":"intention","dessein":"dessein","conseil":"conseil","conseilz":"conseils","avis":"avis","advis":"avis","adviser":"aviser","advisa":"avisa","advisèrent":"avisèrent","promesse":"promesse","parjure":"parjure","foy":"foi","serement":"serment","seremens":"serments","verité":"vérité","verite":"vérité","mensonge":"mensonge","mensonges":"mensonges","secret":"secret","secrets":"secrets","message":"message","messages":"messages","lettre":"lettre","lettres":"lettres","escrit":"écrit","escripre":"écrire","escripvoit":"écrivait","escripvi":"écrivit","escrivit":"écrivit","escrivirent":"écrivirent","lire":"lire","leut":"lut","lurent":"lurent","livre":"livre","livres":"livres","chronique":"chronique","chroniques":"chroniques","histoire":"histoire","histoires":"histoires","conte":"conte","contes":"comtes","racine":"racine","cause":"cause","causes":"causes","effect":"effet","effects":"effets","fin":"fin","fins":"fins","commencement":"commencement","commencemens":"commencements","milieu":"milieu","point":"point","points":"points","partie":"partie","parties":"parties","côté":"côté","costé":"côté","costez":"côtés","devant":"devant","derrain":"dernier","derrains":"derniers","dessus":"dessus","dessoubz":"dessous","dessous":"dessous","dedans":"dedans","dehors":"dehors","auprès":"auprès","emprès":"auprès","pres":"près","loing":"loin","loin":"loin","presque":"presque","quasi":"presque","environ":"environ","entour":"autour","contre":"contre","vers":"vers","envers":"envers","entre":"entre","parmi":"parmi","parmy":"parmi","selon":"selon","selonc":"selon","sans":"sans","sanz":"sans","avec":"avec","avecques":"avec","avuec":"avec","depuis":"depuis","depuisques":"depuis","dessusdit":"dit ci-dessus","dessusdite":"dite ci-dessus","dessusdits":"dits ci-dessus","dessusdittes":"dites ci-dessus"
}
for _k, _v in _EXTRA.items():
    SAFE.setdefault(_k, _v)
del _EXTRA

def modernize_word(word, allow_context=False):
    if word in SAFE: return SAFE[word], "safe"
    if allow_context and word in CONTEXT: return CONTEXT[word], "context"
    return word, "unchanged"

def modernize_expression(text):
    for old, new in sorted(EXPRESSIONS.items(), key=lambda x: len(x[0]), reverse=True):
        text = text.replace(old, new)
    return text

def stats():
    return {"safe": len(SAFE), "expressions": len(EXPRESSIONS), "context": len(CONTEXT), "keep": len(KEEP), "total": len(SAFE)+len(EXPRESSIONS)+len(CONTEXT)}
