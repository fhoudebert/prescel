# Prescel

Préparer un livre numérisé (EPUB issu d'OCR : Google Livres, Gallica…) avant sa relecture dans Sigil.

## Lancement

```
python3 prescel.py --epubcheck /opt/epubcheck/epubcheck-5.4.0/epubcheck.jar
```

S'ouvre dans le navigateur (http://127.0.0.1:8765). Aucune dépendance : Python 3.8+.
Options : `--workdir` (projets, défaut `~/Prescel`), `--sigil CHEMIN`, `--port`, `--no-browser`.
Variables équivalentes : `PRESCEL_EPUBCHECK`, `PRESCEL_SIGIL`.

## Étapes

| Script | Rôle |
|---|---|
| `pdf_to_epub.py` | PDF → EPUB brut : OCR de Gallica (ALTO), couche texte du PDF ou OCR Tesseract ; géométrie des pages |
| `epub_inline2css.py` | styles en ligne → classes (facultatif) |
| `epub_simplify.py` | nettoyage du balisage OCR, lettrines, DOCTYPE XHTML 1.1 ; texte vérifié avant/après |
| `epub_longs.py` | s long lu « f » (« eft » → « est ») : corrections sûres appliquées, liste TSV modifiable |
| `epub_structure.py` | livres, chapitres, titres en capitales, sommaires, notes, avertissement Google retiré, table des matières, liste des pages |
| `epub_modernise.py` | modernisation : imparfaits et conditionnels en « oi » (`--mode oi`), pluriels en « ez » (`--mode ez`), vocabulaire ancien (`--mode vocab`) ; listes TSV modifiables |
| `epub_split_h1.py` | un fichier par livre / chapitre |
| `epub_pages.py` | liste des pages du livre papier rétablie depuis les ancres (`GBS.PA31`, `page-12`) après une retouche dans Sigil, ou `--purge` pour retirer ces ancres |
| `epub_review.py` | rapport de relecture, copie surlignée, dictionnaire pour Sigil ; `--unmark` |

Les réglages préconisés sont cochés par défaut, puis ajustés d'après l'analyse du livre déposé.

## Relance ciblée

Après des corrections dans Sigil, « Relance ciblée » rejoue les étapes 3 à 5 sur le fichier
enregistré (ou sur une version déposée) : les marqueurs de relecture sont retirés d'abord et le
fichier de départ est copié dans `archives/`.

## S long

Dans les imprimés anciens, l'OCR lit le s long (ſ) comme un « f ». `epub_longs.py` se sert du
livre comme dictionnaire : une correction n'est faite que si la forme en « s » existe ailleurs dans
le livre. Les mots qui existent sous les deux formes (« font »/« sont », « fait »/« sait ») sont
laissés au choix : l'onglet « S long » de Prescel permet de les cocher, et le rapport de relecture
en signale chaque occurrence avec le lien vers la page scannée.

## PDF

`pdf_to_epub.py` (étape « Import du PDF » de Prescel) demande PyMuPDF : `pip install pymupdf`.
Pour un PDF de Gallica dont le nom contient l'identifiant (`bpt6k…`, `btv1b…`), l'OCR de la BnF est
récupéré en ALTO (la couche texte des PDF Gallica colle les mots) avec la pagination imprimée ; les
pages de reliure sont ignorées. Sans OCR disponible, Tesseract est utilisé
(`apt install tesseract-ocr tesseract-ocr-fra` ; modèle `frm` pour le moyen français, qui lit le ſ).
La position des lignes sert à retirer titres courants, folios, signatures et réclames, à placer les
manchettes, à recoller césures, lettrines et paragraphes coupés par les pages.

## Tableaux et listes

- Import PDF : les lignes coupées en colonnes par de grands blancs, alignées sur au moins trois
  lignes, deviennent un tableau (`<table class="tableau">`) ; les lignes qui commencent par une
  marque (« 1. », « a) », « — ») au même retrait deviennent une liste (`<ol class="liste">`),
  la marque d'origine restant dans le texte.
- EPUB de Google : les lignes de table des matières imprimée et les entrées d'index que Google
  a repérées deviennent des listes (`<ul class="table-imprimee">`, `<ul class="index">`).

## Licence

Prescel est distribué sous licence MIT (fichier `LICENSE`).

