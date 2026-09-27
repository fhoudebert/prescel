#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prescel — préparer un EPUB issu d'OCR avant la relecture dans Sigil.

Interface locale (navigateur) qui enchaîne les scripts du même dossier :
  epub_inline2css.py, epub_simplify.py, epub_structure.py,
  epub_split_h1.py, epub_review.py
avec leurs réglages expliqués, le journal d'exécution, epubcheck,
la table des matières obtenue, le rapport de relecture et l'ouverture
directe dans Sigil.

Aucune dépendance : Python 3.8+ suffit. epubcheck (Java) et Sigil sont
utilisés s'ils sont trouvés.

  python3 prescel.py                     # ouvre http://127.0.0.1:8765
  python3 prescel.py --workdir ~/Livres/prescel --port 8800
  python3 github/prescel/prescel.py --epubcheck /opt/epubcheck/epubcheck-5.4.0/epubcheck.jar --sigil /opt/Sigil/Sigil-2.8.1-x86_64.AppImage

Variables d'environnement équivalentes : PRESCEL_EPUBCHECK, PRESCEL_SIGIL.
"""

import argparse
import html
import json
import os
import platform
import posixpath
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "0.1"

# --------------------------------------------------------------------------
# Description des étapes (affichée telle quelle par l'interface)
# --------------------------------------------------------------------------

STEPS = [
    {
        "id": "inline2css", "script": "epub_inline2css.py", "suffix": "1-styles", "enabled": False,
        "title": "Styles en ligne → classes",
        "summary": "Remplace chaque style=\"…\" répété par une classe CSS commune. À réserver aux EPUB "
                   "dont on veut garder la mise en forme d'origine : le nettoyage (étape suivante) "
                   "supprime de toute façon ces styles.",
        "options": [
            {"flag": "--sort-properties", "type": "bool", "label": "Regrouper plus largement",
             "help": "« margin:0; text-indent:1em » et « text-indent:1em; margin:0 » donnent la même "
                     "classe. Sans risque sauf si un raccourci (margin) et sa forme longue "
                     "(margin-top) se côtoient."},
            {"flag": "--important", "type": "bool", "label": "Garder la priorité des styles",
             "help": "Ajoute !important : un style en ligne l'emportait sur toute feuille CSS, une "
                     "classe non. À cocher si l'EPUB a déjà une feuille avec des règles précises."},
        ],
    },
    {
        "id": "simplify", "enabled": True, "script": "epub_simplify.py", "suffix": "2-simplifie",
        "title": "Nettoyage du balisage",
        "summary": "Retire l'échafaudage de l'OCR : div et ancres vides, id inutiles, classes et "
                   "styles de Google. Les ancres qui servent aux numéros de page sont gardées. "
                   "Le texte est comparé avant/après : au moindre écart, rien n'est écrit.",
        "options": [
            {"flag": "--join-hyphens", "type": "bool", "default": True, "text": True,
             "label": "Recoller les mots coupés en fin de ligne",
             "help": "« estran-⏎ges » devient « estranges ». Seul le tiret de césure disparaît."},
            {"flag": "--flatten-br", "type": "bool", "default": True, "text": True,
             "label": "Texte continu",
             "help": "Les retours à la ligne de l'imprimé (<br/>) deviennent des espaces. Indispensable "
                     "pour une lecture fluide sur liseuse ; à éviter pour de la poésie."},
            {"flag": "--lettrines", "type": "bool", "default": True, "text": True,
             "label": "Recoller les lettrines",
             "help": "Une grande lettre isolée (« M ») est rattachée au début du paragraphe suivant "
                     "(« E trouuant » → « ME trouuant »). Chaque fusion est listée dans le journal "
                     "pour vérification."},
            {"flag": "--keep-ids", "type": "bool", "advanced": True, "label": "Garder tous les id",
             "help": "Par défaut, seuls les id visés par un lien sont gardés."},
            {"flag": "--keep-old-css", "type": "bool", "advanced": True,
             "label": "Garder les anciennes feuilles CSS",
             "help": "Par défaut elles sont retirées de l'EPUB quand plus rien ne s'en sert."},
        ],
    },
    {
        "id": "structure", "enabled": True, "script": "epub_structure.py", "suffix": "3-structure",
        "title": "Structure du livre",
        "summary": "Reconnaît les livres et chapitres (h1, h2), les sommaires et les notes ; "
                   "reconstruit la table des matières ; convertit la page-map Adobe en liste de "
                   "pages standard ; complète la feuille de style.",
        "options": [
            {"flag": "--merge-pages", "type": "bool", "default": True, "text": True,
             "label": "Recoller les paragraphes coupés par les pages",
             "help": "« …ayant combattu Montgom » + « mery, il n'y… » ne font plus qu'un paragraphe. "
                     "Le vocabulaire du livre décide s'il faut une espace. Le numéro de page reste "
                     "à l'endroit de la jonction."},
            {"flag": "--drop-furniture", "type": "bool", "default": True, "text": True,
             "label": "Retirer folios et signatures",
             "help": "Supprime les restes sans mots : numéros de page (« 172 »), signatures de "
                     "cahier (« IV-1 »), titres courants (« MONTLUC REMPLACÉ EN GUYENNE 171 »). "
                     "La liste complète est affichée."},
            {"flag": "--title-before", "type": "bool",
             "label": "Titre placé avant « Chapitre N »",
             "help": "Pour les éditions anciennes (Belon) où le titre en capitales précède le "
                     "numéro : il devient le titre du chapitre et apparaît dans la table."},
            {"flag": "--summary-max", "type": "int", "default": 350, "advanced": True,
             "label": "Longueur maximale d'un sommaire",
             "help": "Paragraphe court qui suit « Chapitre N » et résume le chapitre (éditions du "
                     "XIXᵉ siècle). 0 pour ne jamais en marquer."},
            {"flag": "--keep-page-map", "type": "bool", "advanced": True,
             "label": "Garder la page-map Adobe",
             "help": "Par défaut elle est convertie en liste de pages du toc.ncx : même résultat "
                     "sur liseuse, et epubcheck ne signale plus d'erreur."},
            {"flag": "--no-toc", "type": "bool", "advanced": True,
             "label": "Ne pas toucher à la table des matières", "help": ""},
            {"flag": "--verbose", "type": "bool", "default": True, "advanced": True,
             "label": "Détailler chaque jonction dans le journal",
             "help": "Utile pour contrôler les paragraphes recollés."},
            {"flag": "--chapter-regex", "type": "text", "advanced": True,
             "label": "Motif des titres de chapitre",
             "help": "Expression régulière Python. Vide : « CHAPITRE II », « Chap. XII. », « Chapitre "
                     "premier »… reconnus."},
            {"flag": "--book-regex", "type": "text", "advanced": True,
             "label": "Motif des titres de livre",
             "help": "Vide : « LIVRE SEPTIÈME », « Le second liure… »."},
            {"flag": "--table-regex", "type": "text", "advanced": True,
             "label": "Motif de la table imprimée",
             "help": "Après ce titre (« TABLE »), plus aucun chapitre n'est détecté, pour ne pas "
                     "doubler la table des matières."},
        ],
    },
    {
        "id": "split", "enabled": True, "script": "epub_split_h1.py", "suffix": "4-decoupe",
        "title": "Un fichier par chapitre",
        "summary": "Coupe les gros fichiers à chaque titre. Manifest, ordre de lecture, liens, table "
                   "des matières et numéros de page sont mis à jour. Dans Sigil, on navigue ainsi "
                   "chapitre par chapitre.",
        "options": [
            {"flag": "--tag", "type": "select", "default": "h1,h2",
             "choices": [["h1,h2", "livres et chapitres"], ["h2", "chapitres seulement"],
                         ["h1", "livres seulement"]],
             "label": "Couper aux titres",
             "help": "« livres et chapitres » : le titre d'un livre ouvre son propre fichier au lieu "
                     "de finir à la fin du chapitre précédent."},
            {"flag": "--match", "type": "text", "label": "Seulement les titres qui commencent par",
             "help": "Expression régulière, par exemple ^(CHAPITRE|TABLE). Vide : tous les titres. "
                     "Évite de couper à un titre de couverture."},
            {"flag": "--titles", "type": "bool", "label": "Titre de chaque fichier = titre du chapitre",
             "help": "Remplit la balise <title> ; certaines liseuses l'affichent en haut de page."},
            {"flag": "--min-parts", "type": "int", "default": 2, "advanced": True,
             "label": "Nombre minimal de morceaux", "help": "Un fichier n'est coupé que s'il donne au "
                                                           "moins ce nombre de morceaux."},
        ],
    },
    {
        "id": "review", "enabled": True, "script": "epub_review.py", "suffix": "relecture",
        "title": "Préparer la relecture",
        "summary": "Produit un rapport qui liste les cas douteux (mots collés ou coupés, casse, "
                   "chiffres dans les mots, chapitres manquants…) avec le fichier Sigil, l'extrait à "
                   "chercher et un lien vers la page scannée d'origine.",
        "options": [
            {"key": "mark", "type": "bool", "default": True, "label": "Surligner les cas dans l'EPUB",
             "help": "Crée une copie « à relire » où chaque cas est surligné en jaune. Dans Sigil, "
                     "rechercher a-verifier pour passer d'un cas au suivant. Le bouton « Retirer "
                     "les marqueurs » les enlève tous après la relecture."},
            {"key": "dict", "type": "bool", "default": True,
             "label": "Dictionnaire du livre pour Sigil",
             "help": "Liste des mots qui reviennent au moins 3 fois. Ajoutée aux dictionnaires "
                     "utilisateur de Sigil, elle évite que l'orthographe ancienne soit soulignée "
                     "partout : il ne reste que les vraies fautes."},
            {"flag": "--wordlist", "type": "text", "advanced": True, "label": "Liste de mots de référence",
             "help": "Chemin d'un fichier de mots (/usr/share/dict/french, .dic Hunspell) : "
                     "détection plus fine des mots collés."},
            {"flag": "--min-glued", "type": "int", "default": 11, "advanced": True,
             "label": "Longueur minimale d'un mot collé",
             "help": "Plus petit = plus de cas signalés, et plus de fausses alertes."},
            {"flag": "--max-items", "type": "int", "default": 400, "advanced": True,
             "label": "Cas affichés par catégorie", "help": ""},
        ],
    },
]
STEP_BY_ID = {s["id"]: s for s in STEPS}

# --------------------------------------------------------------------------
# Outils externes
# --------------------------------------------------------------------------

CONFIG = {"workdir": None, "epubcheck": None, "sigil": None}


def find_epubcheck(explicit):
    cand = explicit or os.environ.get("PRESCEL_EPUBCHECK")
    java = shutil.which("java")
    if cand:
        cand = os.path.expanduser(cand)
        if cand.endswith(".jar"):
            return [java, "-jar", cand] if java and os.path.exists(cand) else None
        return [cand] if shutil.which(cand) or os.path.exists(cand) else None
    if shutil.which("epubcheck"):
        return [shutil.which("epubcheck")]
    if java:
        for root in (HERE, os.path.join(HERE, ".."), os.path.expanduser("~")):
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath.count(os.sep) - root.count(os.sep) > 2:
                    dirnames[:] = []
                    continue
                if "epubcheck.jar" in filenames:
                    return [java, "-jar", os.path.join(dirpath, "epubcheck.jar")]
    return None


def find_sigil(explicit):
    cand = explicit or os.environ.get("PRESCEL_SIGIL")
    if cand:
        return [os.path.expanduser(cand)]
    for name in ("sigil", "Sigil"):
        if shutil.which(name):
            return [shutil.which(name)]
    system = platform.system()
    if system == "Darwin" and os.path.exists("/Applications/Sigil.app"):
        return ["open", "-a", "Sigil"]
    if system == "Windows":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            exe = os.path.join(base, "Sigil", "Sigil.exe")
            if os.path.exists(exe):
                return [exe]
    if shutil.which("flatpak"):
        try:
            r = subprocess.run(["flatpak", "info", "com.sigil_ebook.Sigil"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                return ["flatpak", "run", "com.sigil_ebook.Sigil"]
        except Exception:
            pass
    return None


def open_folder(path):
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # noqa
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# --------------------------------------------------------------------------
# Projets
# --------------------------------------------------------------------------

def slugify(name):
    base = re.sub(r"\.(epub|pdf)$", "", name, flags=re.I)
    base = re.sub(r"[^\w.-]+", "-", base, flags=re.U).strip("-")
    return base or "livre"


def project_dir(slug):
    d = os.path.join(CONFIG["workdir"], slug)
    if not os.path.abspath(d).startswith(os.path.abspath(CONFIG["workdir"])):
        raise ValueError("projet invalide")
    return d


def list_projects():
    out = []
    root = CONFIG["workdir"]
    if not os.path.isdir(root):
        return out
    for slug in sorted(os.listdir(root)):
        src = os.path.join(root, slug, slug + ".epub")
        if os.path.exists(src):
            out.append({"slug": slug, "mtime": os.path.getmtime(os.path.join(root, slug))})
    out.sort(key=lambda p: -p["mtime"])
    return out


MARKER_CACHE = {}


def has_markers(path):
    """Vrai si l'EPUB contient des marqueurs de relecture (a-verifier)."""
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    if key not in MARKER_CACHE:
        found = False
        try:
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if n.lower().endswith((".xhtml", ".html", ".htm", ".xml")) and \
                            b"a-verifier" in z.read(n):
                        found = True
                        break
        except zipfile.BadZipFile:
            pass
        MARKER_CACHE[key] = found
    return MARKER_CACHE[key]


