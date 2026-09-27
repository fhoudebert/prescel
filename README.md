# Prescel

Préparer un livre numérisé (EPUB issu d'OCR : Google Livres, Gallica…) avant sa relecture dans Sigil.

## Lancement

```
python3 prescel.py --epubcheck /opt/epubcheck/epubcheck-5.4.0/epubcheck.jar
```

S'ouvre dans le navigateur (http://127.0.0.1:8765). Aucune dépendance : Python 3.8+.
Options : `--workdir` (projets, défaut `~/Prescel`), `--sigil CHEMIN`, `--port`, `--no-browser`.
Variables équivalentes : `PRESCEL_EPUBCHECK`, `PRESCEL_SIGIL`.

## Étapes

| Script | Rôle |
|---|---|
| `epub_inline2css.py` | styles en ligne → classes (facultatif) |
| `epub_simplify.py` | nettoyage du balisage OCR, texte vérifié avant/après |
| `epub_structure.py` | livres, chapitres, sommaires, notes, table des matières, liste des pages |
| `epub_split_h1.py` | un fichier par livre / chapitre |
| `epub_review.py` | rapport de relecture, copie surlignée, dictionnaire pour Sigil ; `--unmark` |

Les réglages préconisés sont cochés par défaut, puis ajustés d'après l'analyse du livre déposé.

## Relance ciblée

Après des corrections dans Sigil, « Relance ciblée » rejoue les étapes 3 à 5 sur le fichier
enregistré (ou sur une version déposée) : les marqueurs de relecture sont retirés d'abord et le
fichier de départ est copié dans `archives/`.
