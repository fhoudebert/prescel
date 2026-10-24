#!/bin/sh
# Orthographe modernisée d'un tome des Chroniques de Froissart (éd. Kervyn) : chaîne « Moderniser
# l'orthographe d'un texte en moyen français » de utilisation.md (vocabulaire, noms propres, -oi-,
# graphies, -erent, -ans, vocabulaire), puis titre et note de la page de titre.
#   sh livres/froissart-moderne.sh 13 [EPUB relu] [dossier de travail]
# défaut : epub/Oeuvres_de_Froissart_Chroniques_Tome_13-relu.epub
# → epub/Oeuvres_de_Froissart_Chroniques_Tome_13-moderne.epub (listes des remplacements dans le dossier de travail)
# Ensuite : sh livres/froissart-lisible.sh 13
set -e
T=${1:?numéro du tome}; P=$(pwd)
SRC=${2:-"$P/epub/Oeuvres_de_Froissart_Chroniques_Tome_$T-relu.epub"}
W=${3:-travail-moderne-$T}; mkdir -p "$W"
OUT="$P/epub/Oeuvres_de_Froissart_Chroniques_Tome_$T-moderne.epub"
M="python3 $P/scripts/epub_modernise.py"
$M "$SRC"     -o "$W/1.epub" --epoque moyen --mode vocab   --tsv "$W/livre-moderne.tsv"  --wordlist auto
$M "$W/1.epub" -o "$W/2.epub" --epoque moyen --mode vocab   --tsv "$W/livre-noms.tsv"     --wordlist auto \
   --dict "$P/dictionnaires/noms_froissart.py"
$M "$W/2.epub" -o "$W/3.epub" --epoque moyen --mode oi      --tsv "$W/livre-oi.tsv"       --wordlist auto
$M "$W/3.epub" -o "$W/4.epub" --epoque moyen --mode graphie --tsv "$W/livre-graphie.tsv"  --wordlist auto
$M "$W/4.epub" -o "$W/5.epub" --epoque moyen --mode erent   --tsv "$W/livre-erent.tsv"    --wordlist auto
$M "$W/5.epub" -o "$W/6.epub" --epoque moyen --mode ants    --tsv "$W/livre-ants.tsv"     --wordlist auto
$M "$W/6.epub" -o "$W/7.epub" --epoque moyen --mode vocab   --tsv "$W/livre-moderne2.tsv" --wordlist auto
# titre « — orthographe modernisée » et note à la fin de la page de titre
python3 - "$W/7.epub" "$OUT" <<'PY'
import sys, zipfile
src, out = sys.argv[1:]
NOTE = ('  <p class="centre"><i>Orthographe modernisée</i> : graphies, formes verbales et noms propres sont '
        "ramenés à l'usage moderne ; le vocabulaire et la syntaxe sont ceux de Froissart.</p>\n")
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
    for info in sorted(zin.infolist(), key=lambda i: i.filename != "mimetype"):
        data = zin.read(info)
        if info.filename.endswith(".opf"):
            t = data.decode("utf-8")
            if "orthographe modernisée" not in t:
                t = t.replace("</dc:title>", " — orthographe modernisée</dc:title>", 1)
            data = t.encode("utf-8")
        elif info.filename.endswith("titre.xhtml"):
            t = data.decode("utf-8")
            if "<i>Orthographe modernisée</i>" not in t:
                t = t.replace("</body>", NOTE + "</body>", 1)
            data = t.encode("utf-8")
        zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
PY
echo "Fini : $OUT (listes des remplacements : $W/livre-*.tsv)"
