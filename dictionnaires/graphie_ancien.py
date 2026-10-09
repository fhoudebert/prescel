# -*- coding: utf-8 -*-
"""
Règles d'orthographe de l'ancien français (fin XIIᵉ - XIIIᵉ siècle), pour
epub_modernise.py --mode graphie --epoque ancien. Mêmes principes que graphie_moyen.py (dont les
règles sont reprises à la suite) : une forme n'est proposée que si le résultat est un mot de la liste
française ; d'office seulement si une seule forme est possible par des règles sûres.

Règles propres aux scriptae de l'ancien français, réunies sans choisir de dialecte (un texte n'emploie
que les siennes) :
  anglo-normand   ei → oi (aveit → avoit → avait, dreit → droit, veie → voie, treis → trois),
                  u → o devant n ou m (sunt → sont, dunt → dont, unt → ont, sun → son, num → nom)
  champenois,     -aus / -iaus / -ax / -iax → -aux / -eaux (chevaus, chevax → chevaux ; biaus,
  francien        biax → beaux ; chastiaus → châteaux) ; an pour en (ansaigne → enseigne, tans →
                  temps n'est pas proposé : « tans » est aussi « tant ») ; -oiz → -ois
  tous            é devant r + e muet final : père, arrière (Meyer imprime « pére », « ariére ») ;
                  -érent → -èrent ; -ier des infinitifs → -er (laissier → laisser) ; -iez → -ez
                  (2ᵉ personne : saciez, oiez) ; z final → s (pluriels : genz, venuz) au choix.
EXCEPTIONS : vrais mots anciens qu'une règle changerait en un autre mot moderne (« feire » : faire, pas
foire ; « remest » : resta, pas remet ; « doz » : doux, pas dos ; « cenz » : cents, pas cens).
"""
import os
import runpy

_MOYEN = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "graphie_moyen.py"))

RULES = [
    # (motif, remplacement, sûre ?)
    (r"ei(?=t$|ent$|r$|te$)", "oi", True),     # anglo-normand : aveit, aveient, aveir, dreit, dreite
    (r"ei", "oi", False), (r"ei", "ai", False),  # + meison (maison), meis (mais)                        # rei, treis, meis (mois), peis (paix ? poids ?) : au choix
    (r"^([sdm]?)u(?=n[ts]?$)", r"\1o", True),   # sunt, dunt, unt, sun, mun
    (r"u(?=m$|mb)", "o", False),                 # num, nombre ? (au choix)
    (r"iaus$", "eaux", True), (r"iax$", "eaux", True), (r"iaux$", "eaux", True),   # biaus, oisiaus
    (r"aus$", "aux", False), (r"ax$", "aux", True),                                # chevaus, chevax
    (r"eals$", "eaux", True), (r"eal$", "eau", True),                              # beals, beal
    (r"oiz$", "ois", False), (r"oiz$", "oix", False), (r"oiz$", "ez", False),      # croiz, voiz ; verroiz
    (r"(?<=[^aeiou])o(?=v)", "ou", False),                                        # trova, prover
    (r"é(?=re?s?$)", "è", True), (r"é(?=rent$)", "è", True),                        # pére, ariére, parlérent
    (r"iez$", "ez", True),                                                        # saciez, oiez
    (r"z$", "s", False), (r"z$", "ts", False),                                    # genz, venuz ; diz, faiz, denz
    (r"^an(?=[cs])", "en", False),                                                # ansaigne, anseigne
] + [r for r in _MOYEN["RULES"] if r[0] not in (r"és$", r"oi(?=(?:s|t|ent)$)")] + [
    (r"oi(?=(?:t|ent)$)", "ai", True),   # imparfaits « avoit », « avoient » ; mais « -ois » : mois, rois, bois
]

IST_SUBJONCTIF = False   # « dist », « prist », « mist » : passé simple (dit, prit, mit) ; subjonctif « -ïst »

EXCEPTIONS = _MOYEN["EXCEPTIONS"] | set("""
feire feis remest doz alez cenz serreit oiez seiez feit reis rois mes mès les des lor
dex deus tens tanz ert erent esteit seit fet fist out ot ost el al as cil cist cest icil sis
ains einz or ore ores ja mie si se ne nel nes del dou tot toz tuit
mielz proz enz ez iez masc ére estant oste damaige damaiges forche forches doter dotérent dota
augiez faciez iaus iauz iax
""".split())

PREFERE = dict(_MOYEN.get("PREFERE", {}), **{
    "nostre": "notre", "vostre": "votre", "aveit": "avait", "esteit": "était", "dreit": "droit",
    "veie": "voie", "feiz": "fois", "croiz": "croix", "voiz": "voix", "noiz": "noix",
    "meison": "maison", "meisons": "maisons",
})
