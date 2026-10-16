"""Réglages de la chaîne (fixés par epub_apparat_scan.py)."""
import importlib.util, json, re, zipfile, html

EPUB = None         # EPUB maître
SCAN = {}           # lecture de la numérisation (scan_apparat.py), par vue
APPARAT = None      # apparat relu à vue (fichier texte)
GOOGLE = {}         # autre OCR de la même édition : {page imprimée: {"body": [...], "fn": [...]}}
WORDS = set()       # liste de mots français
CORR = None         # module de corrections du volume


def google_pages(path):
    """notes de bas de page et paragraphes d'un EPUB Google Livres, par page imprimée."""
    z = zipfile.ZipFile(path)
    opf_name = next(n for n in z.namelist() if n.endswith(".opf"))
    root = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
    opf = z.read(opf_name).decode()
    items = {a: b for b, a in re.findall(r'<item[^>]*href="([^"]+)"[^>]*id="([^"]+)"', opf)}
    items.update(dict(re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf)))
    pages, cur = {}, None
    for idref in re.findall(r'<itemref[^>]*idref="([^"]+)"', opf):
        h = items.get(idref)
        if not h or not h.endswith(".xml"):
            continue
        t = z.read(root + h).decode("utf-8", "replace")
        for m in re.finditer(r"<a class='page'\s+id='GBS\.P([AR])(\d+)'|<p class='gtxt_(\w+)'[^>]*>(.*?)</p>", t, re.S):
            if m.group(2):
                cur = int(m.group(2)) if m.group(1) == "A" else None
                continue
            if cur is None:
                continue
            txt = html.unescape(re.sub(r"<[^>]+>", "", m.group(4)))
            pages.setdefault(str(cur), {"body": [], "fn": []})["body" if m.group(3) != "footnote" else "fn"].append(txt)
    return pages


def configure(epub, scan, apparat, corrections, google=None, words=None, offset=None):
    global EPUB, SCAN, APPARAT, GOOGLE, WORDS, CORR
    from . import lecture, texte
    EPUB, APPARAT = epub, apparat
    SCAN = json.load(open(scan, encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("corrections_volume", corrections)
    CORR = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(CORR)
    lecture.set_map(getattr(CORR, "VUES", {}))
    GOOGLE = google_pages(google) if google else {}
    WORDS = set(words or ())
    if offset is not None:
        texte.OFFSET = offset
