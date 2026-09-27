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
| `epub_split_h1.py` | un fichier par livre / chapitre |
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
