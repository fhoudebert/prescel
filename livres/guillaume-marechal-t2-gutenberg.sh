#!/bin/sh
# T. II de Guillaume le Maréchal : du maître relu (epub/Guillaume_le_Marechal_T2-a-relire.epub) aux fichiers
# Gutenberg, comme pour le t. I. Marques de relecture retirées, folios replacés d'après le PDF Google, vote
# des deux autres lectures (ABBYY d'Internet Archive, Google), règles OCR ; reprises vérifiées sur le PDF
# Google (vers perdus ou passés dans les notes, numéros de vers) avant les folios.
#   sh livres/guillaume-marechal-t2-gutenberg.sh [dossier de travail]
set -e
P=$(pwd); W=${1:-travail-guillaume-t2}; mkdir -p "$W"
GT2=$(ls "$P"/pdf/*t2-google.pdf | head -1)
IA2="$P/pdf/lhistoiredeguill02meyeuoft_djvu.txt"
[ -f "$IA2" ] || curl -sSL -o "$IA2" https://archive.org/download/lhistoiredeguill02meyeuoft/lhistoiredeguill02meyeuoft_djvu.txt
T1="$P/epub/Guillaume_le_Marechal_T1-a-relire.epub"
cd "$W"
python3 "$P/epub_review.py" "$P/epub/Guillaume_le_Marechal_T2-a-relire.epub" --unmark -o t2-0.epub
python3 "$P/livres/guillaume-marechal-t2-reprises.py" t2-0.epub t2-r.epub "$GT2"
python3 "$P/epub_folios.py" t2-r.epub "$GT2" -o t2-a.epub --report t2-folios.tsv
python3 "$P/epub_vers_reference.py" t2-a.epub "$IA2" --ref2 "$GT2" --vote-seul --accents-ref2 -o t2-b.epub --vocab "$T1" --report t2-votes.tsv
python3 "$P/epub_abimes.py" t2-b.epub "$GT2" -o t2-c.epub
python3 "$P/epub_ocr_vers.py" t2-c.epub -o Guillaume_le_Marechal_T2.epub --sans l-lu --vocab "$T1" --report t2-ocr.tsv
python3 "$P/epub_gutenberg.py" Guillaume_le_Marechal_T2.epub -o Guillaume_le_Marechal_T2
echo "Fini : $W/Guillaume_le_Marechal_T2.txt, $W/Guillaume_le_Marechal_T2.html"
