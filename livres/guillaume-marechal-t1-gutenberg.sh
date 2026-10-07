#!/bin/sh
# T. I de Guillaume le Maréchal : du maître relu (epub/Guillaume_le_Marechal_T1-a-relire.epub) aux fichiers
# Gutenberg. Marques de relecture retirées, folios replacés d'après le PDF Google, vote des deux autres
# lectures (Tesseract Gallica, Google), règles OCR, reprises vérifiées sur le PDF Google.
#   sh livres/guillaume-marechal-t1-gutenberg.sh [dossier de travail]
set -e
P=$(pwd); W=${1:-travail-guillaume-t1}; mkdir -p "$W"
GT1=$(ls "$P"/pdf/*google-t1.pdf | head -1)
T2="$P/epub/Guillaume_le_Marechal_T2-a-relire.epub"
cd "$W"
python3 "$P/epub_review.py" "$P/epub/Guillaume_le_Marechal_T1-a-relire.epub" --unmark -o t1-0.epub
python3 "$P/epub_folios.py" t1-0.epub "$GT1" -o t1-a.epub --report t1-folios.tsv
python3 "$P/epub_vers_reference.py" t1-a.epub "$P/pdf/bpt6k203426d-tesseract.txt" --ref2 "$GT1" --vote-seul --accents-ref2 -o t1-b.epub --vocab "$T2" --report t1-votes.tsv
python3 "$P/epub_ocr_vers.py" t1-b.epub -o t1-c.epub --sans l-lu --vocab "$T2" --report t1-ocr.tsv
python3 "$P/livres/guillaume-marechal-t1-reprises.py" t1-c.epub Guillaume_le_Marechal_T1.epub
python3 "$P/epub_gutenberg.py" Guillaume_le_Marechal_T1.epub -o Guillaume_le_Marechal_T1
echo "Fini : $W/Guillaume_le_Marechal_T1.txt, $W/Guillaume_le_Marechal_T1.html"