def file_role(slug, name):
    if name == slug + ".epub":
        return "original"
    for suffix, role in (("-a-relire.epub", "à relire (marqué)"), ("-relu.epub", "relu, sans marqueurs"),
                         ("-prepare.epub", "préparé"), ("-0-sans-marqueurs.epub", "étape intermédiaire")):
        if name.endswith(suffix):
            return role
    if "-retouche-" in name:
        return "version retouchée déposée"
    if re.search(r"-\d-[\w-]+\.epub$", name):
        return "étape intermédiaire"
    return ""


def project_files(slug):
    d = project_dir(slug)
    files = []
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            if os.path.isfile(p):
                f = {"name": n, "size": os.path.getsize(p), "mtime": os.path.getmtime(p),
                     "url": "/files/%s/%s" % (slug, n)}
                if n.endswith(".epub"):
                    f["role"] = file_role(slug, n)
                    f["markers"] = has_markers(p)
                files.append(f)
    return files


# --------------------------------------------------------------------------
# Analyse d'un EPUB (pour pré-cocher les bons réglages)
# --------------------------------------------------------------------------

CHAP_LINE = re.compile(r"^(?:CHAPITRE|Chapitre|CHAP|Chap)\b\s*\.?\s*\S{1,14}[\s.]*$")
BOOK_LINE = re.compile(r"^(?:(?:LE|Le)\s+)?(?:PREMIER|SECOND|TIERS|premier|second|tiers|LIVRE|Livre)\b.{0,50}"
                       r"(?:LI[UV]RE|li[uv]re|$)")


