#!/bin/sh
# T. III de L'Histoire de Guillaume le Maréchal (éd. Paul Meyer, 1901) : introduction, chronologie,
# additions, traduction abrégée, table — depuis le XML ABBYY d'Internet Archive (lhistoiredeguill03meyeuoft).
# À lancer depuis la racine de Prescel :   sh livres/guillaume-marechal-t3.sh [dossier de travail]
# NB : le scan d'Internet Archive n'a pas les pages cxxii à cxli de l'introduction (vue 441 = p. cxlii).
set -e
P=$(pwd); W=${1:-travail-guillaume-t3}; mkdir -p "$W"
X="$P/pdf/lhistoiredeguill03meyeuoft_abbyy.gz"
[ -f "$X" ] || curl -sSL -o "$X" https://archive.org/download/lhistoiredeguill03meyeuoft/lhistoiredeguill03meyeuoft_abbyy.gz
cd "$W"
python3 "$P/abbyy_to_epub.py" "$X" -o t3-1.epub --titre "L'Histoire de Guillaume le Maréchal, tome III" \
    --auteur "Paul Meyer" --source "https://archive.org/details/lhistoiredeguill03meyeuoft" \
    --pagination 16=1,286=271,320=i,441=cxlii \
    --parties "12-14:Titre:sans-notes,320-443:Introduction,444-455:Chronologie et itinéraire,456-459:Additions et corrections,16-284:Traduction abrégée,286-319:Table:index"
python3 "$P/epub_ocr_prose.py" t3-1.epub -o t3-2.epub --report t3-prose.tsv
python3 "$P/epub_typo.py" t3-2.epub -o Guillaume_le_Marechal_T3.epub
python3 "$P/epub_review.py" Guillaume_le_Marechal_T3.epub --report guillaume-t3-relecture.html --mark Guillaume_le_Marechal_T3-a-relire.epub
echo "Fini : $W/Guillaume_le_Marechal_T3-a-relire.epub"
