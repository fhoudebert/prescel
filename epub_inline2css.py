#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_inline2css.py — Transforme les attributs style="..." inline d'un EPUB
en classes CSS regroupées dans une feuille dédiée.

  * parcourt tous les .xhtml / .html / .htm de l'archive ;
  * normalise chaque style="..." et crée UNE classe par combinaison identique ;
  * remplace style="..." par class="..." (fusion avec un class existant) ;
  * écrit la feuille <dossier OPF>/Styles/inline-styles.css ;
  * ajoute <link rel="stylesheet"> dans les XHTML concernés ;
  * déclare la feuille dans le <manifest> de l'OPF ;
  * ne modifie rien d'autre : le texte des fichiers est édité chirurgicalement
    (pas de re-sérialisation XML), les autres entrées sont recopiées telles
    quelles, « mimetype » reste en tête et non compressé.

Aucune dépendance externe (Python 3.8+).

Usage :
  python3 epub_inline2css.py livre.epub                 # modifie en place
  python3 epub_inline2css.py livre.epub -o propre.epub  # écrit ailleurs
  python3 epub_inline2css.py livre.epub --dry-run       # statistiques seules
"""

import argparse
import datetime
import html
import os
import posixpath
import re
import shutil
import sys
import tempfile
import zipfile
from urllib.parse import quote, unquote

CONTAINER_PATH = "META-INF/container.xml"
XHTML_EXTS = (".xhtml", ".html", ".htm")

# Découpe du document en jetons : on ne touche qu'aux balises ouvrantes,
# jamais aux commentaires, CDATA, instructions, ni au contenu script/style.
TOKEN_RE = re.compile(
    r"""
      (?P<skip><!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!DOCTYPE[^>]*>)
    | (?P<raw><(?P<rawname>script|style)\b(?:[^>"']|"[^"]*"|'[^']*')*(?<!/)>.*?</(?P=rawname)\s*>)
    | (?P<tag><[A-Za-z][^\s/>]*(?:\s+[^\s=/>]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*\s*/?>)
    """,
    re.S | re.I | re.X,
)
TAGNAME_RE = re.compile(r"<[^\s/>]+")
ATTR_RE = re.compile(
    r"""(\s+)([^\s=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?"""
)
CLASS_TOKEN_RE = re.compile(
    r"""\sclass\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I
)


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def decode_text(data):
    """Décode un fichier texte en respectant BOM et déclaration XML."""
    bom = b""
    if data.startswith(b"\xef\xbb\xbf"):
        bom, data = data[:3], data[3:]
        return data.decode("utf-8"), "utf-8", bom
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    enc = m.group(1).decode("ascii") if m else "utf-8"
    return data.decode(enc), enc, bom


def encode_text(text, enc, bom):
    return bom + text.encode(enc)


def attr_value(raw):
    """Valeur brute d'attribut (avec guillemets éventuels) -> texte."""
    if raw is None:
        return ""
    if raw[:1] in "\"'":
        raw = raw[1:-1]
    return raw


def split_declarations(style):
    """Découpe sur ';' en ignorant ceux entre guillemets ou parenthèses
    (ex. url(data:image/png;base64,...))."""
    parts, buf, depth, quote_char = [], [], 0, None
    for ch in style:
        if quote_char:
            buf.append(ch)
            if ch == quote_char:
                quote_char = None
        elif ch in "\"'":
            quote_char = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def normalize_style(style_text, sort_props=False, strip_important=False):
    """Retourne un tuple ((propriété, valeur), ...) canonique."""
    style = html.unescape(style_text)
    style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
    decls = []
    for part in split_declarations(style):
        if ":" not in part:
            continue
        prop, val = part.split(":", 1)
        prop = prop.strip().lower()
        val = " ".join(val.split())
        if strip_important:
            val = re.sub(r"\s*!\s*important\s*$", "", val, flags=re.I)
        if prop and val:
            decls.append((prop, val))
    if sort_props:
        decls.sort(key=lambda d: d[0])  # tri stable
    return tuple(decls)


def rel_href(from_file, to_file):
    base = posixpath.dirname(from_file) or "."
    return quote(posixpath.relpath(to_file, base), safe="/")


def resolve(base_file, href):
    """href relatif à base_file -> chemin dans l'archive."""
    href = unquote(href.split("#", 1)[0])
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_file), href))


# --------------------------------------------------------------------------
# Lecture de l'OPF
# --------------------------------------------------------------------------

def find_opf(zin):
    container = zin.read(CONTAINER_PATH).decode("utf-8", "replace")
    m = re.search(r"""full-path\s*=\s*["']([^"']+)["']""", container)
    if not m:
        sys.exit("Erreur : chemin de l'OPF introuvable dans container.xml")
    return m.group(1)


def get_attr(tag, name):
    m = re.search(r"""\s%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % re.escape(name), tag, re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def manifest_items(opf_text):
    return [m for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf_text)]


# --------------------------------------------------------------------------
# Traitement d'un document XHTML
# --------------------------------------------------------------------------

class Registry:
    """Associe chaque combinaison de déclarations à un nom de classe."""

    def __init__(self, prefix, reserved):
        self.prefix = prefix
        self.reserved = set(reserved)
        self.by_key = {}
        self.counter = 0

    def add_existing(self, name, key):
        if key and key not in self.by_key:
            self.by_key[key] = name
            self.reserved.add(name)
            m = re.fullmatch(re.escape(self.prefix) + r"(\d+)", name)
            if m:
                self.counter = max(self.counter, int(m.group(1)))

    def name_for(self, key):
        if key not in self.by_key:
            while True:
                self.counter += 1
                name = "%s%d" % (self.prefix, self.counter)
                if name not in self.reserved:
                    break
            self.reserved.add(name)
            self.by_key[key] = name
        return self.by_key[key]


def rewrite_tag(tag, registry, opts, stats):
    name_m = TAGNAME_RE.match(tag)
    attrs = list(ATTR_RE.finditer(tag, name_m.end()))
    style_m = class_m = None
    for a in attrs:
        low = a.group(2).lower()
        if low == "style" and style_m is None:
            style_m = a
        elif low == "class" and class_m is None:
            class_m = a
    if style_m is None:
        return tag

    key = normalize_style(attr_value(style_m.group(3)), opts.sort_properties)
    stats["styles"] += 1
    new_class = registry.name_for(key) if key else None

    # Reconstruction : on retire l'attribut style, on met à jour / insère class.
    out, pos = [], 0
    edits = []
    if class_m is not None:
        edits.append(class_m)
    edits.append(style_m)
    edits.sort(key=lambda a: a.start())

    for a in edits:
        out.append(tag[pos:a.start()])
        if a is style_m:
            if new_class and class_m is None:
                out.append('%sclass="%s"' % (a.group(1), new_class))
            # sinon : style supprimé purement et simplement
        else:  # attribut class existant
            raw = a.group(3)
            q = raw[0] if raw and raw[0] in "\"'" else '"'
            classes = attr_value(raw).split()
            if new_class and new_class not in classes:
                classes.append(new_class)
            out.append("%sclass=%s%s%s" % (a.group(1), q, " ".join(classes), q))
        pos = a.end()
    out.append(tag[pos:])
    return "".join(out)


def process_document(text, registry, opts, stats):
    before = stats["styles"]

    def repl(m):
        if m.group("tag"):
            return rewrite_tag(m.group("tag"), registry, opts, stats)
        return m.group(0)

    new_text = TOKEN_RE.sub(repl, text)
    return new_text, stats["styles"] - before


def add_stylesheet_link(text, doc_path, css_path):
    """Ajoute le <link> avant </head> s'il n'est pas déjà présent."""
    for m in re.finditer(r"<link\b[^>]*>", text, re.I):
        href = get_attr(m.group(0), "href")
        if href and resolve(doc_path, href) == css_path:
            return text, False
    head_end = re.search(r"</head\s*>", text, re.I)
    if not head_end:
        return text, None
    # Reprend l'indentation de la ligne de </head> (+ un niveau).
    line_start = text.rfind("\n", 0, head_end.start()) + 1
    indent = text[line_start:head_end.start()]
    indent = indent if indent.strip() == "" else ""
    link = '<link href="%s" rel="stylesheet" type="text/css"/>' % rel_href(doc_path, css_path)
    if indent or line_start == head_end.start():
        insertion = "  " + link + "\n" + indent
    else:
        insertion = link
    pos = head_end.start()
    return text[:pos] + insertion + text[pos:], True


def add_to_manifest(opf_text, opf_path, css_path):
    items = manifest_items(opf_text)
    ids = set()
    for m in items:
        href = get_attr(m.group(0), "href")
        if href and resolve(opf_path, href) == css_path:
            return opf_text, False
        i = get_attr(m.group(0), "id")
        if i:
            ids.add(i)
    end = re.search(r"</((?:[\w-]+:)?)manifest\s*>", opf_text)
    if not end:
        sys.exit("Erreur : balise </manifest> introuvable dans l'OPF")
    prefix = end.group(1)
    item_id, n = "inline-styles-css", 1
    while item_id in ids:
        n += 1
        item_id = "inline-styles-css-%d" % n
    href = rel_href(opf_path, css_path)
    item = '<%sitem id="%s" href="%s" media-type="text/css"/>' % (prefix, item_id, href)

    # Insère juste après le dernier <item>, avec la même indentation.
    if items:
        last = items[-1]
        ls = opf_text.rfind("\n", 0, last.start()) + 1
        indent = opf_text[ls:last.start()]
        indent = indent if indent.strip() == "" else ""
        pos = last.end()
        new = opf_text[:pos] + "\n" + indent + item + opf_text[pos:]
    else:
        pos = end.start()
        new = opf_text[:pos] + item + opf_text[pos:]
    return new, True


# --------------------------------------------------------------------------
# Feuille CSS
# --------------------------------------------------------------------------

def read_existing_css(text, registry, opts):
    """Réutilise les classes d'une feuille déjà générée (relance idempotente)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for m in re.finditer(r"\.([A-Za-z_][\w-]*)\s*\{([^}]*)\}", text):
        key = normalize_style(m.group(2), opts.sort_properties,
                              strip_important=opts.important)
        registry.add_existing(m.group(1), key)


def build_css(registry, opts):
    lines = [
        "/* Généré par epub_inline2css.py : ex-attributs style=\"...\" inline. */",
        "",
    ]
    items = sorted(registry.by_key.items(), key=lambda kv: natural_key(kv[1]))
    for key, name in items:
        lines.append(".%s {" % name)
        for prop, val in key:
            if opts.important and not re.search(r"!\s*important\s*$", val, re.I):
                val += " !important"
            lines.append("  %s: %s;" % (prop, val))
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Remplace les style=\"...\" inline d'un EPUB par des classes CSS.")
    ap.add_argument("epub", help="fichier EPUB à nettoyer")
    ap.add_argument("-o", "--output",
                    help="EPUB de sortie (défaut : modification en place)")
    ap.add_argument("--css-path", default="Styles/inline-styles.css",
                    help="chemin de la feuille, relatif à l'OPF "
                         "(défaut : Styles/inline-styles.css)")
    ap.add_argument("--prefix", default="is",
                    help="préfixe des noms de classes (défaut : is → is1, is2…)")
    ap.add_argument("--sort-properties", action="store_true",
                    help="trier les propriétés pour fusionner davantage de "
                         "combinaisons (attention : peut changer le rendu si "
                         "un raccourci et sa forme longue coexistent)")
    ap.add_argument("--important", action="store_true",
                    help="ajouter !important pour conserver la priorité "
                         "qu'avaient les styles inline")
    ap.add_argument("--backup", action="store_true",
                    help="en mode « en place », garder une copie .bak")
    ap.add_argument("--dry-run", action="store_true",
                    help="analyser et afficher les statistiques sans écrire")
    opts = ap.parse_args()

    src = opts.epub
    if not zipfile.is_zipfile(src):
        sys.exit("Erreur : %s n'est pas une archive ZIP/EPUB" % src)

    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = [i.filename for i in infos]
        opf_path = find_opf(zin)
        opf_dir = posixpath.dirname(opf_path)
        css_path = posixpath.normpath(posixpath.join(opf_dir, opts.css_path))

        # Documents à traiter : manifeste XHTML + tout .xhtml/.html de l'archive.
        opf_raw = zin.read(opf_path)
        opf_text, opf_enc, opf_bom = decode_text(opf_raw)
        docs = []
        for m in manifest_items(opf_text):
            mt = (get_attr(m.group(0), "media-type") or "").lower()
            href = get_attr(m.group(0), "href")
            if href and mt in ("application/xhtml+xml", "text/html"):
                p = resolve(opf_path, href)
                if p in names and p not in docs:
                    docs.append(p)
        for n in names:
            if n.lower().endswith(XHTML_EXTS) and n not in docs:
                docs.append(n)

        # Classes déjà utilisées dans le livre : à ne pas réutiliser.
        decoded = {}
        reserved = set()
        for d in docs:
            try:
                decoded[d] = decode_text(zin.read(d))
            except (UnicodeDecodeError, LookupError) as e:
                print("Avertissement : %s ignoré (%s)" % (d, e), file=sys.stderr)
                continue
            for m in CLASS_TOKEN_RE.finditer(decoded[d][0]):
                reserved.update((m.group(1) or m.group(2) or "").split())

        registry = Registry(opts.prefix, reserved)
        if css_path in names:
            read_existing_css(decode_text(zin.read(css_path))[0], registry, opts)

        stats = {"styles": 0}
        new_data = {}
        touched = []
        no_head = []
        for d, (text, enc, bom) in decoded.items():
            new_text, count = process_document(text, registry, opts, stats)
            if count == 0:
                continue
            new_text, added = add_stylesheet_link(new_text, d, css_path)
            if added is None:
                no_head.append(d)
            new_data[d] = encode_text(new_text, enc, bom)
            touched.append((d, count))

        if not touched:
            print("Aucun attribut style=\"...\" trouvé : EPUB inchangé.")
            return

        new_opf, _ = add_to_manifest(opf_text, opf_path, css_path)
        if new_opf != opf_text:
            new_data[opf_path] = encode_text(new_opf, opf_enc, opf_bom)
        css_bytes = build_css(registry, opts).encode("utf-8")
        if css_path in names:
            new_data[css_path] = css_bytes  # relance : feuille mise à jour

        print("Documents modifiés : %d / %d" % (len(touched), len(decoded)))
        for d, c in touched:
            print("  %-50s %6d style(s)" % (d, c))
        print("Attributs style remplacés : %d" % stats["styles"])
        print("Classes CSS distinctes    : %d" % len(registry.by_key))
        print("Feuille                   : %s" % css_path)
        for d in no_head:
            print("Avertissement : pas de <head> dans %s, lien non ajouté" % d,
                  file=sys.stderr)
        if opts.dry_run:
            print("(--dry-run : rien n'a été écrit)")
            return

        # Réécriture de l'archive : mimetype d'abord, non compressé.
        out_path = opts.output or src
        out_dir = os.path.dirname(os.path.abspath(out_path))
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=out_dir)
        os.close(fd)
        try:
            ordered = sorted(infos, key=lambda i: i.filename != "mimetype")
            with zipfile.ZipFile(tmp, "w") as zout:
                for info in ordered:
                    data = new_data.get(info.filename)
                    if data is None:
                        data = zin.read(info)
                    if info.filename == "mimetype":
                        info.compress_type = zipfile.ZIP_STORED
                    zout.writestr(info, data, compress_type=info.compress_type)
                if css_path not in names:
                    zi = zipfile.ZipInfo(css_path,
                                         datetime.datetime.now().timetuple()[:6])
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = 0o644 << 16
                    zout.writestr(zi, css_bytes)
        except BaseException:
            os.unlink(tmp)
            raise

    if not opts.output and opts.backup:
        shutil.copy2(src, src + ".bak")
    shutil.copymode(src, tmp)   # mkstemp crée en 0600 : on reprend les droits de l'original
    os.replace(tmp, out_path)
    print("EPUB écrit : %s" % out_path)


if __name__ == "__main__":
    main()