Outils et données utilisés, qui ont leur propre licence :
- PyMuPDF (import PDF, facultatif) : AGPL-3.0 ou licence commerciale d'Artifex ;
- Tesseract (OCR, facultatif) : Apache 2.0 ;
- epubcheck (contrôle, facultatif) : BSD-3-Clause ;
- liste de mots « an-array-of-french-words » (téléchargée par `epub_longs.py --wordlist auto`) : MIT ;
- OCR et images de Gallica : conditions de réutilisation de la BnF (usage non commercial libre).

## Numéros de page et Sigil

Les ancres vides comme `<a id="GBS.PA31"></a>` marquent le début de chaque page du livre papier ;
elles alimentent la liste des pages du `toc.ncx` (« page 31 » sur la liseuse). Quand Sigil régénère
la table des matières, cette liste disparaît et les ancres semblent mortes. `epub_structure.py`
(donc la relance ciblée de Prescel) la refait d'elle-même ; hors de Prescel :

```
python3 epub_pages.py livre-relu.epub -o livre-pages.epub           # rétablir / réparer la liste des pages
python3 epub_pages.py livre-relu.epub -o livre-sans-pages.epub --purge  # ou retirer les ancres
```

## DOCTYPE (EPUB 2)

Google Livres écrit ses pages en XHTML 1.0 Strict, qu'epubcheck refuse dans un EPUB 2
(`HTM-004`). Toutes les étapes qui réécrivent les pages (nettoyage, s long, structure, relecture)
mettent le DOCTYPE en XHTML 1.1. Pour corriger un fichier en cours de relecture sans toucher aux
marqueurs :

```
python3 epub_review.py livre-a-relire.epub --fix-doctype
```

## Modernisation (oi → ai, vocabulaire)

`epub_modernise.py`, sur le modèle du s long : les corrections sûres sont appliquées, les autres
laissées au choix dans une liste (onglets « oi → ai » et « Modernisation » de Prescel).

- `--mode oi` : « il estoit » → « il était », « ils auroient » → « ils auraient ». Le dictionnaire
  `dictionnaires/verbes_oi.py` donne la forme moderne complète ; ailleurs la règle -oi- → -ai- n'est
  appliquée que si le mot obtenu existe en français (« reconnoit » → « reconnaît »). Les mots où « oi »
  est juste (« trois », « droit », « soit ») ne sont pas touchés ; « François », « Anglois »
  (nom propre ou nationalité ?) restent au choix et sont signalés dans le rapport.
- `--mode ez` : « les bontez » → « les bontés », « ils sont armez » → « armés ». Chaque occurrence
  précédée de « vous » (« vous avez », « vous les envoyez »), en inversion (« allez-vous », « où allez
  vous ») ou à l'impératif en tête de phrase (« Venez ») est gardée ; « nez », « chez », « assez »
  ne sont jamais touchés. `dictionnaires/pluriels_ez.py` donne les formes qui ne suivent pas la règle
  (« excez » → « excès », « extremitez » → « extrémités »).
- `--mode vocab` : « luy » → « lui », « mesme » → « même », « aussi tost » → « aussitôt », d'après
  `dictionnaires/vocabulaire_17_18.py` ; les graphies qui sont aussi des mots modernes (« des » →
  « dès ») restent au choix. C'est un choix d'édition : l'étape n'est jamais cochée d'office.

Les deux dictionnaires sont de simples fichiers Python (`{"ancien": "moderne", …}`) : on peut les
compléter librement.

## Après des retouches dans Sigil

Couper un paragraphe en deux dans Sigil recopie son `id` (erreur epubcheck « Duplicate »), et
supprimer un passage peut emporter une ancre de page que le `toc.ncx` vise encore (« identificateur
de fragment non défini », playOrder identiques). `epub_pages.py` (et la relance ciblée de Prescel)
retire les id en double, sort de la liste des pages celles dont l'ancre a disparu, fait viser le
début du fichier aux entrées de table orphelines et renumérote les playOrder. Les marqueurs de
relecture sont conservés.

## Relance après les listes de corrections

Une fois les mots laissés au choix du s long et des imparfaits en « oi » tranchés, décochez ces
étapes : à la relance sur le fichier marqué, leurs mots ne sont plus signalés ni surlignés (seules
les listes des étapes cochées sont transmises au rapport). Le réglage avancé « Ne pas signaler » de
l'étape « Préparer la relecture » (option `--sans` d'`epub_review.py`) retire de même les autres
catégories déjà traitées.