def strip_tags(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def analyse(path):
    info = {"ok": True, "notes": []}
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Ce fichier n'est pas une archive EPUB valide."}
    with z:
        names = z.namelist()
        try:
            container = z.read("META-INF/container.xml").decode("utf-8", "replace")
            opf_path = re.search(r"""full-path\s*=\s*["']([^"']+)""", container).group(1)
            opf = z.read(opf_path).decode("utf-8", "replace")
        except Exception:
            return {"ok": False, "error": "container.xml ou OPF introuvable : EPUB incomplet."}
        ver = re.search(r"""<(?:\w+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf)
        title = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.S)
        author = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf, re.S)
        info.update({
            "version": ver.group(1) if ver else "?",
            "title": html.unescape(title.group(1).strip()) if title else "",
            "author": html.unescape(author.group(1).strip()) if author else "",
            "page_map": bool(re.search(r"page-map\s*=", opf)),
        })
        docs = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")) or
                ("/Text/" in n and n.endswith(".xml"))]
        stats = dict(docs=len(docs), images=sum(n.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg"))
                                                for n in names),
                     styles=0, gtxt=0, gbs=0, h1=0, h2=0, chap_lines=0, chap_title_before=0,
                     book_lines=0, markers=0, paragraphs=0, chars=0, divs=0)
        for n in docs:
            t = z.read(n).decode("utf-8", "replace")
            stats["styles"] += len(re.findall(r"\sstyle\s*=", t))
            stats["gtxt"] += t.count("gtxt_")
            stats["gbs"] += len(re.findall(r"""id=["']GBS\.""", t))
            stats["h1"] += len(re.findall(r"<h1\b", t))
            stats["h2"] += len(re.findall(r"<h2\b", t))
            stats["markers"] += t.count("a-verifier")
            stats["divs"] += len(re.findall(r"<div\b", t))
            paras = [strip_tags(m) for m in re.findall(r"<(?:p|h[1-6])\b[^>]*>(.*?)</(?:p|h[1-6])>", t, re.S)]
            stats["paragraphs"] += len(paras)
            stats["chars"] += sum(len(p) for p in paras)
            for i, ptxt in enumerate(paras):
                if CHAP_LINE.match(ptxt):
                    stats["chap_lines"] += 1
                    prev = paras[i - 1] if i else ""
                    letters = [c for c in prev if c.isalpha()][:12]
                    if len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) >= 0.8:
                        stats["chap_title_before"] += 1
                elif BOOK_LINE.match(ptxt) and len(ptxt) < 90:
                    stats["book_lines"] += 1
        info["stats"] = stats
        info["google"] = stats["gtxt"] > 0 or stats["gbs"] > 0
        info["simplified"] = any(n.endswith("Styles/livre.css") for n in names) and stats["gtxt"] == 0

    # Recommandations : {étape: {"enabled": bool, "options": {clé: valeur}}}
    rec = {s["id"]: {"enabled": False, "options": {}} for s in STEPS}
    notes = info["notes"]
    if info["google"] and not info["simplified"]:
        notes.append("EPUB produit par Google Livres (OCR) : nettoyage complet conseillé.")
    elif info["google"]:
        notes.append("EPUB issu de Google Livres (OCR), déjà passé par le nettoyage.")
    if info["simplified"]:
        notes.append("Le balisage semble déjà nettoyé (livre.css présente) : étape 2 décochée.")
    else:
        rec["simplify"]["enabled"] = True
        ocr = info["google"] or stats["divs"] > stats["paragraphs"]
        rec["simplify"]["options"] = {"--join-hyphens": ocr, "--flatten-br": ocr, "--lettrines": ocr}
        if not ocr:
            notes.append("Balisage qui ne ressemble pas à de l'OCR : césures, texte continu et "
                         "lettrines décochés.")
    if stats["styles"] and not info["google"]:
        notes.append("%d attributs style=\"…\" : l'étape 1 peut les regrouper si vous voulez garder "
                     "la mise en forme." % stats["styles"])
    rec["structure"]["enabled"] = True
    rec["structure"]["options"] = {"--merge-pages": info["google"], "--drop-furniture": info["google"]}
    if stats["chap_lines"] and stats["chap_title_before"] >= 0.4 * stats["chap_lines"]:
        rec["structure"]["options"]["--title-before"] = True
        notes.append("Dans %d cas sur %d, un titre en capitales précède « Chapitre N » : réglage "
                     "« titre placé avant » coché." % (stats["chap_title_before"], stats["chap_lines"]))
    if stats["chap_lines"] or stats["h2"]:
        notes.append("%d lignes « Chapitre … » repérées." % (stats["chap_lines"] + stats["h2"]))
    if info["page_map"]:
        notes.append("Numéros de page du livre papier présents (page-map) : ils seront conservés.")
    if stats["chap_lines"] + stats["h2"] >= 3:
        rec["split"]["enabled"] = True
        rec["split"]["options"] = {"--tag": "h1,h2" if (stats["book_lines"] or stats["h1"]) else "h2"}
    rec["review"]["enabled"] = True
    if stats["markers"]:
        notes.append("Cet EPUB contient déjà des marqueurs de relecture (%d) : pensez à les retirer "
                     "avant publication." % stats["markers"])
    info["recommend"] = rec
    return info


# --------------------------------------------------------------------------
# Exécution des étapes (tâches en arrière-plan)
# --------------------------------------------------------------------------

JOBS = {}
JOBS_LOCK = threading.Lock()


class Job:
    def __init__(self, slug, kind):
        self.id = uuid.uuid4().hex[:12]
        self.slug, self.kind = slug, kind
        self.lines = []           # {"step": id, "text": str, "kind": "out"|"cmd"|"err"|"info"}
        self.steps = []           # {"id","title","status","seconds","output"}
        self.status = "running"
        self.result = {}
        self.lock = threading.Lock()

    def log(self, step, text, kind="out"):
        with self.lock:
            self.lines.append({"step": step, "text": text, "kind": kind})

    def snapshot(self, since):
        with self.lock:
            return {"id": self.id, "status": self.status, "steps": [dict(s) for s in self.steps],
                    "lines": self.lines[since:], "next": len(self.lines), "result": self.result}


def run_command(job, step_id, cmd):
    job.log(step_id, " ".join(_quote(c) for c in cmd), "cmd")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                            cwd=HERE, text=True, encoding="utf-8", errors="replace")
    for line in proc.stdout:
        job.log(step_id, line.rstrip("\n"))
    return proc.wait()


def _quote(s):
    return s if re.fullmatch(r"[\w./:=,@%+-]+", s) else "'" + s.replace("'", "'\\''") + "'"


