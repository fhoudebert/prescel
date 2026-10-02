# Prescel

Préparer un livre numérisé — EPUB issu d'OCR (Google Livres, Gallica…) ou PDF — avant sa
relecture dans [Sigil](https://sigil-ebook.com/).

Prescel enchaîne des scripts Python indépendants depuis une interface web locale : nettoyage du
balisage, corrections propres aux imprimés anciens (s long, imparfaits en « oi », pluriels en
« ez » et en « ans »…), structure du livre (titres, notes, table des matières, numéros de page),
découpage par chapitre, puis rapport de relecture et copie surlignée à ouvrir dans Sigil.
Aucun mot n'est changé sans être listé : chaque étape vérifie le texte avant/après, et les
corrections douteuses restent au choix, dans des listes que l'on coche.

## Sommaire

- [Installation et lancement](#installation-et-lancement)
- [Déroulement dans Prescel](#déroulement-dans-prescel)
- [Les scripts](#les-scripts)
- [Imprimés anciens : listes de corrections](#imprimés-anciens--listes-de-corrections)
- [Dictionnaires](#dictionnaires)
- [Corriger d'après une autre édition](#corriger-daprès-une-autre-édition)
- [PDF](#pdf)
- [Structure : titres, notes, tableaux et listes](#structure--titres-notes-tableaux-et-listes)
- [Relecture dans Sigil](#relecture-dans-sigil)
- [Après des retouches dans Sigil](#après-des-retouches-dans-sigil)
- [Licence](#licence)

## Installation et lancement

Python 3.8+ suffit ; les autres outils sont facultatifs.

```
python3 prescel.py --epubcheck /opt/epubcheck/epubcheck-5.4.0/epubcheck.jar
```

La page s'ouvre dans le navigateur (http://127.0.0.1:8765). Les projets sont rangés dans
`~/Prescel/<livre>/` ; chaque étape écrit son propre fichier, l'original n'est jamais modifié.

| Option | Variable | Rôle |
|---|---|---|
| `--epubcheck CHEMIN` | `PRESCEL_EPUBCHECK` | contrôle epubcheck (`epubcheck.jar` ou commande) |
| `--sigil CHEMIN` | `PRESCEL_SIGIL` | bouton « Ouvrir dans Sigil » |
| `--tessdata DOSSIER` | `PRESCEL_TESSDATA` | modèles Tesseract (OCR des PDF) |
| `--workdir DOSSIER` | | dossier des projets (défaut `~/Prescel`) |
| `--port N`, `--no-browser` | | serveur local |

Facultatif :
- import PDF : `pip install pymupdf` ;
- OCR des PDF sans texte : `apt install tesseract-ocr tesseract-ocr-fra` (et le modèle `frm`,
  moyen français, qui lit le ſ) ;
- epubcheck (Java) pour le contrôle ; Sigil pour la relecture.

## Déroulement dans Prescel

1. **Déposer** un EPUB ou un PDF. Prescel l'analyse (Google Livres ? s long ? imparfaits en
   « oi » ? journal daté ? titres en capitales ?) et coche les étapes et réglages adaptés ;
   chaque réglage est expliqué à côté, ceux qui touchent au texte sont signalés.
2. **Préparer le livre** : les étapes s'enchaînent, le journal s'affiche en direct, epubcheck
   contrôle le résultat. Onglets : journal, table des matières obtenue, listes de corrections
   (S long, oi → ai, ez → és, ans → ants, Modernisation), rapport de relecture, conseils Sigil.
3. **Trancher les listes** : dans chaque onglet, cocher ou décocher les mots laissés au choix,
   enregistrer.
4. **Relire dans Sigil** la version « à relire », où chaque cas douteux est surligné.
5. **Relance ciblée** après Sigil (ou après avoir déposé une version retouchée) : les étapes de
   listes, structure, découpage et rapport sont rejouées sur le fichier enregistré ; les
   marqueurs sont retirés d'abord, le fichier de départ est archivé dans `archives/`.
6. **Retirer les marqueurs** quand la relecture est finie : le fichier `…-relu.epub` est prêt,
   contrôlé par epubcheck.

## Les scripts

Chaque script s'utilise aussi seul (`python3 script.py --help`).

| Script | Rôle |
|---|---|
| `pdf_to_epub.py` | PDF → EPUB brut : OCR de Gallica (ALTO), couche texte du PDF ou OCR Tesseract ; géométrie des pages |
| `epub_inline2css.py` | styles en ligne → classes (facultatif) |
| `epub_simplify.py` | nettoyage du balisage OCR, lettrines, DOCTYPE XHTML 1.1 ; texte vérifié avant/après |
| `epub_longs.py` | s long lu « f » (« eft » → « est ») |
| `epub_modernise.py` | imparfaits en « oi » (`--mode oi`), pluriels en « ez » (`--mode ez`), passé simple en « erent » (`--mode erent`), pluriels en « ans » (`--mode ants`), vocabulaire (`--mode vocab`) |
| `epub_reference.py` | corrige l'EPUB d'après une autre édition du texte (PDF ou texte) : alignement mot à mot, catégories au choix, rapport d'écarts |
| `epub_structure.py` | livres, chapitres, titres en capitales, dates d'un journal, sommaires, notes reliées, avertissement Google retiré, table des matières, liste des pages |
| `epub_split_h1.py` | un fichier par livre / chapitre |
| `epub_review.py` | rapport de relecture, copie surlignée, dictionnaire pour Sigil ; `--unmark`, `--fix-doctype`, `--sans` |
| `epub_pages.py` | liste des pages du livre papier rétablie ou réparée ; `--purge` |

Ordre des étapes : import PDF → nettoyage → s long → oi → ez → erent → ans → vocabulaire → référence → structure →
découpage → rapport. Le s long passe en premier : les autres listes supposent « estoit », pas
« eftoit ».

## Imprimés anciens : listes de corrections

Toutes fonctionnent de la même façon : une liste TSV par livre (`appliquer`, `forme_lue`,
`correction`, occurrences…), les corrections sûres appliquées d'office, les autres laissées au
choix dans un onglet de Prescel. Les choix enregistrés sont repris à chaque relance ; la casse est
respectée (« Estoit » → « Était ») ; seuls les mots listés changent.

| Onglet | Exemple | Laissé au choix |
|---|---|---|
| **S long** (`epub_longs.py`) | « eft » → « est », « faifoit » → « faisoit » | mots qui existent sous les deux formes : « font »/« sont », « fait »/« sait » |
| **oi → ai** (`--mode oi`) | « il estoit » → « il était », « auroient » → « auraient » | noms propres et nationalités (« François », « Anglois »), formes inconnues |
| **ez → és** (`--mode ez`) | « les bontez » → « les bontés », « sont armez » → « armés » | formes inconnues ; « vous avez », « allez-vous », « Venez » sont toujours gardés |
| **erent → èrent** (`--mode erent`) | « ils allerent » → « allèrent », « donnérent » → « donnèrent » | forme aussi adjectif (« different »), forme inconnue (s long à corriger d'abord) |
| **ans → ants** (`--mode ants`) | « charmans » → « charmants », « Penitens » → « Pénitents » | rien d'office : décocher ce qu'on veut garder |
| **Modernisation** (`--mode vocab`) | « luy » → « lui », « mesme » → « même », « aussi tost » → « aussitôt » | graphies qui sont aussi des mots modernes (« des » → « dès ») |

Garde-fous communs :
- le livre sert de dictionnaire (une forme corrigée doit exister ailleurs dans le livre), et une
  liste libre de mots français (`--wordlist auto`, téléchargée une fois) repère les vrais mots :
  « force », « fleur », « trois », « droit », « sens », « gens » ne sont jamais touchés ;
- les mots laissés au choix du s long et des imparfaits en « oi » sont signalés un par un dans le
  rapport, avec le lien vers la page scannée ;
- les accents aigus qui manquent sont rétablis quand la forme accentuée existe (« deputez » →
  « députés », « Residens » → « Résidents ») ;
- la modernisation du vocabulaire est un choix d'édition : l'étape n'est jamais cochée d'office.

Une fois une liste tranchée, décocher son étape : à la relance sur le fichier marqué, ses mots ne
sont plus surlignés. Le réglage avancé « Ne pas signaler » de l'étape « Préparer la relecture »
(`epub_review.py --sans CATÉGORIE`) retire de même les autres catégories déjà traitées.

## Dictionnaires

De simples fichiers Python `{"ancien": "moderne", …}`, à compléter librement :

| Fichier | Utilisé par | Contenu |
|---|---|---|
| `dictionnaires/verbes_oi.py` | oi → ai | imparfaits et conditionnels, avec la forme moderne complète (« estoit » → « était », « envoyeroit » → « enverrait ») |
| `dictionnaires/pluriels_ez.py` | ez → és | formes qui ne suivent pas la règle (« excez » → « excès », « extremitez » → « extrémités ») |
| `dictionnaires/pluriels_ants.py` | ans → ants | formes à accent ou abîmées (« presens » → « présents ») |
| `dictionnaires/vocabulaire_17_18.py` | Modernisation | vocabulaire et expressions (« luy », « mesme », « païs », « aussi tost »), et erreurs d'OCR fréquentes relevées par comparaison avec une édition moderne (« vlande » → « viande », « fubtil » → « subtil ») |

Un dictionnaire passe toujours avant la règle générale de son étape.

## Corriger d'après une autre édition

Quand une autre édition du même texte existe (PDF ou texte), `epub_reference.py` (étape « Corriger
d'après une autre édition ») retrouve chaque paragraphe de l'EPUB dans cette référence — même si
l'une est en graphie ancienne et l'autre modernisée — et compare les deux mot à mot. Notes, appels
de note et repères de pagination de la référence sont écartés.

```
python3 epub_reference.py livre.epub "Chardin voyages.pdf" --from-page 118 -o livre-corrige.epub
```

Seules les catégories demandées (`--apply`) sont appliquées ; toutes sont listées dans le rapport
d'écarts (`…-ecarts.html`) :

| Catégorie | Exemple | Par défaut |
|---|---|---|
| `ocr` | « font » → « sont », « vlande » → « viande », « Dadlan » → « Dadian », « Roy al » → « royal » | appliquée |
| `esperluette` | « & » → « et » | non |
| `apostrophes` | « qu'il » → « qu’il » | non |
| `casse` | « Roi » → « roi » | non |
| `graphie` | « par tout » → « partout », « Tiflis » → « Tifflis » | non |
| `variante` | « leurs » / « leur », « Européens » / « Européans » (autre mot correct) | non |

Les mots en plus ou en moins ne sont jamais appliqués. Les noms propres et abréviations dont la
graphie diffère restent en variantes, sauf confusion évidente de l'OCR (l / i).

**Droits** : une édition moderne (texte établi, modernisé, annoté) est une œuvre protégée même si
le texte d'origine est libre. Corriger les erreurs d'OCR d'après elle revient à vérifier une
lecture ; reprendre ses choix de modernisation, de ponctuation ou de majuscules reproduit son
travail d'éditeur : demandez l'accord de l'éditeur avant de diffuser un tel résultat.

## PDF

`pdf_to_epub.py` (étape « Import du PDF ») choisit la source du texte page par page :
- **Gallica** : si le nom du PDF contient l'identifiant (`bpt6k…`, `btv1b…`, ou réglage
  « Identifiant Gallica »), l'OCR de la BnF est récupéré en ALTO — la couche texte des PDF Gallica
  colle les mots — avec la pagination imprimée ; les pages de reliure sont ignorées ;
- **couche texte** du PDF, si elle est exploitable ;
- **OCR Tesseract** sinon (`fra`, `frm` ou les deux ; images pleine résolution de Gallica en option ;
  réglage « Pages à traiter » pour un essai rapide).

La position des lignes sert à retirer titres courants, folios, signatures et réclames, à placer
les manchettes, à recoller césures, lettrines et paragraphes coupés par les pages, à garder les
vers ligne à ligne, à reconnaître tableaux et listes. Les mots peu sûrs pour l'OCR sont surlignés.

## Structure : titres, notes, tableaux et listes

- **Titres** : « CHAPITRE II », « Chap. XII. », ordinaux en toutes lettres même abîmés par l'OCR ;
  livres (« Le second liure ») ; titres composés en capitales sur plusieurs lignes ; titre placé
  avant « Chapitre N » (éditions anciennes) ; dates d'un journal (« 6. Mars. »). Les titres
  courants répétés (« PREFACE » en tête de chaque page) sont retirés.
- **Sommaires** : le paragraphe court qui suit « Chapitre N » (« Des Images. ») reçoit la classe
  `sommaire` et complète l'entrée de la table : « Chapitre IX — Des Images ». Une classe `sommaire`
  posée à la main dans Sigil juste sous un titre est conservée à la relance. Le `toc.ncx` étant
  régénéré à chaque relance, c'est dans le texte (titre + sommaire) qu'il faut corriger, pas dans
  le `toc.ncx`.
- **Notes** : « bonneter1 » devient un appel en exposant relié à « 1. Saluer en ôtant le bonnet »,
  aller-retour par liens ; les notes dont l'appel est perdu sont listées dans le rapport.
- **Table des matières** reconstruite depuis les titres ; **liste des pages** du livre papier
  (page-map de Google convertie en `pageList` standard).
- **Tableaux et listes** : à l'import PDF, lignes coupées en colonnes → `<table class="tableau">`,
  lignes à marque (« 1. », « a) ») → `<ol class="liste">` ; dans les EPUB de Google, table
  imprimée et index → `<ul class="table-imprimee">`, `<ul class="index">`.

## Relecture dans Sigil

Le rapport (`…-relecture.html`) liste chaque cas avec le fichier Sigil, l'extrait (bouton
« copier » pour la recherche de Sigil) et le lien vers la page scannée : mots collés ou coupés,
coupures par trait d'union (« estran- ges »), casse mélangée, chiffres dans un mot, lettres
isolées, lettrines perdues, ponctuation, paragraphes très courts ou coupés, numérotation des
chapitres, notes sans appel, mots peu sûrs pour l'OCR, s long et imparfaits laissés au choix.

Dans la version « à relire », chaque cas est entouré de `<span class="a-verifier">` : rechercher
`a-verifier` dans Sigil pour aller de cas en cas. Le fichier `…-dictionnaire.txt` (mots du livre)
s'ajoute aux dictionnaires utilisateur de Sigil pour que l'orthographe ancienne ne soit plus
soulignée. Quand la relecture est finie : bouton « Retirer les marqueurs », ou

```
python3 epub_review.py livre-a-relire.epub --unmark -o livre-relu.epub
```

## Après des retouches dans Sigil

- **Numéros de page** : les ancres vides `<a id="GBS.PA31"></a>` marquent le début de chaque page
  du livre papier et alimentent la liste des pages du `toc.ncx`. Sigil la supprime quand il
  régénère la table des matières ; la relance ciblée la refait, ou :
  ```
  python3 epub_pages.py livre-relu.epub -o livre-pages.epub            # rétablir / réparer
  python3 epub_pages.py livre-relu.epub -o livre-sans-pages.epub --purge   # ou retirer les ancres
  ```
  Si les ancres ont disparu du texte (purge, nettoyage dans Sigil), elles peuvent être reportées
  depuis une autre version du livre, même en graphie ancienne — typiquement l'EPUB de Google
  d'origine, dont la page-map donne aussi les numéros imprimés :
  ```
  python3 epub_pages.py livre-relu.epub --from livre-google.epub -o livre-pages.epub
  ```
- **Id en double** (couper un paragraphe dans Sigil recopie son `id`), **ancres disparues**
  encore visées par le `toc.ncx`, **playOrder identiques** : réparés par `epub_pages.py` et par la
  relance ciblée, marqueurs conservés.
- **Liens cassés** après un renommage ou un déplacement dans Sigil (« Styles/livre.css » au lieu de
  « ../Styles/livre.css », image introuvable) : refaits vers le fichier du même nom par
  `epub_pages.py` et par la relance ciblée.
- **DOCTYPE** : Google écrit en XHTML 1.0 Strict, refusé par epubcheck dans un EPUB 2 (`HTM-004`).
  Toutes les étapes le corrigent ; pour un fichier en cours de relecture :
  `python3 epub_review.py livre-a-relire.epub --fix-doctype`.

## Licence

Prescel est distribué sous licence MIT (fichier `LICENSE`).

Outils et données utilisés, qui ont leur propre licence :
- PyMuPDF (import PDF, facultatif) : AGPL-3.0 ou licence commerciale d'Artifex ;
- Tesseract (OCR, facultatif) : Apache 2.0 ;
- epubcheck (contrôle, facultatif) : BSD-3-Clause ;
- liste de mots « an-array-of-french-words » (téléchargée par `--wordlist auto`) : MIT ;
- OCR et images de Gallica : conditions de réutilisation de la BnF (usage non commercial libre).
