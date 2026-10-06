# Prescel

Préparer un livre numérisé — EPUB issu d'OCR (Google Livres, Gallica…) ou PDF — avant sa
relecture dans [Sigil](https://sigil-ebook.com/), puis le publier : EPUB relu, ou texte et HTML
pour [Project Gutenberg](https://www.gutenberg.org/).

Prescel enchaîne des scripts Python indépendants depuis une interface web locale : nettoyage du
balisage, corrections propres aux imprimés anciens (s long, imparfaits en « oi », pluriels en
« ez » et en « ans »…), structure du livre (titres, notes, table des matières, numéros de page),
découpage par chapitre, puis rapport de relecture et copie surlignée à ouvrir dans Sigil.
Aucun mot n'est changé sans être listé : chaque étape vérifie le texte avant/après, et les
corrections douteuses restent au choix, dans des listes que l'on coche.

## Sommaire

- [Réutiliser Prescel : de Gallica ou Google Livres à Gutenberg ou à une autre plateforme](#réutiliser-prescel--de-gallica-ou-google-livres-à-gutenberg-ou-à-une-autre-plateforme)
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
- [Publier sur Project Gutenberg](#publier-sur-project-gutenberg)
- [Typographie française](#typographie-française)
- [Licence](#licence)

## Réutiliser Prescel : de Gallica ou Google Livres à Gutenberg ou à une autre plateforme

Les scripts ont été mis au point sur des récits de voyage des XVIᵉ–XVIIIᵉ siècles (Belon, Chardin,
Thévenot, Dellon, Choisy, Carré) et un texte du XIXᵉ (Montluc, Hachette 1872). Ils servent tels
quels pour tout livre ancien en français numérisé par Google Livres, Gallica ou Internet Archive.
Les étapes ci-dessous peuvent se suivre dans l'interface Prescel ou en ligne de commande.

### 1. Choisir la cible avant de corriger

La plateforme visée décide de ce qu'on a le droit de changer : à trancher **avant** les étapes de
modernisation.

| Cible | Texte attendu | Étapes à éviter | Fichiers à produire |
|---|---|---|---|
| **Project Gutenberg** | fidèle à **une** édition du domaine public aux États-Unis (publiée il y a plus de 95 ans) ; orthographe d'origine | modernisation (oi, ez, erent, ans, vocabulaire) ; corrections tirées d'une édition moderne protégée, sauf erreurs d'OCR | `.txt` UTF-8 + `.html` HTML5 valide (`epub_gutenberg.py`) |
| **Wikisource** | fidèle, page à page, aligné sur le fac-similé | modernisation ; découpage par chapitre | texte par page (l'EPUB sert de base de relecture) |
| **Édition personnelle, site, bibliothèque numérique, liseuse** | libre : modernisation possible si elle est annoncée | — | EPUB relu (`…-relu.epub`), validé par epubcheck |
| **Boutiques d'ebooks** (Kobo, Apple, Google Play, Amazon…) | conditions propres à chaque boutique pour le domaine public (certaines exigent un apport : notes, présentation, traduction) | à vérifier dans leurs conditions du moment | EPUB validé par epubcheck |

Dans tous les cas : texte dans le domaine public dans le pays de diffusion (en France, auteur mort
depuis plus de 70 ans) ; illustrations ajoutées (portrait de couverture…) de licence compatible ;
une édition moderne utilisée comme référence (`epub_reference.py`) ne sert qu'à corriger l'OCR,
pas à en reprendre les choix d'éditeur.

### 2. Récupérer la source et ce qu'il faut garder

| Source | À télécharger | À conserver tout au long du travail |
|---|---|---|
| **Google Livres** (affichage complet) | l'EPUB (« Télécharger EPUB ») ; le PDF pour comparer | l'EPUB d'origine : ses ancres et sa page-map sont la seule source sûre des numéros de page (`epub_pages.py --from`) |
| **Gallica** | le PDF, **sans le renommer** (son nom contient l'identifiant `bpt6k…` / `btv1b…`) | l'identifiant : il donne l'OCR de la BnF (ALTO), la pagination et les liens vers chaque vue |
| **Internet Archive** | le PDF (couche texte) ou l'EPUB | le PDF |
| **Autre édition du même texte** (même moderne) | PDF, EPUB ou texte | uniquement pour `epub_reference.py --apply ocr` (`ponctuation` en plus si c'est la même édition) |

Pour la vérification des droits par Gutenberg, garder aussi les images de la page de titre et de
son verso.

### 3. Parcours A — Google Livres → EPUB relu → Gutenberg

```
# 1. préparation (ou bouton « Préparer le livre » dans Prescel, réglages préconisés)
python3 epub_simplify.py  google.epub -o 1.epub --join-hyphens --flatten-br --lettrines
python3 epub_longs.py     1.epub -o 2.epub --tsv livre-s-long.tsv --wordlist auto
python3 epub_structure.py 2.epub -o 3.epub --merge-pages --drop-furniture --drop-google-notice \
        --caps-titles --link-notes            # + --title-before, --date-titles selon le livre
python3 epub_split_h1.py  3.epub -o 4.epub --tag h1,h2
python3 epub_review.py    4.epub --report relecture.html --mark a-relire.epub \
        --longs-tsv livre-s-long.tsv --dict-out dictionnaire.txt

# 2. relecture dans Sigil (rechercher « a-verifier »), puis relance ciblée dans Prescel

# 3. finalisation
python3 epub_review.py a-relire.epub --unmark -o relu.epub
python3 epub_pages.py  relu.epub -o relu.epub            # liens, id en double, liste des pages
python3 epub_pages.py  relu.epub --from google.epub -o relu.epub   # si les numéros de page ont disparu
python3 epub_typo.py   relu.epub -o relu.epub            # typographie française
python3 epub_gutenberg.py relu.epub -o Mon_livre --title-file titre
```

Pour Gutenberg, **ne pas lancer** `epub_modernise.py` et limiter `epub_reference.py` à
`--apply ocr`. Le s long rendu par « s » est l'usage de Gutenberg.

### 4. Parcours B — Gallica (PDF) → EPUB relu → Gutenberg

```
python3 pdf_to_epub.py "Titre_[...]Auteur_bpt6k9627352r.pdf" -o brut.epub
#   OCR de la BnF disponible : utilisé automatiquement (ALTO) ;
#   sinon : --source ocr --lang fra (ou frm, fra+frm), et --pages 20-40 pour un essai
python3 epub_longs.py brut.epub -o 2.epub --tsv livre-s-long.tsv --wordlist auto
python3 epub_structure.py 2.epub -o 3.epub --drop-furniture --caps-titles --link-notes
# puis comme le parcours A (découpage, rapport, Sigil, finalisation)
```

Le nettoyage (`epub_simplify.py`) est inutile : l'EPUB produit est déjà propre. Les liens du
rapport de relecture ouvrent la vue Gallica de chaque page.

#### Édition savante en plusieurs volumes (variantes, errata, plusieurs numérisations)

Chaîne suivie pour les Chroniques de Froissart éditées par Kervyn de Lettenhove (Gallica +
Google Livres) ; elle vaut pour toute édition critique du XIXe siècle du même genre (apparat de
variantes en bas de page, errata en fin de volume, table des sommaires) :

```
python3 pdf_to_epub.py "Titre_[...]_bpt6k38933z.pdf" -o 1.epub            # ALTO Gallica ; --variantes auto, --notes auto
python3 epub_reference.py 1.epub google.epub --apply ocr,ponctuation -o 2.epub --report ecarts.html
python3 epub_structure.py 2.epub -o 3.epub --merge-pages --drop-furniture --caps-titles --link-notes
python3 epub_errata.py 3.epub -o 4.epub --tsv livre-errata.tsv --retirer   # liste relue sur le scan, relancer
python3 livres/froissart-kervyn-finitions.py 4.epub 5.epub --tome XIII --ordinal TREIZIÈME \
        --annees 1386-1389 --sous-titre "(…)" --date 1871 [--table-fix livres/tome.json]
python3 epub_recolle.py 5.epub -o 6.epub --tsv livre-recolle.tsv
python3 epub_guillemets.py 6.epub -o 7.epub
python3 epub_apparat.py 7.epub -o 8.epub
# facultatif : seconde lecture d'un PDF d'images du même livre (Google, Internet Archive)
python3 pdf_tesseract.py images.pdf -o livre-tesseract.txt
python3 epub_reference.py 8.epub google.epub --confirm livre-tesseract.txt \
        --apply ocr,graphie,casse,variante,guillemets --keep @livre-errata.tsv -o 9.epub
python3 epub_typo.py 9.epub -o maitre.epub
python3 epub_review.py maitre.epub --report relecture.html --mark a-relire.epub
# relecture dans Sigil, puis
python3 epub_review.py relu.epub --unmark -o maitre.epub
python3 epub_gutenberg.py maitre.epub -o Mon_livre
```

Ce que fait chaque étape, et ses précautions :

- **import** : l'apparat (« 1-2 Gens. 3-4 Viel. ») est reconnu à son interligne plus serré et mis à
  part (`<p class="variantes">`), les appels passent en exposant ; les notes « (1) … » de bas de
  page vont dans `<p class="note">` ; les « répétés en tête de chaque ligne d'une citation sont
  retirés (`--garder-guillemets-de-ligne` pour les garder). Gallica refuse parfois les requêtes
  trop rapprochées (« too many requests ») : le script ralentit et réessaie ; une page encore
  refusée vient de la couche texte du PDF et est listée, une relance ne redemande qu'elle ;
- **référence** : une autre numérisation de la **même** édition. `--apply ponctuation` rétablit
  les virgules, points-virgules et deux-points perdus par l'OCR. Si la référence est un PDF dont le
  texte colle les mots (PDF Google ou Internet Archive), faire la ponctuation seule, puis l'OCR
  dans une seconde passe avec `--prudent` ;
- **errata** : la liste `livre-errata.tsv` est écrite d'après l'OCR ; la relire sur le scan (les
  pages et lignes imprimées sont parfois fausses), ajouter quelques mots de la ligne en
  « contexte » pour les mots courts, relancer. `--retirer` ôte la section (et son entrée du
  sommaire) une fois tout appliqué ; `epub_gutenberg.py` le signale dans la note de transcription ;
- **finitions** (`livres/`) : page de titre de l'édition originale à la place de celle du
  fac-similé, titre de départ ponctué, pages blanches retirées, table imprimée refaite en tableau.
  `--table-fix` : fichier JSON `{"titre lu": ["titre juste", "page ou null"]}` pour les mots que
  l'OCR de la table a perdus (exemple : `livres/froissart-t13-table.json`). Pour un autre auteur,
  copier ce script et changer la page de titre ;
- **recollage, guillemets, apparat** : corrections évidentes sans plus-value de relecture (mots
  coupés ou collés, « u » et « n » lus pour « et », numéros d'apparat lus « U ») ; tout est listé ;
- **seconde lecture** (`--confirm`) : une correction n'est appliquée que si les deux OCR lisent la
  même chose ; garde-fous : accents seulement pour la graphie (jamais retirés sans appui), pas de
  petits mots, pas d'exposants (« VIIIm », « IIIIxx »), pas de titres courants, pas de mots
  recollés inconnus ; `--keep @livre-errata.tsv` empêche de rendre aux mots de l'errata la faute
  imprimée que les deux lectures retrouvent ;
- **relecture** : le rapport signale aussi les guillemets non refermés ;
- **Gutenberg** : les variantes sont regroupées en fin de volume page par page, les numéros de page
  sont en marge du HTML (lien vers les variantes) et entre accolades `{12}` dans le texte ; la
  table imprimée est rendue en tableau (points de conduite dans le texte).

#### Moderniser l'orthographe d'un texte en moyen français (Froissart)

`epub_modernise.py --epoque moyen` change de profil de dictionnaires : le XIVᵉ siècle n'a ni le
lexique ni les règles des XVIIᵉ-XVIIIᵉ (« -és » y est une 2ᵉ personne : « avés » → « avez »,
quand au XVIIᵉ « bontez » → « bontés » ; `--mode ez` est donc refusé). Chaîne suivie pour les
tomes 12 à 14 (≈ 72-74 % → 88-91 % de mots à l'orthographe moderne), à partir de l'EPUB relu :

```
python3 epub_modernise.py relu.epub -o 1.epub --epoque moyen --mode vocab --tsv livre-moderne.tsv --wordlist auto
python3 epub_modernise.py 1.epub -o 2.epub --epoque moyen --mode vocab \
        --dict dictionnaires/noms_froissart.py --tsv livre-noms.tsv --wordlist auto
python3 epub_modernise.py 2.epub -o 3.epub --epoque moyen --mode oi --tsv livre-oi.tsv --wordlist auto
python3 epub_modernise.py 3.epub -o 4.epub --epoque moyen --mode graphie --tsv livre-graphie.tsv --wordlist auto
python3 epub_modernise.py 4.epub -o 5.epub --epoque moyen --mode erent --tsv livre-erent.tsv --wordlist auto
python3 epub_modernise.py 5.epub -o 6.epub --epoque moyen --mode ants --tsv livre-ants.tsv --wordlist auto
python3 epub_modernise.py 6.epub -o moderne.epub --epoque moyen --mode vocab --tsv livre-moderne2.tsv --wordlist auto
```

- `dictionnaires/moyen_francais.py` : formes sûres (« prins » → « pris », « misrent » → « mirent »,
  « voulenté » → « volonté », « roiaulme » → « royaume ») ; `FORCE` pour les formes qui sont aussi
  un mot moderne mais ont presque toujours ce sens chez l'auteur (« conte » → « comte ») ;
  `VERSION_MODERNE` pour les mots dont le sens a changé (« cuidier », « nennil », « plenté »),
  jamais appliqués : ils relèvent d'une version reformulée ;
- `dictionnaires/graphie_moyen.py` : règles d'orthographe enchaînées (s muet, y, lettres doublées,
  « aulx », « ung », « -ié », picard « ch », « -aige »…) ; une forme n'est proposée que si le
  résultat est un mot de la liste française ; d'office quand une seule forme est possible
  (`PREFERE` tranche « nostre » → « notre ») ; sinon au choix (« eust » : eut ou eût) ;
  `EXCEPTIONS` : vrais mots anciens qu'une règle changerait en un autre mot (« ens », « lés »,
  « celier ») ;
- `dictionnaires/noms_froissart.py` : noms propres de l'auteur (« Jehan » → « Jean »,
  « Portingal » → « Portugal ») ;
- choix d'après le contexte : « party » devient « parti » après un auxiliaire ou un déterminant
  (« est party », « en ce party ») et « partit » sinon ; « logiés » devient « logez » après « vous »,
  « logés » sinon ; « grant » devient « grande » devant un nom féminin, « grand » devant un nom
  masculin terminé par une consonne (`CONTEXTE`, appliqué de nouveau en fin de chaîne, une fois les
  noms modernisés) ; « quant » devient « quand », sauf dans « quant à » ;
- ce qui reste : vocabulaire et syntaxe de Froissart (« moult », « ains », « si », « grant
  joie »), à garder dans une orthographe modernisée ; dans Prescel, étapes « Modernisation du
  vocabulaire » (Époque : moyen français), « Orthographe du moyen français » et « Noms propres ».

#### Poème édité vers par vers (Guillaume le Maréchal, éd. Paul Meyer)

Les deux tomes se reconstruisent d'une traite depuis les sources du dépôt :
`sh livres/guillaume-marechal.sh [dossier]`. Les vers où le compte a dû être recalé sur un numéro
imprimé sont repérés `a-verifier` dans l'EPUB (« Numérotation : vers 2952 compté 2954 ») : un vers
coupé, collé ou perdu est à chercher tout près. Ni `epub_guillemets.py` ni `epub_recolle.py` ne
conviennent à l'ancien français (« u » y veut dire « où », « Partant » est un mot).

Quand Gallica n'a pas d'OCR (pas de couche texte, ALTO refusé), le texte vient d'un autre PDF
(Internet Archive) et les images Gallica servent de seconde lecture :

```
python3 pdf_vers.py lhistoiredeguill01meyeuoft.pdf -o 1.epub --pages 1-383   # vers, numéros, manchettes, notes
python3 livres/guillaume-marechal-t1-finitions.py 1.epub 2.epub                # page de titre, titres
python3 livres/guillaume-marechal-t1-errata.py 2.epub 2b.epub                  # errata de l'avant-propos (« lis. »)
python3 pdf_tesseract.py gallica.pdf -o gallica-tesseract.txt                 # seconde lecture
python3 epub_reference.py 2.epub gallica-tesseract.txt --prudent --apply ocr -o 3.epub
python3 epub_typo.py 3.epub -o maitre.epub
python3 epub_review.py maitre.epub --ancien --report relecture.html --mark a-relire.epub
```

- `pdf_vers.py` garde une ligne imprimée par vers (pdf_to_epub.py les recollerait en paragraphes),
  recolle les morceaux de vers que l'OCR a posés sur des lignes de base décalées, lit les numéros
  de la marge même mal lus (« 1 60 », « 2!2!0 ») et recompte les vers : un numéro imprimé ne recale
  le compte que s'il est proche (un chiffre mal lu ne le dérègle pas) ; le journal liste les
  pages où le compte a été recalé (vers coupé ou deux vers collés à vérifier). Une ligne en retrait
  ouvre un paragraphe ; les notes du bas de page suivent le paragraphe sans le couper ;
- PDF Gallica avec OCR (tome 2) : `pdf_vers.py livre_bpt6k203427s.pdf --premier-vers 10153
  --debut 8 --pages 1-338` lit la couche texte du PDF ; les numéros de page viennent de la
  pagination de Gallica (l'ark est pris dans le nom du fichier) ; les seuils s'adaptent à la
  taille de la page ; la référence Google de ce tome, d'OCR plus faible, ne sert qu'en mode
  prudent et sans liste de mots modernes (`--prudent --wordlist ""`), pour ne pas « corriger »
  l'ancien français en français moderne ;
- vocabulaire du tome 2 (fin du volume, deux colonnes) : `pdf_glossaire.py livre.pdf -o vocab.xhtml
  --pages 340-395 --premiere-vue 338`, puis la référence Google en deux passes (ponctuation, puis
  OCR prudente) et `epub_abimes.py` pour les gloses en italique illisibles ; le fichier obtenu est
  donné en troisième argument à `livres/guillaume-marechal-t2-finitions.py` ;
- errata de fin du tome 2, qui vise les vers des deux tomes : `epub_errata_vers.py livre.epub -o
  livre-2.epub --tsv livres/guillaume-marechal-errata.tsv` (liste relue sur le scan ; seules les
  leçons « lis. » et la ponctuation y sont, pas les corrections proposées « corr. ») ;
- numéros de vers : deux numéros imprimés sur la même page dont l'écart égale l'écart de lignes se
  confirment l'un l'autre et recalent le compte même s'il a dérivé de plus de 8 vers ;
- `epub_review.py --ancien` : « e » (et), « i » (y), « o » (avec), « u » sont des mots ; les
  lettres restituées par l'éditeur (« maisni[é]e ») et l'apparat ne sont pas des lettres isolées ;
- `epub_gutenberg.py` aligne le numéro de vers à droite (texte) ou dans la marge (HTML) et met
  les manchettes entre crochets.

### 5. Parcours C — édition modernisée (usage personnel, autre plateforme)

Après le s long, ajouter les listes de modernisation, à trancher dans les onglets de Prescel :

```
python3 epub_modernise.py 2.epub -o 2b.epub --mode oi    --tsv livre-oi.tsv    --wordlist auto
python3 epub_modernise.py 2b.epub -o 2c.epub --mode ez   --tsv livre-ez.tsv    --wordlist auto
python3 epub_modernise.py 2c.epub -o 2d.epub --mode erent --tsv livre-erent.tsv --wordlist auto
python3 epub_modernise.py 2d.epub -o 2e.epub --mode ants --tsv livre-ants.tsv  --wordlist auto
python3 epub_modernise.py 2e.epub -o 2f.epub --mode vocab --tsv livre-moderne.tsv --wordlist auto
```

et, si une autre édition existe, une passe de comparaison :

```
python3 epub_reference.py relu.epub reference.pdf --from-page 118 \
        --apply ocr,esperluette,apostrophes,casse,graphie,variante \
        --keep "Ptolémée,Européens" -o relu2.epub --report ecarts.html
```

(la catégorie `variante` et les choix de graphie d'une édition moderne n'ont leur place que dans une
édition destinée à un usage personnel ou autorisée par son éditeur).

### 6. Ce qu'il faut adapter d'un livre à l'autre

| Réglage | Où | Quand |
|---|---|---|
| Titres de chapitre | `--chapter-regex`, `--book-regex`, `--title-before`, `--date-titles`, `--caps-titles` | numérotation ou mise en page inhabituelle ; journal daté |
| Page de titre | `epub_gutenberg.py --title-file NOM` | le fichier de la page de titre ne commence pas par « titre » |
| Dictionnaires | `dictionnaires/*.py` | mots récurrents du livre (ils servent ensuite aux suivants) |
| Mots à ne pas toucher | `epub_reference.py --keep` ; décocher dans les onglets | noms propres, graphies voulues |
| Listes TSV | `<livre>-s-long.tsv`, `-oi.tsv`… dans le dossier du projet | à garder : vos choix sont repris à chaque relance |
| Catégories du rapport | `epub_review.py --sans` | catégories déjà traitées |

### 7. Avant de publier

- [ ] epubcheck : 0 erreur (`epub_pages.py` répare liens, id en double, liste des pages) ;
- [ ] plus aucun marqueur `a-verifier` (`epub_review.py --unmark`) ;
- [ ] table des matières complète (titre + sommaire de chaque chapitre) ;
- [ ] page de titre et date conformes au scan ;
- [ ] note de transcription : corrections faites, notes renumérotées, modernisation éventuelle ;
- [ ] pour Gutenberg : droits validés sur https://copy.pglaf.org, `.html` sans erreur sur
      https://validator.w3.org/, `.txt` à 72 caractères par ligne, puis dépôt sur
      https://upload.pglaf.org.


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
   marqueurs sont retirés d'abord, le fichier de départ est archivé dans `archives/`. Décocher
   alors « Corriger d'après une autre édition » : elle pourrait défaire des corrections de relecture
   (errata, recollage, guillemets et typographie peuvent être rejoués sans risque).
6. **Retirer les marqueurs** quand la relecture est finie : le fichier `…-relu.epub` est prêt,
   contrôlé par epubcheck.

## Les scripts

Chaque script s'utilise aussi seul (`python3 script.py --help`).

| Script | Rôle |
|---|---|
| `pdf_to_epub.py` | PDF → EPUB brut : OCR de Gallica (ALTO), couche texte du PDF ou OCR Tesseract ; géométrie des pages |
| `pdf_vers.py` | EPUB d'un poème numéroté vers par vers (couche texte d'un PDF) : une ligne imprimée = un vers, numéros de vers en marge recomptés, manchettes (folios, dates), notes de bas de page mises à part |
| `pdf_glossaire.py` | glossaire ou vocabulaire sur deux colonnes en retrait suspendu → un paragraphe par article, vedette en gras |
| `epub_abimes.py` | mots illisibles de l'OCR (« d~pen~sHce », souvent l'italique) réparés d'après une autre numérisation, par leur contexte |
| `epub_errata_vers.py` | errata d'un poème numéroté : chaque correction vise un vers par son numéro (leçons « lis. », virgule ou point-virgule en fin de vers, ponctuation à supprimer) ; une liste sert à tous les tomes |
| `pdf_tesseract.py` | OCR Tesseract d'un PDF d'images, page par page (reprise possible) : seconde lecture pour `epub_reference.py --confirm` |
| `epub_inline2css.py` | styles en ligne → classes (facultatif) |
| `epub_simplify.py` | nettoyage du balisage OCR, lettrines, DOCTYPE XHTML 1.1 ; texte vérifié avant/après |
| `epub_longs.py` | s long lu « f » (« eft » → « est ») |
| `epub_modernise.py` | imparfaits en « oi » (`--mode oi`), pluriels en « ez » (`--mode ez`), passé simple en « erent » (`--mode erent`), pluriels en « ans » (`--mode ants`), vocabulaire (`--mode vocab`), orthographe du moyen français par règles (`--mode graphie`) ; `--epoque 17-18|moyen` choisit les dictionnaires |
| `epub_reference.py` | corrige l'EPUB d'après une autre édition du texte (PDF, EPUB ou texte), confirmée au besoin par une seconde lecture (`--confirm`) : alignement mot à mot, catégories au choix, rapport d'écarts |
| `epub_structure.py` | livres, chapitres, titres en capitales, dates d'un journal, sommaires, notes reliées, avertissement Google retiré, table des matières, liste des pages |
| `epub_errata.py` | applique l'errata imprimé du livre (« P. 24, l. 30, sont — font ») à la page indiquée ; liste à relire dans `<livre>-errata.tsv` |
| `epub_recolle.py` | recolle les mots coupés d'une espace (« Portin gal », « autre ment ») quand le mot entier est ailleurs dans le livre ; liste dans `<livre>-recolle.tsv` |
| `epub_guillemets.py` | guillemets que l'OCR a lus « u » (« ) et « n » (») ; guillemets répétés en tête de ligne supprimés |
| `epub_apparat.py` | numéros d'appel de l'apparat de variantes lus « U », déduits des numéros voisins |
| `epub_typo.py` | typographie française de la ponctuation (insécables, espaces, « — », « … ») ; seules les espaces changent |
| `epub_split_h1.py` | un fichier par livre / chapitre |
| `epub_review.py` | rapport de relecture, copie surlignée, dictionnaire pour Sigil ; `--unmark`, `--fix-doctype`, `--sans` |
| `epub_gutenberg.py` | fichiers à déposer chez Project Gutenberg : texte UTF-8 (72 caractères par ligne) et HTML5 valide |
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
| `ponctuation` | « de Poithou d'Angou » → « de Poithou, d'Angou » (signe absent de l'EPUB ; même édition seulement) | non |
| `guillemets` | « … belle. Non obstant » → « … belle. » Non obstant » (fermant lu par la référence et par `--confirm`) | non |

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

## Publier sur Project Gutenberg

Project Gutenberg demande deux fichiers « maîtres » : un texte brut UTF-8 et un HTML5 qui passe le
validateur du W3C (https://validator.w3.org/). Il ajoute lui-même son en-tête et sa licence.

```
python3 epub_gutenberg.py livre-relu.epub -o Mon_livre      # → Mon_livre.txt, Mon_livre.html
```

- texte : lignes de 72 caractères au plus, fins de ligne CRLF, paragraphes séparés par une ligne
  vide, quatre lignes vides avant chaque chapitre et deux après, italique en `_soulignés_`,
  notes `[1]` en fin de chapitre ;
- HTML : une seule page, CSS intégrée, notes reliées dans les deux sens, aucun script ;
- `--title-file NOM` désigne la page de titre de l'EPUB (défaut « titre ») ; `--apostrophes auto`
  garde une seule forme d'apostrophe (la plus fréquente) ; `--esperluette` remplace les « & » restants
  par « et » quand le reste du livre l'écrit ainsi ;
- marqueurs de relecture et classes de Prescel disparaissent ; les notes sont renumérotées de 1 à
  N ; une note de transcription l'indique (`--note` pour en ajouter) ;
- édition à variantes (`<p class="variantes">`) : les variantes sont regroupées en fin de volume,
  page par page, et les numéros de page du livre restent (`{12}` dans le texte, en marge du HTML
  avec un lien vers les variantes) ; `--folios oui|non` pour forcer ;
- tableaux (table des matières imprimée) : rendus en tableau HTML, avec des points de conduite
  dans le texte ; une page de table renvoie aux numéros de page ;
- errata appliqué par `epub_errata.py` : signalé dans la note de transcription.

Avant l'envoi : faire vérifier les droits (scans de la page de titre et de son verso) sur
https://copy.pglaf.org, puis déposer les fichiers sur https://upload.pglaf.org.

## Typographie française

`typo_fr.py` applique les règles d'espacement françaises ; `epub_typo.py` les applique à un EPUB,
et `epub_gutenberg.py` aux fichiers pour Project Gutenberg (sauf `--no-typo`, et seulement pour
un livre en français) :

| Signe | Avant | Après |
|---|---|---|
| `. , … ) ]` | aucune espace | une espace si un mot suit |
| `; : ! ?` | espace insécable | une espace si un mot suit |
| `«` | — | espace insécable |
| `»` | espace insécable | une espace si un mot suit |
| `( [` | — | aucune espace |
| `...` | devient `…` | |
| ` - ` entre deux espaces, `-` en tête de paragraphe | devient le tiret `—` | une espace |
| `—` collé (« France.— 1-2 ») | une espace | une espace |

Les règles passent par-dessus l'italique (« _mea culpa_ ; »), ne touchent pas aux nombres
(« 10:30 », « 1,5 ») et sont vérifiées : seules les espaces, `...` et le tiret changent.

## Licence

Prescel est distribué sous licence MIT (fichier `LICENSE`).

Outils et données utilisés, qui ont leur propre licence :
- PyMuPDF (import PDF, facultatif) : AGPL-3.0 ou licence commerciale d'Artifex ;
- Tesseract (OCR, facultatif) : Apache 2.0 ;
- epubcheck (contrôle, facultatif) : BSD-3-Clause ;
- liste de mots « an-array-of-french-words » (téléchargée par `--wordlist auto`) : MIT ;
- OCR et images de Gallica : conditions de réutilisation de la BnF (usage non commercial libre).