def epubcheck(job, step_id, path):
    if not CONFIG["epubcheck"]:
        return None
    job.log(step_id, "epubcheck " + os.path.basename(path), "cmd")
    try:
        r = subprocess.run(CONFIG["epubcheck"] + [path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    except Exception as e:
        job.log(step_id, "epubcheck n'a pas pu être lancé : %s" % e, "err")
        return None
    out = (r.stdout or "") + (r.stderr or "")
    msgs = [l for l in out.splitlines() if re.match(r"(FATAL|ERROR|WARNING)", l)]
    for l in msgs[:30]:
        job.log(step_id, l.replace(path, os.path.basename(path)), "err")
    summary = next((l for l in out.splitlines() if l.startswith("Messages:")), "")
    m = re.search(r"(\d+) fatals? / (\d+) errors? / (\d+) warnings?", summary)
    res = {"fatals": int(m.group(1)), "errors": int(m.group(2)), "warnings": int(m.group(3))} if m \
        else {"fatals": 0, "errors": len(msgs), "warnings": 0}
    job.log(step_id, "epubcheck : %d erreur(s), %d avertissement(s)"
            % (res["fatals"] + res["errors"], res["warnings"]), "info")
    return res


def build_args(step, opts):
    args = []
    for o in step["options"]:
        if "flag" not in o:
            continue
        key = o["flag"]
        val = opts.get(key, o.get("default"))
        if o["type"] == "bool":
            if val:
                args.append(key)
        elif o["type"] == "select":
            if val not in (None, ""):
                args += [key, str(val)]
        elif o["type"] == "int":
            if val not in (None, "") and str(val) != str(o.get("default")):
                args += [key, str(val)]
        elif o["type"] == "text":
            if val:
                args += [key, str(val)]
    return args


def pipeline(job, plan, check_mode, start=None):
    slug = job.slug
    d = project_dir(slug)
    original = os.path.join(d, slug + ".epub")
    current = os.path.join(d, os.path.basename(start)) if start else original
    py = sys.executable
    ok = True
    if not os.path.isfile(current):
        job.log("prescel", "Fichier de départ introuvable : %s" % os.path.basename(current), "err")
        job.status = "error"
        return
    job.result["start"] = os.path.basename(current)
    if current != original:
        # Relance ciblée : on archive le fichier de départ (il peut porter des
        # corrections faites dans Sigil et porter le nom d'une sortie à venir).
        arch_dir = os.path.join(d, "archives")
        os.makedirs(arch_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        arch = os.path.join(arch_dir, "%s-%s.epub" % (os.path.basename(current)[:-5], stamp))
        shutil.copy2(current, arch)
        job.log("prescel", "Relance à partir de %s (copie de sécurité : archives/%s)"
                % (os.path.basename(current), os.path.basename(arch)), "info")
        current = arch
        if has_markers(current):
            st = {"id": "unmark", "title": "Retrait des marqueurs (avant relance)", "status": "running",
                  "seconds": None, "output": None, "epubcheck": None}
            with job.lock:
                job.steps.append(st)
            t0 = time.time()
            clean = os.path.join(d, slug + "-0-sans-marqueurs.epub")
            rc = run_command(job, "unmark", [py, "-u", os.path.join(HERE, "epub_review.py"),
                                             current, "--unmark", "-o", clean])
            st["seconds"] = round(time.time() - t0, 1)
            if rc != 0:
                st["status"] = "error"
                job.status = "error"
                return
            st["status"], st["output"] = "done", os.path.basename(clean)
            current = clean
    final_epub = current
    for entry in plan:
        step = STEP_BY_ID[entry["id"]]
        st = {"id": step["id"], "title": step["title"], "status": "running", "seconds": None,
              "output": None, "epubcheck": None}
        with job.lock:
            job.steps.append(st)
        t0 = time.time()
        opts = entry.get("options", {})
        script = os.path.join(HERE, step["script"])
        if not os.path.exists(script):
            job.log(step["id"], "Script introuvable : %s (à placer à côté de prescel.py)" % step["script"], "err")
            st["status"], ok = "error", False
            break
        if step["id"] == "review":
            report = os.path.join(d, slug + "-relecture.html")
            cmd = [py, "-u", script, current, "--report", report] + build_args(step, opts)
            marked = os.path.join(d, slug + "-a-relire.epub") if opts.get("mark", True) else None
            dico = os.path.join(d, slug + "-dictionnaire.txt") if opts.get("dict", True) else None
            if marked:
                cmd += ["--mark", marked]
            if dico:
                cmd += ["--dict-out", dico]
            rc = run_command(job, step["id"], cmd)
            st["seconds"] = round(time.time() - t0, 1)
            if rc != 0:
                st["status"], ok = "error", False
                break
            st["status"] = "done"
            job.result["report"] = os.path.basename(report)
            if marked and os.path.exists(marked):
                job.result["marked"] = os.path.basename(marked)
                st["output"] = os.path.basename(marked)
                if check_mode in ("each", "end"):
                    st["epubcheck"] = epubcheck(job, step["id"], marked)
            if dico:
                job.result["dictionary"] = os.path.basename(dico)
            continue

        out = os.path.join(d, "%s-%s.epub" % (slug, step["suffix"]))
        if os.path.abspath(out) == os.path.abspath(current):
            out = out[:-5] + "-nouveau.epub"
        if os.path.exists(out):
            os.remove(out)
        cmd = [py, "-u", script, current, "-o", out] + build_args(step, opts)
        rc = run_command(job, step["id"], cmd)
        st["seconds"] = round(time.time() - t0, 1)
        if rc != 0:
            st["status"], ok = "error", False
            job.log(step["id"], "L'étape s'est arrêtée (code %d) : l'EPUB précédent est intact." % rc, "err")
            break
        if not os.path.exists(out):
            shutil.copy2(current, out)
            job.log(step["id"], "Rien à modifier : copie inchangée pour l'étape suivante.", "info")
        st["status"], st["output"] = "done", os.path.basename(out)
        current = final_epub = out
        if check_mode == "each":
            st["epubcheck"] = epubcheck(job, step["id"], out)

    if ok:
        final = os.path.join(d, slug + "-prepare.epub")
        if final_epub != final:
            shutil.copy2(final_epub, final)
        job.result["final"] = os.path.basename(final)
        if check_mode == "end" and not any(s.get("epubcheck") for s in job.steps if s["output"] and
                                           not s["output"].endswith("-a-relire.epub")):
            job.result["epubcheck"] = epubcheck(job, "final", final)
        elif check_mode == "each":
            last = [s for s in job.steps if s.get("epubcheck") and not s["output"].endswith("-a-relire.epub")]
            job.result["epubcheck"] = last[-1]["epubcheck"] if last else None
        job.result["toc"] = read_toc(final)
    job.status = "done" if ok else "error"


def unmark_job(job, name):
    d = project_dir(job.slug)
    src = os.path.join(d, name)
    out = os.path.join(d, job.slug + "-relu.epub")
    st = {"id": "unmark", "title": "Retrait des marqueurs", "status": "running", "seconds": None,
          "output": None, "epubcheck": None}
    job.steps.append(st)
    t0 = time.time()
    rc = run_command(job, "unmark", [sys.executable, "-u", os.path.join(HERE, "epub_review.py"),
                                     src, "--unmark", "-o", out])
    st["seconds"] = round(time.time() - t0, 1)
    st["status"] = "done" if rc == 0 else "error"
    if rc == 0:
        st["output"] = os.path.basename(out)
        job.result["final"] = os.path.basename(out)
        job.result["epubcheck"] = epubcheck(job, "unmark", out)
    job.status = "done" if rc == 0 else "error"


def start_job(slug, kind, target, *args):
    job = Job(slug, kind)
    with JOBS_LOCK:
        JOBS[job.id] = job

    def runner():
        try:
            target(job, *args)
        except Exception as e:  # erreur inattendue : visible dans le journal
            job.log("prescel", "Erreur interne : %r" % e, "err")
            job.status = "error"
    threading.Thread(target=runner, daemon=True).start()
    return job


def read_toc(path):
    """[(niveau, libellé)] depuis le toc.ncx (ou le nav EPUB 3)."""
    try:
        with zipfile.ZipFile(path) as z:
            ncx = next((n for n in z.namelist() if n.endswith(".ncx")), None)
            if ncx:
                t = z.read(ncx).decode("utf-8", "replace")
                t = re.sub(r"<pageList\b.*?</pageList>", "", t, flags=re.S)
                out, depth = [], 0
                for m in re.finditer(r"<navPoint\b|</navPoint>|<text>(.*?)</text>", t, re.S):
                    tok = m.group(0)
                    if tok.startswith("<navPoint"):
                        depth += 1
                    elif tok.startswith("</navPoint"):
                        depth -= 1
                    elif depth > 0:
                        out.append([depth, html.unescape(m.group(1).strip())])
                pages = len(re.findall(r"<pageTarget\b", z.read(ncx).decode("utf-8", "replace")))
                return {"entries": out, "pages": pages}
    except Exception:
        pass
    return {"entries": [], "pages": 0}


# --------------------------------------------------------------------------
# Serveur HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Prescel/" + VERSION

    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    # ---- GET ----
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/config":
            self.send_json({"steps": STEPS, "projects": list_projects(),
                            "epubcheck": bool(CONFIG["epubcheck"]), "sigil": bool(CONFIG["sigil"]),
                            "workdir": CONFIG["workdir"], "version": VERSION,
                            "missing": [s["script"] for s in STEPS
                                        if not os.path.exists(os.path.join(HERE, s["script"]))]})
        elif path == "/api/project":
            slug = parse_qs(url.query).get("slug", [""])[0]
            src = os.path.join(project_dir(slug), slug + ".epub")
            if not os.path.exists(src):
                return self.send_json({"ok": False, "error": "Projet introuvable."}, 404)
            info = analyse(src)
            info.update({"slug": slug, "files": project_files(slug)})
            self.send_json(info)
        elif path.startswith("/api/job/"):
            job = JOBS.get(path.rsplit("/", 1)[-1])
            if not job:
                return self.send_json({"error": "tâche inconnue"}, 404)
            since = int(parse_qs(url.query).get("since", ["0"])[0])
            snap = job.snapshot(since)
            snap["files"] = project_files(job.slug)
            self.send_json(snap)
        elif path.startswith("/files/"):
            self.serve_file(unquote(path[len("/files/"):]), parse_qs(url.query).get("dl", ["0"])[0] == "1")
        else:
            self.send_error(404)

    def serve_file(self, rel, download):
        root = os.path.abspath(CONFIG["workdir"])
        full = os.path.abspath(os.path.join(root, rel))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            return self.send_error(404)
        ctype = {".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8",
                 ".epub": "application/epub+zip"}.get(os.path.splitext(full)[1].lower(),
                                                      "application/octet-stream")
        size = os.path.getsize(full)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        if download or full.endswith(".epub"):
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % os.path.basename(full))
        self.end_headers()
        with open(full, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/upload":
                return self.upload()
            body = self.read_json()
            if path == "/api/run":
                slug = body["slug"]
                plan = [p for p in body.get("steps", []) if p.get("enabled")]
                if not plan:
                    return self.send_json({"ok": False, "error": "Aucune étape cochée."}, 400)
                job = start_job(slug, "pipeline", pipeline, plan, body.get("epubcheck", "end"),
                                body.get("start") or None)
                self.send_json({"ok": True, "job": job.id})
            elif path == "/api/unmark":
                job = start_job(body["slug"], "unmark", unmark_job, body["file"])
                self.send_json({"ok": True, "job": job.id})
            elif path == "/api/open":
                self.open_in(body)
            else:
                self.send_error(404)
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def upload(self):
        name = unquote(self.headers.get("X-Filename", "livre.epub"))
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        if name.lower().endswith(".pdf"):
            return self.send_json({"ok": False, "pdf": True, "error":
                                   "L'import PDF n'est pas encore disponible. Il passera par la couche "
                                   "texte du PDF (ou un OCR comme Tesseract) avant de rejoindre la même "
                                   "chaîne. En attendant, convertissez le PDF en EPUB (Calibre) ou "
                                   "téléchargez l'EPUB proposé par la bibliothèque numérique."})
        if not name.lower().endswith(".epub"):
            return self.send_json({"ok": False, "error": "Choisissez un fichier .epub."}, 400)
        target = unquote(self.headers.get("X-Project", ""))
        if target:
            # Version retouchée (enregistrée par Sigil ailleurs) ajoutée au projet
            d = project_dir(target)
            if not os.path.isdir(d):
                return self.send_json({"ok": False, "error": "Projet introuvable."}, 404)
            fname = "%s-retouche-%s.epub" % (target, time.strftime("%Y%m%d-%H%M%S"))
            with open(os.path.join(d, fname), "wb") as f:
                f.write(data)
            if analyse(os.path.join(d, fname)).get("ok") is False:
                os.remove(os.path.join(d, fname))
                return self.send_json({"ok": False, "error": "Ce fichier n'est pas un EPUB lisible."}, 400)
            return self.send_json({"ok": True, "retouche": fname, "files": project_files(target)})
        slug = slugify(os.path.basename(name))
        d = project_dir(slug)
        os.makedirs(d, exist_ok=True)
        src = os.path.join(d, slug + ".epub")
        with open(src, "wb") as f:
            f.write(data)
        info = analyse(src)
        info.update({"slug": slug, "files": project_files(slug)})
        self.send_json(info)

    def open_in(self, body):
        what, slug = body.get("what"), body.get("slug")
        d = project_dir(slug)
        if what == "folder":
            open_folder(d)
            return self.send_json({"ok": True})
        path = os.path.join(d, os.path.basename(body.get("file", "")))
        if not os.path.isfile(path):
            return self.send_json({"ok": False, "error": "Fichier introuvable."}, 404)
        if not CONFIG["sigil"]:
            return self.send_json({"ok": False, "error": "Sigil introuvable : relancez Prescel avec "
                                   "--sigil CHEMIN (ou la variable PRESCEL_SIGIL)."}, 404)
        subprocess.Popen(CONFIG["sigil"] + [path])
        self.send_json({"ok": True})


# --------------------------------------------------------------------------
# Page web (HTML + CSS + JS, sans dépendance)
# --------------------------------------------------------------------------

PAGE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prescel</title>
<style>
:root {
  --encre: #1f2a44; --papier: #f3f5f2; --feuille: #ffffff; --vert: #2f7a6b; --vert-clair: #d9ebe6;
  --or: #b0860a; --or-clair: #fbf0c9; --rouge: #9b2c2c; --gris: #5d6673; --trait: #d3d9d4;
  --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
  --mono: ui-monospace, "SFMono-Regular", "DejaVu Sans Mono", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--papier); color: var(--encre); }
body { font: 15px/1.5 var(--sans); }
a { color: var(--vert); }
button, input, select { font: inherit; color: inherit; }
:focus-visible { outline: 3px solid var(--or); outline-offset: 2px; }

header.bandeau { display: flex; align-items: baseline; gap: 1.2rem; flex-wrap: wrap;
  padding: 1.6rem clamp(1rem, 4vw, 3rem) 1rem; border-bottom: 1px solid var(--trait); }
header.bandeau h1 { font: 600 2.1rem/1 var(--serif); margin: 0; letter-spacing: .01em; }
header.bandeau p { margin: 0; color: var(--gris); font-family: var(--serif); font-size: 1.05rem; }
.outils { margin-left: auto; font-size: .85rem; color: var(--gris); display: flex; gap: 1rem; }
.outils .ok::before { content: "● "; color: var(--vert); }
.outils .non::before { content: "○ "; color: var(--gris); }

.grille { display: grid; grid-template-columns: minmax(0, 1fr) 24rem; gap: 2rem;
  padding: 1.5rem clamp(1rem, 4vw, 3rem) 2rem; align-items: start; }
@media (max-width: 70rem) { .grille { grid-template-columns: 1fr; } aside.panneau { position: static; } }

/* Choix du fichier */
.depot { border: 2px dashed var(--trait); border-radius: 6px; padding: 1.2rem 1.4rem; background: var(--feuille);
  display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; }
.depot.survol { border-color: var(--vert); background: var(--vert-clair); }
.depot strong { font: 600 1.15rem var(--serif); display: block; }
.depot small { color: var(--gris); }
.bouton { border: 1px solid var(--encre); background: var(--feuille); padding: .45rem .9rem; border-radius: 4px;
  cursor: pointer; }
.bouton:hover { background: var(--vert-clair); }
.bouton.principal { background: var(--encre); color: #fff; border-color: var(--encre); padding: .6rem 1.2rem;
  font-weight: 600; }
.bouton.principal:hover { background: #2c3a5e; }
.bouton:disabled { opacity: .45; cursor: not-allowed; }
.reprendre { margin-left: auto; font-size: .9rem; }
.reprendre select { max-width: 14rem; }

.fiche { margin: 1.2rem 0 0; padding: 1rem 1.4rem; background: var(--feuille); border-left: 4px solid var(--vert); }
.fiche h2 { font: 600 1.35rem/1.25 var(--serif); margin: 0 0 .2rem; }
.fiche .auteur { color: var(--gris); font-family: var(--serif); margin: 0 0 .6rem; }
.fiche dl { display: flex; flex-wrap: wrap; gap: .3rem 1.6rem; margin: 0 0 .6rem; font-size: .9rem; }
.fiche dt { color: var(--gris); } .fiche dd { margin: 0 0 0 .3rem; font-weight: 600; }
.fiche dl div { display: flex; }
.fiche ul { margin: .3rem 0 0; padding-left: 1.1rem; font-family: var(--serif); }
.erreur { color: var(--rouge); font-weight: 600; }

/* Chaîne des étapes : la seule vraie séquence de la page */
ol.chaine { list-style: none; margin: 2rem 0 0; padding: 0; counter-reset: etape; position: relative; }
ol.chaine::before { content: ""; position: absolute; left: 1.05rem; top: .4rem; bottom: .4rem;
  border-left: 2px solid var(--encre); opacity: .25; }
li.etape { counter-increment: etape; position: relative; padding: 0 0 2rem 3.2rem; }
li.etape::before { content: counter(etape); position: absolute; left: 0; top: 0; width: 2.2rem; height: 2.2rem;
  border-radius: 50%; background: var(--papier); border: 2px solid var(--encre);
  font: 600 1.05rem/2rem var(--serif); text-align: center; }
li.etape.inactive::before { border-color: var(--trait); color: var(--gris); }
li.etape.inactive .corps { opacity: .5; }
.entete { display: flex; align-items: baseline; gap: .7rem; }
.entete label { font: 600 1.25rem/1.3 var(--serif); cursor: pointer; }
.entete input { width: 1.1rem; height: 1.1rem; accent-color: var(--vert); transform: translateY(2px); }
.etape .resume { font-family: var(--serif); font-size: 1rem; margin: .25rem 0 .8rem; max-width: 46rem; }
.options { background: var(--feuille); border: 1px solid var(--trait); border-radius: 4px; }
.option { display: grid; grid-template-columns: minmax(12rem, 18rem) minmax(0, 1fr); gap: 1.2rem;
  padding: .7rem 1rem; border-top: 1px solid var(--trait); }
.option:first-child { border-top: none; }
@media (max-width: 44rem) { .option { grid-template-columns: 1fr; gap: .2rem; } }
.option .ctrl label { display: flex; gap: .5rem; align-items: flex-start; cursor: pointer; font-weight: 600; }
.option .ctrl input[type=checkbox] { margin-top: .2rem; accent-color: var(--vert); width: 1rem; height: 1rem; flex: none; }
.option .ctrl input[type=text], .option .ctrl input[type=number], .option .ctrl select {
  width: 100%; margin-top: .3rem; padding: .3rem .4rem; border: 1px solid var(--trait); border-radius: 3px;
  background: var(--papier); }
.option .ctrl input[type=text] { font-family: var(--mono); font-size: .85rem; }
.option .aide { margin: 0; color: var(--gris); font-size: .9rem; }
.touche { display: inline-block; margin-top: .3rem; font-size: .75rem; font-weight: 600; color: var(--or);
  background: var(--or-clair); padding: .05rem .45rem; border-radius: 3px; }
.recommande { font-size: .75rem; color: var(--vert); margin-left: .4rem; font-weight: 400; }
details.avance > summary { cursor: pointer; padding: .5rem 1rem; color: var(--gris); font-size: .9rem;
  border-top: 1px solid var(--trait); }
details.avance[open] > summary { color: var(--encre); }

/* Panneau de droite */
aside.panneau { position: sticky; top: 1rem; display: flex; flex-direction: column; gap: 1rem; }
.bloc { background: var(--feuille); border: 1px solid var(--trait); border-radius: 4px; padding: 1rem 1.1rem; }
.bloc h3 { font: 600 1.1rem var(--serif); margin: 0 0 .6rem; }
.bloc fieldset { border: none; padding: 0; margin: .2rem 0 1rem; }
.bloc legend { font-size: .85rem; color: var(--gris); margin-bottom: .3rem; }
.bloc fieldset label { display: block; font-size: .9rem; margin: .15rem 0; }
.bloc .bouton.principal { width: 100%; }
ul.suivi { list-style: none; padding: 0; margin: 0; font-size: .9rem; }
ul.suivi li { display: grid; grid-template-columns: 1.3rem 1fr auto; gap: .4rem; padding: .3rem 0;
  border-bottom: 1px solid var(--trait); }
ul.suivi .etat { font-weight: 700; }
ul.suivi .running .etat { color: var(--or); } ul.suivi .done .etat { color: var(--vert); }
ul.suivi .error .etat { color: var(--rouge); }
ul.suivi small { color: var(--gris); }
.check { font-size: .8rem; }
.check.bon { color: var(--vert); } .check.mauvais { color: var(--rouge); }
.actions { display: flex; flex-direction: column; gap: .5rem; margin-top: .8rem; }
.actions .bouton { text-align: left; }
.fichiers { font-size: .85rem; margin: .3rem 0 0; padding-left: 1rem; }
.bloc select#depart { width: 100%; padding: .3rem; border: 1px solid var(--trait); border-radius: 3px; background: var(--papier); }
.note { font-size: .85rem; color: var(--gris); margin: .4rem 0 0; font-family: var(--serif); }
.note.attention { color: var(--or); font-weight: 600; }
.bloc-relance-actif { border-color: var(--vert); box-shadow: inset 4px 0 0 var(--vert); }
.fichiers li { margin: .15rem 0; overflow-wrap: anywhere; }

/* Journal et résultats */
section.sortie { padding: 0 clamp(1rem, 4vw, 3rem) 4rem; scroll-margin-top: 1rem; }
.onglets { display: flex; gap: .2rem; border-bottom: 2px solid var(--encre); }
.onglets button { border: none; background: none; padding: .5rem 1rem; cursor: pointer; font: 600 1rem var(--serif);
  color: var(--gris); border-radius: 4px 4px 0 0; }
.onglets button[aria-selected=true] { background: var(--encre); color: #fff; }
.vue { background: var(--feuille); border: 1px solid var(--trait); border-top: none; padding: 1rem 1.2rem;
  min-height: 12rem; }
pre.journal { margin: 0; max-height: 32rem; overflow: auto; font: .8rem/1.5 var(--mono); white-space: pre-wrap; }
pre.journal .cmd { color: var(--vert); font-weight: 600; }
pre.journal .err { color: var(--rouge); }
pre.journal .info { color: var(--or); font-weight: 600; }
pre.journal .titre { display: block; margin-top: .8rem; font: 600 .95rem var(--serif); color: var(--encre); }
ul.tdm { font-family: var(--serif); margin: 0; padding: 0; list-style: none; columns: 2 22rem; column-gap: 2.5rem; }
ul.tdm li { break-inside: avoid; margin: .15rem 0; padding-left: 1.2rem; text-indent: -1.2rem; }
ul.tdm li.niv1 { font-weight: 600; margin-top: .6rem; }
ul.tdm li.niv2 { padding-left: 2.4rem; }
iframe.rapport { width: 100%; height: 36rem; border: none; }
.vide { color: var(--gris); font-family: var(--serif); }
.conseils { font-family: var(--serif); max-width: 50rem; }
.conseils h4 { font-size: 1.05rem; margin: 1.2rem 0 .3rem; }
.conseils li { margin: .25rem 0; }
@media (prefers-reduced-motion: no-preference) {
  li.etape.courante::before { animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { background: var(--or-clair); } }
}
</style>
</head>
<body>
<header class="bandeau">
  <h1>Prescel</h1>
  <p>préparer un livre numérisé avant sa relecture dans Sigil</p>
  <div class="outils" id="outils"></div>
</header>

<div class="grille">
  <main>
    <div class="depot" id="depot">
      <div>
        <strong>Choisir le livre</strong>
        <small>Un EPUB (Google Livres, Gallica, Internet Archive…). Glisser-déposer ici ou</small>
      </div>
      <label class="bouton">Parcourir…<input type="file" id="fichier" accept=".epub,.pdf" hidden></label>
      <div class="reprendre" id="reprendre"></div>
    </div>
    <div id="fiche"></div>
    <ol class="chaine" id="chaine"></ol>
  </main>

  <aside class="panneau">
    <div class="bloc">
      <h3>Lancer</h3>
      <fieldset>
        <legend>Contrôle epubcheck</legend>
        <label><input type="radio" name="check" value="end" checked> sur le résultat final</label>
        <label><input type="radio" name="check" value="each"> après chaque étape</label>
        <label><input type="radio" name="check" value="none"> jamais</label>
      </fieldset>
      <fieldset id="depart-bloc" hidden>
        <legend>Partir de</legend>
        <select id="depart" aria-label="Fichier de départ"></select>
        <p class="note" id="depart-note"></p>
      </fieldset>
      <button class="bouton principal" id="lancer" disabled>Préparer le livre</button>
      <p class="vide" id="attente" style="margin:.6rem 0 0;font-size:.9rem">Choisissez d'abord un EPUB.</p>
    </div>
    <div class="bloc" id="bloc-relance" hidden>
      <h3>Relance ciblée</h3>
      <p class="note">Après des corrections dans Sigil (titre de chapitre ajouté, paragraphe réparé…),
        on rejoue seulement la structure, le découpage et le rapport sur le fichier enregistré.
        Les marqueurs de relecture sont retirés avant, et le fichier de départ est archivé.</p>
      <div class="actions">
        <button class="bouton" id="relance">Préparer une relance après Sigil</button>
        <label class="bouton">Déposer une version retouchée…<input type="file" id="retouche" accept=".epub" hidden></label>
      </div>
      <p class="note" id="relance-note"></p>
    </div>
    <div class="bloc" id="bloc-suivi" hidden>
      <h3>Déroulement</h3>
      <ul class="suivi" id="suivi"></ul>
      <div class="actions" id="actions"></div>
    </div>
    <div class="bloc" id="bloc-fichiers" hidden>
      <h3>Fichiers du projet</h3>
      <ul class="fichiers" id="fichiers"></ul>
    </div>
  </aside>
</div>

<section class="sortie">
    <div class="onglets" role="tablist" id="onglets">
      <button role="tab" aria-selected="true" data-vue="journal">Journal</button>
      <button role="tab" aria-selected="false" data-vue="tdm">Table des matières</button>
      <button role="tab" aria-selected="false" data-vue="rapport">Rapport de relecture</button>
      <button role="tab" aria-selected="false" data-vue="sigil">Relire dans Sigil</button>
    </div>
    <div class="vue" id="vue-journal"><pre class="journal" id="journal"><span class="vide">Le journal d'exécution s'affichera ici.</span></pre></div>
    <div class="vue" id="vue-tdm" hidden><p class="vide">La table des matières du livre préparé s'affichera ici.</p></div>
    <div class="vue" id="vue-rapport" hidden><p class="vide">Le rapport de relecture s'affichera ici après l'étape « Préparer la relecture ».</p></div>
    <div class="vue conseils" id="vue-sigil" hidden></div>
</section>

<script>
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
const state = { config: null, project: null, job: null, since: 0, lastStep: null };

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} :
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({ ok: false, error: "Réponse illisible du serveur." }));
  if (!r.ok && data.ok !== false) data.ok = false;
  return data;
}

/* ---------- démarrage ---------- */
async function init() {
  state.config = await api("/api/config");
  const c = state.config;
  $("#outils").append(
    el("span", { class: c.epubcheck ? "ok" : "non", title: c.epubcheck ? "" : "Indiquez --epubcheck CHEMIN au lancement" },
       c.epubcheck ? "epubcheck" : "epubcheck absent"),
    el("span", { class: c.sigil ? "ok" : "non", title: c.sigil ? "" : "Indiquez --sigil CHEMIN au lancement" },
       c.sigil ? "Sigil" : "Sigil introuvable"));
  if (c.missing.length) $("#fiche").append(el("p", { class: "erreur" },
    "Scripts manquants à côté de prescel.py : " + c.missing.join(", ")));
  if (!c.epubcheck) $$radio("none");
  renderProjects();
  renderSteps();
  renderSigilHelp();
  setupDrop();
  document.querySelectorAll("#onglets button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.vue)));
  $("#lancer").addEventListener("click", run);
  $("#depart").addEventListener("change", startChanged);
  $("#relance").addEventListener("click", prepareRelance);
  $("#retouche").addEventListener("change", e => { if (e.target.files[0]) uploadRetouche(e.target.files[0]); e.target.value = ""; });
}
function $$radio(v) { document.querySelectorAll("input[name=check]").forEach(r => { r.checked = r.value === v; if (!state.config.epubcheck && r.value !== "none") r.disabled = true; }); }

function renderProjects() {
  const p = state.config.projects;
  const box = $("#reprendre"); box.innerHTML = "";
  if (!p.length) return;
  const sel = el("select", { "aria-label": "Reprendre un projet" },
    el("option", { value: "" }, "Reprendre un projet…"),
    p.map(x => el("option", { value: x.slug }, x.slug)));
  sel.addEventListener("change", async () => { if (sel.value) loadProject(await api("/api/project?slug=" + encodeURIComponent(sel.value))); });
  box.append(sel);
}

/* ---------- étapes et réglages ---------- */
function renderSteps() {
  const ol = $("#chaine"); ol.innerHTML = "";
  for (const s of state.config.steps) {
    const on = el("input", { type: "checkbox", id: "on-" + s.id, checked: !!s.enabled });
    on.addEventListener("change", () => li.classList.toggle("inactive", !on.checked));
    const opts = el("div", { class: "options" });
    const adv = el("details", { class: "avance" }, el("summary", {}, "Réglages avancés"));
    for (const o of s.options) (o.advanced ? adv : opts).append(renderOption(s, o));
    if (adv.children.length > 1) opts.append(adv);
    const li = el("li", { class: "etape" + (s.enabled ? "" : " inactive"), id: "etape-" + s.id },
      el("div", { class: "entete" }, on, el("label", { for: "on-" + s.id }, s.title), el("span", { class: "recommande", id: "rec-" + s.id })),
      el("div", { class: "corps" }, el("p", { class: "resume" }, s.summary), opts));
    ol.append(li);
  }
}
function optId(s, o) { return "opt-" + s.id + "-" + (o.flag || o.key).replace(/[^\w]/g, ""); }
function renderOption(s, o) {
  const id = optId(s, o);
  let ctrl;
  if (o.type === "bool") {
    ctrl = el("label", {}, el("input", { type: "checkbox", id, checked: !!o.default }), o.label);
  } else if (o.type === "select") {
    ctrl = el("label", { for: id, style: "display:block" }, o.label,
      el("select", { id }, o.choices.map(([v, t]) => el("option", { value: v, selected: v === o.default }, t))));
  } else {
    ctrl = el("label", { for: id, style: "display:block" }, o.label,
      el("input", { type: o.type === "int" ? "number" : "text", id, value: o.default ?? "", spellcheck: "false" }));
  }
  const help = el("div", {}, el("p", { class: "aide" }, o.help || ""),
    o.text ? el("span", { class: "touche", title: "Le texte final est vérifié caractère par caractère ; seul ce qui est décrit change." }, "touche au texte (vérifié)") : null);
  return el("div", { class: "option" }, el("div", { class: "ctrl" }, ctrl), help);
}
function setStep(id, enabled, options = {}) {
  const on = $("#on-" + id); if (!on) return;
  on.checked = enabled; $("#etape-" + id).classList.toggle("inactive", !enabled);
  const s = state.config.steps.find(x => x.id === id);
  for (const o of s.options) {
    const k = o.flag || o.key; if (!(k in options)) continue;
    const input = $("#" + optId(s, o));
    if (o.type === "bool") input.checked = !!options[k]; else input.value = options[k];
  }
}
function resetDefaults() {
  for (const s of state.config.steps) {
    const options = {};
    for (const o of s.options) options[o.flag || o.key] = o.default ?? (o.type === "bool" ? false : "");
    setStep(s.id, !!s.enabled, options);
    $("#rec-" + s.id).textContent = "";
  }
}
function collect() {
  return state.config.steps.map(s => {
    const options = {};
    for (const o of s.options) {
      const input = $("#" + optId(s, o)); const k = o.flag || o.key;
      options[k] = o.type === "bool" ? input.checked : o.type === "int" ? (input.value === "" ? null : Number(input.value)) : input.value.trim();
    }
    return { id: s.id, enabled: $("#on-" + s.id).checked, options };
  });
}

/* ---------- choix du fichier ---------- */
function setupDrop() {
  const d = $("#depot");
  ["dragenter", "dragover"].forEach(ev => d.addEventListener(ev, e => { e.preventDefault(); d.classList.add("survol"); }));
  ["dragleave", "drop"].forEach(ev => d.addEventListener(ev, e => { e.preventDefault(); d.classList.remove("survol"); }));
  d.addEventListener("drop", e => { if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
  $("#fichier").addEventListener("change", e => { if (e.target.files[0]) upload(e.target.files[0]); });
}
async function upload(file) {
  $("#fiche").innerHTML = ""; $("#fiche").append(el("p", { class: "vide" }, "Analyse de « " + file.name + " »…"));
  const r = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file });
  const data = await r.json();
  loadProject(data);
}
function loadProject(info) {
  const f = $("#fiche"); f.innerHTML = "";
  if (!info.ok) {
    f.append(el("div", { class: "fiche" }, el("p", { class: "erreur" }, info.error)));
    $("#lancer").disabled = true; return;
  }
  state.project = info;
  resetDefaults();
  const st = info.stats;
  const facts = [["EPUB", info.version], ["fichiers texte", st.docs], ["images", st.images],
    ["paragraphes", st.paragraphs.toLocaleString("fr")], ["titres", st.h1 + st.h2],
    ["lignes « Chapitre »", st.chap_lines], ["numéros de page", info.page_map || st.gbs ? "oui" : "non"]];
  f.append(el("div", { class: "fiche" },
    el("h2", {}, info.title || info.slug),
    info.author ? el("p", { class: "auteur" }, info.author) : null,
    el("dl", {}, facts.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, String(v))))),
    info.notes.length ? el("ul", {}, info.notes.map(n => el("li", {}, n))) : null,
    el("p", { class: "aide", style: "margin:.6rem 0 0;color:var(--gris);font-size:.9rem" },
      "Les étapes et réglages ci-dessous ont été pré-cochés d'après cette analyse ; ajustez-les si besoin.")));
  for (const [id, rec] of Object.entries(info.recommend)) {
    setStep(id, rec.enabled, rec.options);
    $("#rec-" + id).textContent = rec.enabled ? "conseillé" : "";
  }
  $("#lancer").disabled = false; $("#attente").textContent = "Projet : " + info.slug;
  $("#relance-note").textContent = "";
  $("#bloc-relance").classList.remove("bloc-relance-actif");
  renderFiles(info.files, true);
}

