#!/bin/sh
# T. III de L'Histoire de Guillaume le Maréchal (éd. Paul Meyer, 1901) : introduction, chronologie,
# additions, traduction abrégée, table. À lancer depuis la racine de Prescel :
#   sh livres/guillaume-marechal-t3.sh [dossier de travail]
# Base : le DjVu (exemplaire de Harvard, couche texte de Google), complet et le mieux lu, dans l'ordre de
# l'imprimé. Seconde source : le XML ABBYY d'Internet Archive (exemplaire de Toronto, sans les pages
# cxxii-cxli), qui apporte l'italique et des appels de note, puis sa lecture brute (djvu.txt) pour les
# mots que le DjVu a mal lus.
set -e
P=$(pwd); W=${1:-travail-guillaume-t3}; mkdir -p "$W"
DJ=$(ls "$P"/pdf/*tome_3.djvu | head -1)
X="$P/pdf/lhistoiredeguill03meyeuoft_abbyy.gz"
T="$P/pdf/lhistoiredeguill03meyeuoft_djvu.txt"
IA=https://archive.org/download/lhistoiredeguill03meyeuoft
[ -f "$X" ] || curl -sSL -o "$X" $IA/lhistoiredeguill03meyeuoft_abbyy.gz
[ -f "$T" ] || curl -sSL -o "$T" $IA/lhistoiredeguill03meyeuoft_djvu.txt
cd "$W"
TITRE="L'Histoire de Guillaume le Maréchal, tome III"
python3 "$P/abbyy_to_epub.py" "$DJ" -o t3-djvu.epub --titre "$TITRE" --auteur "Paul Meyer" \
    --pagination 12=i,172=1 \
    --parties "8-10:Titre:sans-notes,12-155:Introduction,156-167:Chronologie et itinéraire:tableau,168-171:Additions et corrections:index,172-440:Traduction abrégée,442-475:Table:index"
python3 "$P/abbyy_to_epub.py" "$X" -o t3-abbyy.epub --titre "$TITRE" --auteur "Paul Meyer" \
    --pagination 16=1,286=271,320=i,441=cxlii \
    --parties "12-14:Titre:sans-notes,320-443:Introduction,444-455:Chronologie et itinéraire,456-459:Additions et corrections,16-284:Traduction abrégée,286-319:Table:index" > abbyy.log
python3 "$P/epub_fusion.py" t3-djvu.epub t3-abbyy.epub -o t3-1.epub --report t3-fusion.tsv
python3 "$P/epub_reference.py" t3-1.epub "$T" --prudent --apply ocr -o t3-2.epub --report t3-ecarts.html
python3 "$P/epub_ocr_prose.py" t3-2.epub -o t3-3.epub --report t3-prose.tsv
python3 "$P/epub_typo.py" t3-3.epub -o t3-4.epub
python3 "$P/livres/guillaume-marechal-t3-reprises.py" t3-4.epub Guillaume_le_Marechal_T3.epub
python3 "$P/epub_review.py" Guillaume_le_Marechal_T3.epub --report guillaume-t3-relecture.html --mark Guillaume_le_Marechal_T3-a-relire.epub
echo "Fini : $W/Guillaume_le_Marechal_T3-a-relire.epub"
