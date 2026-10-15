# Sources des livres

D'où viennent les PDF, textes d'OCR et EPUB de comparaison utilisés par Prescel, pour pouvoir les
retélécharger. Les scripts de `livres/` cherchent les PDF de ce dossier d'après une partie de leur nom
(`ls pdf/*google-t1.pdf`) : garder ces noms en les retéléchargeant.

Gallica : bouton « Télécharger », document entier. Google Livres : « Télécharger le PDF » (ou l'EPUB),
proposé pour les livres du domaine public. Internet Archive : page « details », rubrique « Download
options ».

## Froissart, Œuvres, éd. Kervyn de Lettenhove (Bruxelles, 1870-1877), Chroniques

| Tome | Rôle | Source | Fichier |
|---|---|---|---|
| XII (1386-1389), 1871 | texte de base (ALTO) | Gallica [bpt6k38933z](https://gallica.bnf.fr/ark:/12148/bpt6k38933z) | — (téléchargé par `pdf_to_epub.py`) |
| XII | seconde numérisation : comparaison, contrôle sur l'image | Google Livres [JZENAAAAQAAJ](https://books.google.com/books?id=JZENAAAAQAAJ) | `Oeuvres_de_Froissart_1386_1389_Depuis_le.pdf` (retiré du dépôt) |
| XII | autre édition (Buchon, 1835), comparaison livre III, ch. XLIV à XC | [Wikisource](https://fr.wikisource.org/wiki/Les_Chroniques_de_Sire_Jean_Froissart/Livre_III) | — (décisions : `livres/froissart-t12-buchon.tsv`) |
| XIII (1386-1389) | texte de base | Gallica [bpt6k389349](https://gallica.bnf.fr/ark:/12148/bpt6k389349) | — |
| XIII | seconde numérisation | Google Livres [ZFFXAAAAcAAJ](https://books.google.com/books?id=ZFFXAAAAcAAJ) | `epub/Oeuvres_de_Froissart-13.epub` |
| XIII | troisième lecture (Tesseract, `pdf_tesseract.py`) | Internet Archive [oeuvresdefroiss02belggoog](https://archive.org/details/oeuvresdefroiss02belggoog) | `oeuvresdefroiss02belggoog-tesseract.txt` |
| XIV (1389-1392) | texte de base | Gallica [bpt6k38935n](https://gallica.bnf.fr/ark:/12148/bpt6k38935n) | — |
| XIV | seconde numérisation | Google Livres [95OiiHRqQ9wC](https://books.google.com/books?id=95OiiHRqQ9wC) | `froissart-95OiiHRqQ9wC-14.pdf` |
| XIV | troisième lecture (Tesseract) | Internet Archive [oeuvresdefroiss02beligoog](https://archive.org/details/oeuvresdefroiss02beligoog) | `oeuvresdefroiss02beligoog-14-tesseract.txt` |

Les pages de titre envoyées à copy.pglaf.org pour la vérification des droits sont dans `epub/`
(`t12-titre.png`, `t13-titre.png`, `t14-titre.png`).

## L'Histoire de Guillaume le Maréchal, éd. Paul Meyer (Société de l'Histoire de France, 1891-1901)

| Tome | Rôle | Source | Fichier |
|---|---|---|---|
| I | texte de base | Internet Archive [lhistoiredeguill01meyeuoft](https://archive.org/details/lhistoiredeguill01meyeuoft) | `lhistoiredeguill01meyeuoft.pdf` |
| I | seconde lecture (Tesseract) | Gallica [bpt6k203426d](https://gallica.bnf.fr/ark:/12148/bpt6k203426d) | `bpt6k203426d-tesseract.txt` |
| I | troisième lecture, folios | Google Livres [5aYUAAAAQAAJ](https://books.google.com/books?id=5aYUAAAAQAAJ) | `L_histoire_de_Guillaume_le_Maréchal_google-t1.pdf` |
| II | texte de base (OCR Gallica) | Gallica [bpt6k203427s](https://gallica.bnf.fr/ark:/12148/bpt6k203427s) | `L'histoire_de_Guillaume_le_Maréchal_[...]_bpt6k203427s.pdf` |
| II | seconde lecture, folios | Google Livres [e-tU0gEACAAJ](https://books.google.com/books?id=e-tU0gEACAAJ) | `L_histoire_de_Guillaume_le_Maréchal_t2-google.pdf` |
| II | troisième lecture | Internet Archive [lhistoiredeguill02meyeuoft](https://archive.org/details/lhistoiredeguill02meyeuoft) | téléchargé par `livres/guillaume-marechal-t2-gutenberg.sh` |
| III | texte de base (DjVu, exemplaire de Harvard) | — | `*tome_3.djvu` (non suivi par git) |
| III | seconde lecture (XML ABBYY) | Internet Archive [lhistoiredeguill03meyeuoft](https://archive.org/details/lhistoiredeguill03meyeuoft) | téléchargé par `livres/guillaume-marechal-t3.sh` |

## Autres livres

| Livre | Source | Fichier |
|---|---|---|
| Alexandre de Salies, *Histoire de Foulques-Nerra* (1874) | transcription saisie au traitement de texte (OpenOffice, 2006) | `foulquesNerra.pdf` |
| *Commentaires de Montluc* (Hachette, 1872) | Google Livres [ATFNAQAAMAAJ](https://books.google.com/books?id=ATFNAQAAMAAJ) | `epub/Commentaires_de_Montluc.epub` |
| Jean Chardin, *Voyages en Perse* (1711) | Google Livres [BwgPAAAAQAAJ](https://books.google.com/books?id=BwgPAAAAQAAJ) | `epub/Jean-Chardin-Voyages_en_Perse-relu.epub` |