/* ---------- exécution ---------- */
async function run() {
  const check = document.querySelector("input[name=check]:checked").value;
  const res = await api("/api/run", { slug: state.project.slug, steps: collect(), epubcheck: check,
                                     start: $("#depart").value || null });
  if (!res.ok) { alert(res.error); return; }
  startPolling(res.job, true);
}
function startPolling(jobId, reset) {
  state.job = jobId; state.since = 0; state.lastStep = null;
  if (reset) { $("#journal").innerHTML = ""; $("#suivi").innerHTML = ""; $("#actions").innerHTML = ""; }
  $("#bloc-suivi").hidden = false; $("#lancer").disabled = true; $("#lancer").textContent = "En cours…";
  showTab("journal");
  $(".sortie").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  poll();
}
async function poll() {
  const j = await api("/api/job/" + state.job + "?since=" + state.since);
  state.since = j.next;
  const pre = $("#journal");
  const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
  for (const l of j.lines) {
    if (l.step !== state.lastStep) {
      const s = state.config.steps.find(x => x.id === l.step);
      pre.append(el("span", { class: "titre" }, s ? s.title : l.step === "final" ? "Contrôle final" : l.step === "unmark" ? "Retrait des marqueurs" : l.step === "prescel" ? "Départ" : l.step));
      state.lastStep = l.step;
    }
    pre.append(el("span", { class: l.kind }, (l.kind === "cmd" ? "$ " : "") + l.text + "\n"));
  }
  if (atBottom) pre.scrollTop = pre.scrollHeight;
  renderSuivi(j);
  renderFiles(j.files);
  if (j.status === "running") setTimeout(poll, 600);
  else finish(j);
}
function renderSuivi(j) {
  const ul = $("#suivi"); ul.innerHTML = "";
  document.querySelectorAll("li.etape").forEach(li => li.classList.remove("courante"));
  for (const s of j.steps) {
    const mark = s.status === "done" ? "✓" : s.status === "error" ? "✗" : "…";
    const ck = s.epubcheck ? el("div", { class: "check " + (s.epubcheck.errors + s.epubcheck.fatals ? "mauvais" : "bon") },
      "epubcheck : " + (s.epubcheck.errors + s.epubcheck.fatals) + " erreur(s)") : null;
    ul.append(el("li", { class: s.status }, el("span", { class: "etat" }, mark),
      el("span", {}, s.title, ck), el("small", {}, s.seconds != null ? s.seconds + " s" : "")));
    if (s.status === "running") $("#etape-" + s.id)?.classList.add("courante");
  }
}
function fmtTime(t) {
  const d = new Date(t * 1000), now = new Date();
  const hm = d.toLocaleTimeString("fr", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === now.toDateString() ? hm : d.toLocaleDateString("fr") + " " + hm;
}
function renderStart(files, reset) {
  const sel = $("#depart"); const prev = reset ? "" : sel.value;
  const epubs = files.filter(f => f.name.endsWith(".epub"));
  state.epubs = epubs;
  sel.innerHTML = "";
  const slug = state.project.slug;
  const orig = epubs.find(f => f.role === "original");
  const order = [orig, ...epubs.filter(f => f !== orig).sort((a, b) => b.mtime - a.mtime)].filter(Boolean);
  for (const f of order) {
    const label = (f.role === "original" ? "Original — " : "") + f.name +
      (f.role && f.role !== "original" ? " (" + f.role + ")" : "") + " — " + fmtTime(f.mtime);
    sel.append(el("option", { value: f.role === "original" ? "" : f.name, selected: (f.role === "original" ? "" : f.name) === prev }, label));
  }
  $("#depart-bloc").hidden = epubs.length < 2;
  $("#bloc-relance").hidden = false;
  startChanged();
}
function startChanged() {
  const v = $("#depart").value;
  const f = (state.epubs || []).find(x => x.name === v);
  const note = $("#depart-note");
  note.className = "note";
  if (!v) { note.textContent = "Toute la chaîne repart du fichier déposé."; $("#lancer").textContent = "Préparer le livre"; return; }
  $("#lancer").textContent = "Relancer depuis ce fichier";
  note.textContent = (f && f.markers ? "Contient des marqueurs : ils seront retirés avant les étapes. " : "") +
    "Une copie est gardée dans archives/.";
  if (f && f.markers) note.className = "note attention";
}
function prepareRelance() {
  const cands = (state.epubs || []).filter(f => f.role !== "original" && f.role !== "étape intermédiaire")
    .sort((a, b) => b.mtime - a.mtime);
  const note = $("#relance-note");
  if (!cands.length) { note.textContent = "Aucune version relue ou retouchée dans ce projet : préparez d'abord le livre."; return; }
  const f = cands[0];
  $("#depart").value = f.name; startChanged();
  for (const s of state.config.steps) setStep(s.id, ["structure", "split", "review"].includes(s.id));
  $("#bloc-relance").classList.add("bloc-relance-actif");
  note.textContent = "Départ : " + f.name + " (modifié " + fmtTime(f.mtime) + "). Étapes 3, 4 et 5 cochées, réglages conservés. Cliquez « Relancer depuis ce fichier ».";
}
async function uploadRetouche(file) {
  const note = $("#relance-note"); note.textContent = "Envoi de « " + file.name + " »…";
  const r = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name),
    "X-Project": encodeURIComponent(state.project.slug) }, body: file });
  const data = await r.json();
  if (!data.ok) { note.textContent = data.error; return; }
  renderFiles(data.files);
  prepareRelance();
}
function renderFiles(files, reset) {
  if (!files || !files.length) return;
  renderStart(files, reset);
  $("#bloc-fichiers").hidden = false;
  const ul = $("#fichiers"); ul.innerHTML = "";
  for (const f of files) ul.append(el("li", {}, el("a", { href: f.url + (f.name.endsWith(".html") ? "" : "?dl=1"), target: f.name.endsWith(".html") ? "_blank" : null }, f.name),
    " ", el("small", {}, (f.size / 1024).toFixed(0) + " Ko")));
}
function finish(j) {
  $("#lancer").disabled = false; startChanged();
  $("#bloc-relance").classList.remove("bloc-relance-actif");
  const r = j.result || {}; const slug = state.project.slug;
  const act = $("#actions"); act.innerHTML = "";
  if (j.status === "error") act.append(el("p", { class: "erreur" }, "Une étape a échoué : voir le journal. Les fichiers déjà produits restent utilisables."));
  const openBtn = (label, file) => el("button", { class: "bouton", onclick: async () => {
    const x = await api("/api/open", { what: "sigil", slug, file }); if (!x.ok) alert(x.error); } }, label);
  if (r.marked) act.append(openBtn("Ouvrir la version à relire dans Sigil", r.marked));
  if (r.final) act.append(openBtn("Ouvrir « " + r.final + " » dans Sigil", r.final));
  if (r.marked) act.append(el("button", { class: "bouton", title: "À faire quand la relecture est terminée et enregistrée dans Sigil",
    onclick: () => unmark(r.marked) }, "Retirer les marqueurs (relecture finie)"));
  act.append(el("button", { class: "bouton", onclick: () => api("/api/open", { what: "folder", slug }) }, "Ouvrir le dossier du projet"));
  if (r.final) act.append(el("a", { class: "bouton", href: "/files/" + slug + "/" + r.final + "?dl=1" }, "Télécharger " + r.final));
  if (r.epubcheck) act.append(el("p", { class: "check " + (r.epubcheck.errors + r.epubcheck.fatals ? "mauvais" : "bon") },
    "epubcheck (final) : " + (r.epubcheck.errors + r.epubcheck.fatals) + " erreur(s), " + r.epubcheck.warnings + " avertissement(s)"));
  if (r.toc) renderToc(r.toc);
  if (r.report) {
    const v = $("#vue-rapport"); v.innerHTML = "";
    v.append(el("p", {}, el("a", { href: "/files/" + slug + "/" + r.report, target: "_blank" }, "Ouvrir le rapport dans un nouvel onglet"),
      " (à garder ouvert à côté de Sigil)"),
      el("iframe", { class: "rapport", src: "/files/" + slug + "/" + r.report + "?t=" + Date.now(), title: "Rapport de relecture" }));
  }
}
async function unmark(file) {
  const res = await api("/api/unmark", { slug: state.project.slug, file });
  if (!res.ok) { alert(res.error); return; }
  startPolling(res.job, false);
}
function renderToc(toc) {
  const v = $("#vue-tdm"); v.innerHTML = "";
  if (!toc.entries.length) { v.append(el("p", { class: "vide" }, "Aucune table des matières trouvée.")); return; }
  v.append(el("p", {}, toc.entries.length + " entrées" + (toc.pages ? " — " + toc.pages + " numéros de page du livre papier" : "")),
    el("ul", { class: "tdm" }, toc.entries.map(([lv, t]) => el("li", { class: "niv" + lv }, t))));
}
function showTab(name) {
  document.querySelectorAll("#onglets button").forEach(b => b.setAttribute("aria-selected", b.dataset.vue === name));
  document.querySelectorAll(".vue").forEach(v => v.hidden = v.id !== "vue-" + name);
}

