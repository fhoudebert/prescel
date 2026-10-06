#!/bin/sh
# Reconstruit les deux tomes de L'Histoire de Guillaume le Maréchal (éd. Paul Meyer) depuis les
# sources du dépôt, jusqu'aux EPUB à relire. À lancer depuis la racine de Prescel :
#   sh livres/guillaume-marechal.sh [dossier de travail]
# Sources : pdf/lhistoiredeguill01meyeuoft.pdf (t. I, Internet Archive), pdf/bpt6k203426d-tesseract.txt
# (seconde lecture du t. I, Gallica), pdf/…bpt6k203427s.pdf (t. II, Gallica, avec OCR),
# epub/lhistoirededegu00meyegoog.epub (t. II, Google).
set -e
P=$(pwd); W=${1:-travail-guillaume}; mkdir -p "$W"
T2PDF=$(ls "$P"/pdf/*bpt6k203427s*.pdf | head -1)
GOOG="$P/epub/lhistoirededegu00meyegoog.epub"
ERR="$P/livres/guillaume-marechal-errata.tsv"
cd "$W"
# --- tome I
python3 "$P/pdf_vers.py" "$P/pdf/lhistoiredeguill01meyeuoft.pdf" -o t1-1.epub --pages 1-383 > t1-vers.log
python3 "$P/livres/guillaume-marechal-t1-finitions.py" t1-1.epub t1-2.epub
python3 "$P/livres/guillaume-marechal-t1-errata.py" t1-2.epub t1-3.epub
python3 "$P/epub_reference.py" t1-3.epub "$P/pdf/bpt6k203426d-tesseract.txt" --prudent --apply ocr --wordlist "" -o t1-4.epub --report t1-ecarts.html
python3 "$P/epub_typo.py" t1-4.epub -o t1-5.epub
python3 "$P/epub_errata_vers.py" t1-5.epub -o Guillaume_le_Marechal_T1.epub --tsv "$ERR"
python3 "$P/epub_review.py" Guillaume_le_Marechal_T1.epub --ancien --report guillaume-t1-relecture.html --mark Guillaume_le_Marechal_T1-a-relire.epub
# --- tome II (vers 10153-19214, puis le vocabulaire)
ln -sf "$T2PDF" t2_bpt6k203427s.pdf
python3 "$P/pdf_vers.py" t2_bpt6k203427s.pdf -o t2-1.epub --premier-vers 10153 --debut 8 --pages 1-338 > t2-vers.log
python3 "$P/pdf_glossaire.py" t2_bpt6k203427s.pdf -o vocab.xhtml --pages 340-395 --premiere-vue 338
python3 "$P/livres/guillaume-marechal-t2-finitions.py" t2-1.epub t2-2.epub vocab.xhtml
python3 "$P/epub_reference.py" t2-2.epub "$GOOG" --prudent --apply ocr --wordlist "" -o t2-3.epub --report t2-ecarts.html
python3 "$P/epub_abimes.py" t2-3.epub "$GOOG" -o t2-4.epub --files vocabulaire
python3 "$P/epub_typo.py" t2-4.epub -o t2-5.epub
python3 "$P/epub_errata_vers.py" t2-5.epub -o Guillaume_le_Marechal_T2.epub --tsv "$ERR"
python3 "$P/epub_review.py" Guillaume_le_Marechal_T2.epub --ancien --report guillaume-t2-relecture.html --mark Guillaume_le_Marechal_T2-a-relire.epub
echo "Fini : $W/Guillaume_le_Marechal_T1-a-relire.epub, $W/Guillaume_le_Marechal_T2-a-relire.epub"
