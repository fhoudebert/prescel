#!/bin/sh
# T. III de Guillaume le Maréchal : du maître relu (epub/Guillaume_le_Marechal_T3-a-relire.epub) aux fichiers
# Gutenberg. Marques de relecture retirées, finitions (corrections de la relecture reportées sur les autres
# occurrences, mots coupés, guillemets répétés en tête de ligne, table recollée), puis TXT (CRLF) et HTML.
#   sh livres/guillaume-marechal-t3-gutenberg.sh [dossier de travail]
set -e
P=$(pwd); W=${1:-travail-guillaume-t3}; mkdir -p "$W"
cd "$W"
python3 "$P/epub_review.py" "$P/epub/Guillaume_le_Marechal_T3-a-relire.epub" --unmark -o t3-0.epub
python3 "$P/livres/guillaume-marechal-t3-finitions.py" t3-0.epub Guillaume_le_Marechal_T3.epub
python3 "$P/epub_review.py" Guillaume_le_Marechal_T3.epub --report t3-controle.html
python3 "$P/epub_gutenberg.py" Guillaume_le_Marechal_T3.epub -o Guillaume_le_Marechal_T3
echo "Fini : $W/Guillaume_le_Marechal_T3.epub, .txt, .html (contrôle : $W/t3-controle.html)"