/* ---------- conseils pour Sigil ---------- */
function renderSigilHelp() {
  $("#vue-sigil").innerHTML = `
  <h4>Ordre de travail conseillé</h4>
  <ol>
    <li><b>Remplacements globaux d'abord.</b> Le rapport propose ceux qui valent pour tout le livre
      (« ß » → « ss », virgules collées…). Dans Sigil : Édition › Rechercher et remplacer, étendue
      « Tous les fichiers HTML », mode <i>Regex</i> quand c'est indiqué. Vérifiez sur trois ou quatre cas avant « Tout remplacer ».</li>
    <li><b>Puis les cas un par un.</b> Ouvrez la version « à relire » : chaque cas est surligné en jaune.
      Cherchez <code>a-verifier</code> (mode Normal) et utilisez « Suivant » ; le rapport, ouvert à côté,
      donne pour chaque cas le lien vers la page scannée.</li>
    <li><b>Titres manquants.</b> La section « Numérotation des chapitres » du rapport indique où un titre manque.
      Ajoutez-le en <code>&lt;h2&gt;</code>, enregistrez, puis utilisez « Relance ciblée » : les étapes 3 à 5
      sont rejouées sur le fichier enregistré et la table des matières est régénérée.</li>
    <li><b>Correcteur orthographique.</b> Ajoutez le fichier <code>…-dictionnaire.txt</code> aux dictionnaires
      utilisateur de Sigil (Préférences › Dictionnaires) : l'orthographe ancienne du livre n'est plus soulignée,
      il reste surtout les vraies coquilles.</li>
    <li><b>Pour finir.</b> Enregistrez dans Sigil, puis cliquez « Retirer les marqueurs » : le fichier
      <code>…-relu.epub</code> est prêt, contrôlé par epubcheck.</li>
  </ol>
  <h4>Bon à savoir</h4>
  <ul>
    <li>Les numéros de page du livre papier sont conservés : dans le rapport, le lien « page » ouvre la page scannée correspondante.</li>
    <li>Chaque étape écrit un nouveau fichier ; l'original n'est jamais modifié. On peut relancer avec d'autres réglages à tout moment.</li>
    <li>Rien ne s'efface du texte sans être listé dans le journal (folios retirés, paragraphes recollés, lettrines).</li>
  </ul>`;
}

