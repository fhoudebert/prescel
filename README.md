# Prescel

Préparer un livre numérisé — EPUB issu d'OCR (Google Livres, Gallica, Internet Archive…) ou PDF —
avant sa relecture dans [Sigil](https://sigil-ebook.com/), puis le publier : EPUB relu, ou texte et
HTML pour [Project Gutenberg](https://www.gutenberg.org/).

Prescel enchaîne des scripts Python indépendants, depuis une interface web locale ou en ligne de
commande : import, nettoyage, corrections propres aux imprimés anciens, structure du livre,
rapport de relecture et copie surlignée pour Sigil, fichiers de publication. Aucun mot n'est
changé sans être listé : chaque étape vérifie le texte avant et après, et les corrections
douteuses restent au choix, dans des listes que l'on coche ou des marques `a-verifier` que l'on
parcourt dans Sigil.

**Pour s'en servir vraiment : [guide d'utilisation](utilisation.md)** (chaînes complètes,
réglages, scripts un par un, pièges connus).

## Vue d'ensemble

```
source (EPUB Google, PDF Gallica, PDF / XML d'Internet Archive, PDF de traitement de texte)
  → import            pdf_to_epub.py, abbyy_to_epub.py, pdf_vers.py, epub_simplify.py
  → corrections       s long, recollage, guillemets, errata, autre numérisation (vote, veto)
  → structure         titres, notes reliées, table des matières, numéros de page, découpage
  → relecture         rapport + copie surlignée à ouvrir dans Sigil
  → publication       EPUB relu (epubcheck) ou fichiers Gutenberg (texte + HTML5)
```

| Parcours | Pour | Dans le guide |
|---|---|---|
| A — Google Livres | EPUB de Google → EPUB relu → Gutenberg | [Parcours A](utilisation.md#3-parcours-a--google-livres--epub-relu--gutenberg) |
| B — Gallica | PDF Gallica (OCR de la BnF) → EPUB relu → Gutenberg | [Parcours B](utilisation.md#4-parcours-b--gallica-pdf--epub-relu--gutenberg) |
| Édition savante | apparat de variantes, errata, plusieurs numérisations (Froissart) | [Édition savante](utilisation.md#édition-savante-en-plusieurs-volumes-variantes-errata-plusieurs-numérisations) |
| Poème numéroté | vers par vers, numéros en marge, notes (Guillaume le Maréchal) | [Poème](utilisation.md#poème-édité-vers-par-vers-guillaume-le-maréchal-éd-paul-meyer) |
| Prose d'Internet Archive | XML ABBYY ou DjVu, trois lectures confrontées | [Prose savante](utilisation.md#prose-savante-depuis-internet-archive-t-iii-de-guillaume-le-maréchal) |
| PDF de traitement de texte | transcription déjà saisie, sans OCR (Foulques-Nerra) | [PDF de traitement de texte](utilisation.md#pdf-issu-dun-traitement-de-texte-histoire-de-foulques-nerra) |
| C — édition modernisée | orthographe modernisée (XVIIᵉ-XVIIIᵉ, moyen et ancien français) | [Parcours C](utilisation.md#5-parcours-c--édition-modernisée-usage-personnel-autre-plateforme) |

La cible se choisit **avant** de corriger : Project Gutenberg veut le texte fidèle à une édition
du domaine public (pas de modernisation, pas de reprise d'une édition moderne protégée) ; une
édition personnelle peut être modernisée si elle l'annonce. Voir
[Choisir la cible](utilisation.md#1-choisir-la-cible-avant-de-corriger).

## Démarrage rapide

Python 3.8+ ; facultatif : `pip install pymupdf` (PDF), Tesseract (OCR), epubcheck (contrôle),
Sigil (relecture).

```
python3 prescel.py --epubcheck /opt/epubcheck/epubcheck-5.4.0/epubcheck.jar
```

La page s'ouvre dans le navigateur (http://127.0.0.1:8765) : déposer un EPUB ou un PDF, Prescel
coche les étapes adaptées, « Préparer le livre », trancher les listes, relire dans Sigil la
version « à relire », retirer les marqueurs. En ligne de commande, chaque script s'utilise seul
(`python3 script.py --help`), par exemple pour un EPUB de Google Livres :

```
python3 epub_simplify.py  google.epub -o 1.epub --join-hyphens --flatten-br --lettrines
python3 epub_longs.py     1.epub -o 2.epub --tsv livre-s-long.tsv --wordlist auto
python3 epub_structure.py 2.epub -o 3.epub --merge-pages --drop-furniture --caps-titles --link-notes
python3 epub_review.py    3.epub --report relecture.html --mark a-relire.epub
# relecture dans Sigil (rechercher « a-verifier »), puis
python3 epub_review.py a-relire.epub --unmark -o relu.epub
python3 epub_gutenberg.py relu.epub -o Mon_livre
```

## Contenu du dépôt

| Dossier ou fichier | Contenu |
|---|---|
| `prescel.py` | interface web locale |
| `pdf_*.py`, `abbyy_to_epub.py` | import (PDF Gallica, couche texte, OCR Tesseract, XML ABBYY, DjVu, poèmes, glossaires) |
| `epub_*.py` | une étape chacun : nettoyage, corrections, structure, relecture, publication ([liste](utilisation.md#les-scripts)) |
| `typo_fr.py` | typographie française (espaces, tirets, points de suspension) |
| `dictionnaires/` | listes de corrections et de modernisation, à compléter ([détails](utilisation.md#dictionnaires)) |
| `livres/` | scripts et listes propres à un livre (Froissart, Guillaume le Maréchal, Foulques-Nerra), modèles pour un livre du même genre |
| `epub/` | livres produits (EPUB, fichiers Gutenberg) |
| `utilisation.md` | guide d'utilisation détaillé |

## Licence

Prescel est distribué sous licence MIT (fichier `LICENSE`).

Outils et données utilisés, qui ont leur propre licence :
- PyMuPDF (import PDF, facultatif) : AGPL-3.0 ou licence commerciale d'Artifex ;
- Tesseract (OCR, facultatif) : Apache 2.0 ;
- epubcheck (contrôle, facultatif) : BSD-3-Clause ;
- liste de mots « an-array-of-french-words » (téléchargée par `--wordlist auto`) : MIT ;
- OCR et images de Gallica : conditions de réutilisation de la BnF (usage non commercial libre).
