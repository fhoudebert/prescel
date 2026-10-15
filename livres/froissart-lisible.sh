#!/bin/sh
# Lecture facilitée d'un tome des Chroniques de Froissart (éd. Kervyn) : à partir de l'EPUB à
# l'orthographe modernisée (chaîne « Moderniser l'orthographe d'un texte en moyen français » de
# utilisation.md), les mots disparus ou trompeurs sont remplacés par un synonyme moderne
# (dictionnaires/lisible_froissart.py), puis la passe de vocabulaire ordinaire (« cuida » → « pensa »,
# « grant » → grand / grande). Les NOTES de l'éditeur (titre-4) et ce qui suit ne sont pas touchées.
#   sh livres/froissart-lisible.sh 13 [dossier de travail]
# → epub/Oeuvres_de_Froissart_Chroniques_Tome_13-lisible.epub
set -e
T=${1:?numéro du tome}; P=$(pwd); W=${2:-travail-lisible-$T}; mkdir -p "$W"
SRC="$P/epub/Oeuvres_de_Froissart_Chroniques_Tome_$T-moderne.epub"
OUT="$P/epub/Oeuvres_de_Froissart_Chroniques_Tome_$T-lisible.epub"
python3 "$P/scripts/epub_modernise.py" "$SRC" -o "$W/1.epub" --epoque moyen --mode vocab \
        --dict "$P/dictionnaires/lisible_froissart.py" --jusqua titre-4 --tsv "$W/lisible.tsv" --wordlist auto
python3 "$P/scripts/epub_modernise.py" "$W/1.epub" -o "$W/2.epub" --epoque moyen --mode vocab \
        --jusqua titre-4 --tsv "$W/vocabulaire.tsv" --wordlist auto
# titre et note de la page de titre : « orthographe modernisée » → « lecture facilitée »
python3 - "$W/2.epub" "$OUT" <<'PY'
import sys, zipfile
src, out = sys.argv[1:]
NOTE = ("<i>Lecture facilitée</i> : orthographe modernisée (graphies, formes verbales, noms propres) ; "
        "les mots disparus ou dont le sens a changé sont remplacés par un synonyme moderne "
        "(« adont » → « alors », « tantôt » → « aussitôt », « devers » → « vers ») ; "
        "la syntaxe et les tournures sont celles de Froissart.")
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
    for info in sorted(zin.infolist(), key=lambda i: i.filename != "mimetype"):
        data = zin.read(info)
        if info.filename.endswith(".opf"):
            data = data.decode("utf-8").replace("— orthographe modernisée", "— lecture facilitée").encode("utf-8")
        elif info.filename.endswith("titre.xhtml"):
            t = data.decode("utf-8")
            i = t.find("<i>Orthographe modernisée</i>")
            if i >= 0:
                data = (t[:i] + NOTE + t[t.index("</p>", i):]).encode("utf-8")
        zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
PY
echo "Fini : $OUT (listes des remplacements : $W/lisible.tsv, $W/vocabulaire.tsv)"