init();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Lancement
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Prescel : préparer un EPUB issu d'OCR avant Sigil.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--workdir", default=os.path.join(os.path.expanduser("~"), "Prescel"),
                    help="dossier des projets (défaut : ~/Prescel)")
    ap.add_argument("--epubcheck", help="epubcheck : commande ou chemin de epubcheck.jar")
    ap.add_argument("--sigil", help="chemin de l'exécutable Sigil")
    ap.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    opts = ap.parse_args()

    CONFIG["workdir"] = os.path.abspath(os.path.expanduser(opts.workdir))
    os.makedirs(CONFIG["workdir"], exist_ok=True)
    CONFIG["epubcheck"] = find_epubcheck(opts.epubcheck)
    CONFIG["sigil"] = find_sigil(opts.sigil)

    server = ThreadingHTTPServer(("127.0.0.1", opts.port), Handler)
    url = "http://127.0.0.1:%d/" % opts.port
    print("Prescel %s — %s" % (VERSION, url))
    print("  projets   : %s" % CONFIG["workdir"])
    print("  epubcheck : %s" % (" ".join(CONFIG["epubcheck"]) if CONFIG["epubcheck"] else "non trouvé (--epubcheck)"))
    print("  Sigil     : %s" % (" ".join(CONFIG["sigil"]) if CONFIG["sigil"] else "non trouvé (--sigil)"))
    print("Ctrl+C pour arrêter.")
    if not opts.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
