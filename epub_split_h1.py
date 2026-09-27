#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_split_h1.py — Découpe les gros fichiers XHTML d'un EPUB à chaque <h1>
en gardant l'EPUB fonctionnel.

  * chaque <h1> ouvre un nouveau fichier (livre.xhtml, livre_002.xhtml, …) ;
    le premier morceau garde le nom d'origine, donc les liens sans ancre
    restent valides ;
  * si le <h1> est imbriqué (<div class="chapitre"><h1>…), les éléments
    parents sont refermés en fin de morceau et rouverts à l'identique
    (mêmes attributs) au début du suivant : le style est conservé ;
  * le <head> est recopié tel quel dans chaque morceau (CSS, métadonnées) ;
  * manifest : nouveaux <item> insérés après l'original (propriétés EPUB 3
    svg / mathml / scripted recalculées pour chaque morceau) ;
  * spine : nouveaux <itemref> insérés après l'original, dans l'ordre ;
  * liens réécrits partout (XHTML, nav EPUB 3, toc.ncx, <guide> de l'OPF) :
    toute cible « livre.xhtml#ancre » ou « #ancre » pointe vers le morceau
    qui contient réellement cette ancre (id="…" ou name="…") ;
  * le reste de l'EPUB n'est pas touché (édition textuelle chirurgicale,
    pas de re-sérialisation XML ; « mimetype » en tête, non compressé).

Aucune dépendance externe (Python 3.8+).

Usage :
  python3 epub_split_h1.py livre.epub                     # en place
  python3 epub_split_h1.py livre.epub -o decoupe.epub
  python3 epub_split_h1.py livre.epub --only Text/livre.xhtml --titles
  python3 epub_split_h1.py livre.epub --tag h2 --dry-run
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
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

TOKEN_RE = re.compile(
    r"""
      (?P<skip><!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!DOCTYPE[^>]*>)
    | (?P<raw><(?P<rawname>script|style)\b(?:[^>"']|"[^"]*"|'[^']*')*(?<!/)>.*?</(?P=rawname)\s*>)
    | (?P<end></(?P<endname>[A-Za-z][^\s/>]*)\s*>)
    | (?P<tag><(?P<name>[A-Za-z][^\s/>]*)(?:\s+[^\s=/>]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*\s*(?P<selfclose>/?)>)
    """,
    re.S | re.I | re.X,
)
ATTR_RE = re.compile(r"""(\s+)([^\s=/>]+)(?:(\s*=\s*)("[^"]*"|'[^']*'|[^\s"'>]+))?""")
BODY_OPEN_RE = re.compile(r"""<(?:[\w-]+:)?body\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.I)
BODY_CLOSE_RE = re.compile(r"</(?:[\w-]+:)?body\s*>", re.I)
MEDIA_RE = re.compile(r"<(?:[\w-]+:)?(?:img|image|svg|object|video|audio|table|hr|iframe|math)\b", re.I)
LINK_ATTRS = {"href", "xlink:href", "src"}


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8", data[:3]
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([\w.:-]+)["']""", data)
    enc = m.group(1).decode("ascii") if m else "utf-8"
    return data.decode(enc), enc, b""


def encode_text(text, enc, bom):
    return bom + text.encode(enc, "xmlcharrefreplace")


def local(name):
    return name.split(":")[-1].lower()


def resolve(base_file, href):
    href = unquote(href)
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_file), href))


def rel_href(from_file, to_file):
    base = posixpath.dirname(from_file) or "."
    return quote(posixpath.relpath(to_file, base), safe="/")


def get_attr(tag, name):
    m = re.search(r"""\s%s\s*=\s*(?:"([^"]*)"|'([^']*)')""" % re.escape(name), tag, re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def set_attr(tag, name, value):
    """Remplace / ajoute / supprime (value=None) un attribut dans une balise."""
    m = re.search(r"""(\s+)(%s)(\s*=\s*)("[^"]*"|'[^']*')""" % re.escape(name), tag)
    if m:
        if value is None:
            return tag[:m.start()] + tag[m.end():]
        return tag[:m.start()] + '%s%s%s"%s"' % (m.group(1), m.group(2), m.group(3), value) + tag[m.end():]
    if value is None:
        return tag
    end = len(tag) - (2 if tag.endswith("/>") else 1)
    return tag[:end].rstrip() + ' %s="%s"' % (name, value) + tag[end:]


def line_indent(text, pos):
    ls = text.rfind("\n", 0, pos) + 1
    ind = text[ls:pos]
    return ind if ind.strip() == "" else ""


def find_opf(zin):
    c = zin.read(CONTAINER_PATH).decode("utf-8", "replace")
    m = re.search(r"""full-path\s*=\s*["']([^"']+)["']""", c)
    if not m:
        sys.exit("Erreur : chemin de l'OPF introuvable dans container.xml")
    return m.group(1)


# --------------------------------------------------------------------------
# Découpage d'un document
# --------------------------------------------------------------------------

def is_meaningful(fragment):
    frag = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
    if MEDIA_RE.search(frag):
        return True
    txt = html.unescape(re.sub(r"<[^>]*>", "", frag))
    return txt.strip() != ""


def heading_text(text, pos, target):
    m = re.compile(r"<(?:[\w-]+:)?(?:%s)\b[^>]*>(.*?)</(?:[\w-]+:)?(?:%s)\s*>" % (target, target),
                   re.S | re.I).match(text, pos)
    if not m:
        return None
    t = html.unescape(re.sub(r"<[^>]*>", " ", m.group(1)))
    t = " ".join(t.split())
    return html.escape(t, quote=False) or None


def split_document(text, target, is_html, text_filter=None):
    """Retourne une liste de (contenu_complet, contenu_body, titre_h) ou None."""
    bo = BODY_OPEN_RE.search(text)
    closes = list(BODY_CLOSE_RE.finditer(text))
    if not bo or not closes:
        return None
    bc = closes[-1]
    b_start, b_end = bo.end(), bc.start()

    stack, cuts = [], []
    for m in TOKEN_RE.finditer(text, b_start, b_end):
        if m.group("tag"):
            name = m.group("name")
            ln = local(name)
            if ln in target.split("|") and (text_filter is None or
                                 text_filter.search(heading_text(text, m.start(), target) or "")):
                cuts.append((m.start(), list(stack)))
            if not m.group("selfclose") and not (is_html and ln in VOID):
                stack.append((name, m.group("tag")))
        elif m.group("end"):
            ln = local(m.group("endname"))
            for i in range(len(stack) - 1, -1, -1):
                if local(stack[i][0]) == ln:
                    del stack[i:]
                    break

    if not cuts:
        return None
    # Pas de morceau vide avant le premier titre.
    if not is_meaningful(text[b_start:cuts[0][0]]):
        cuts = cuts[1:]
    if not cuts:
        return None

    prefix, suffix = text[:b_start], text[b_end:]

    def closing(st):
        return "".join("</%s>" % name for name, _ in reversed(st))

    def reopening(st):
        return "".join(tag for _, tag in st)

    bounds = [(b_start, [], None)] + [(pos, st, pos) for pos, st in cuts]
    parts = []
    for i, (start, st, hpos) in enumerate(bounds):
        if i + 1 < len(bounds):
            stop, next_st = bounds[i + 1][0], bounds[i + 1][1]
            body = reopening(st) + text[start:stop] + closing(next_st) + "\n"
        else:
            body = reopening(st) + text[start:b_end]
        # Le premier morceau commence-t-il lui-même par le titre ?
        if hpos is None:
            lead = re.match(r"(?:\s|<[^>]*>)*?(?=<(?:[\w-]+:)?(?:%s)\b)" % target, text[start:], re.I)
            if lead and not is_meaningful(lead.group(0)):
                hpos = start + lead.end()
        title = heading_text(text, hpos, target) if hpos is not None else None
        own = text[start:stop] if i + 1 < len(bounds) else text[start:b_end]
        parts.append((prefix + body + suffix, own, title))
    return parts


def collect_ids(fragment):
    ids = []
    for m in TOKEN_RE.finditer(fragment):
        if m.group("tag"):
            for a in ATTR_RE.finditer(m.group("tag")):
                if a.group(2).lower() in ("id", "name") and a.group(4):
                    v = a.group(4)
                    ids.append(v[1:-1] if v[:1] in "\"'" else v)
    return ids


def set_title(doc, title):
    return re.sub(r"(<(?:[\w-]+:)?title\b[^>]*>).*?(</(?:[\w-]+:)?title\s*>)",
                  lambda m: m.group(1) + title + m.group(2), doc, count=1, flags=re.S | re.I)


# --------------------------------------------------------------------------
# Réécriture des liens
# --------------------------------------------------------------------------

def rewrite_links(text, doc_path, orig_of_doc, splits):
    """doc_path : chemin du document ; orig_of_doc : fichier d'origine si le
    document est un morceau (sinon None) ; splits : orig -> idmap."""

    def fix(raw):
        value = html.unescape(raw)
        if "#" not in value:
            return None
        path, frag = value.split("#", 1)
        if not path:
            target_file = orig_of_doc or doc_path
        else:
            if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", path) or path.startswith("//"):
                return None
            target_file = resolve(doc_path, path)
        if target_file not in splits:
            return None
        new_file = splits[target_file].get(unquote(frag), target_file)
        current = doc_path if not path else target_file
        if new_file == current:
            return None
        new = "#" + frag if new_file == doc_path else rel_href(doc_path, new_file) + "#" + frag
        return html.escape(new, quote=True)

    def fix_tag(tag):
        out, pos, changed = [], 0, False
        for a in ATTR_RE.finditer(tag, re.match(r"<[^\s/>]+", tag).end()):
            if a.group(2).lower() in LINK_ATTRS and a.group(4):
                raw = a.group(4)
                q = raw[0] if raw[:1] in "\"'" else '"'
                new = fix(raw[1:-1] if raw[:1] in "\"'" else raw)
                if new is not None:
                    out.append(tag[pos:a.start(4)] + q + new + q)
                    pos, changed = a.end(4), True
        if not changed:
            return tag
        out.append(tag[pos:])
        return "".join(out)

    return TOKEN_RE.sub(lambda m: fix_tag(m.group("tag")) if m.group("tag") else m.group(0), text)


# --------------------------------------------------------------------------
# OPF
# --------------------------------------------------------------------------

def recompute_properties(orig_props, content, epub3):
    if not epub3:
        return orig_props
    props = [p for p in (orig_props or "").split()
             if p not in ("svg", "mathml", "scripted", "remote-resources")]
    if re.search(r"<(?:[\w-]+:)?svg\b", content):
        props.append("svg")
    if re.search(r"<(?:[\w-]+:)?math\b", content):
        props.append("mathml")
    if re.search(r"<script\b", content, re.I):
        props.append("scripted")
    if "remote-resources" in (orig_props or "") and \
            re.search(r"""\s(?:src|xlink:href)\s*=\s*["']https?:""", content):
        props.append("remote-resources")
    return " ".join(props) or None


def update_opf(opf_text, opf_path, plans, epub3):
    """plans : liste de (orig_path, [chemins des morceaux], [contenus])."""
    all_ids = set(re.findall(r"""\sid\s*=\s*["']([^"']+)["']""", opf_text))
    for orig, paths, contents in plans:
        item_m = None
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf_text):
            href = get_attr(m.group(0), "href")
            if href and resolve(opf_path, href) == orig:
                item_m = m
                break
        if not item_m:
            print("Avertissement : %s absent du manifest" % orig, file=sys.stderr)
            continue
        item_tag = item_m.group(0)
        orig_id = get_attr(item_tag, "id")
        orig_props = get_attr(item_tag, "properties")

        new_items, new_ids = [], []
        first_tag = set_attr(item_tag, "properties",
                             recompute_properties(orig_props, contents[0], epub3))
        for path, content in zip(paths[1:], contents[1:]):
            n = 2
            base = orig_id or "part"
            nid = "%s_%03d" % (base, len(new_ids) + 2)
            while nid in all_ids:
                n += 1
                nid = "%s_%03d_%d" % (base, len(new_ids) + 2, n)
            all_ids.add(nid)
            new_ids.append(nid)
            t = set_attr(item_tag, "id", nid)
            t = set_attr(t, "href", rel_href(opf_path, path))
            t = set_attr(t, "properties", recompute_properties(orig_props, content, epub3))
            new_items.append(t)
        ind = line_indent(opf_text, item_m.start())
        sep = ("\n" + ind) if ind or opf_text[item_m.start() - 1:item_m.start()] == "\n" else ""
        opf_text = (opf_text[:item_m.start()] + first_tag +
                    "".join(sep + t for t in new_items) + opf_text[item_m.end():])

        # Spine
        ref_m = None
        for m in re.finditer(r"<(?:[\w-]+:)?itemref\b[^>]*>", opf_text):
            if get_attr(m.group(0), "idref") == orig_id:
                ref_m = m
                break
        if ref_m:
            ind = line_indent(opf_text, ref_m.start())
            sep = ("\n" + ind) if ind or opf_text[ref_m.start() - 1:ref_m.start()] == "\n" else ""
            refs = "".join(sep + set_attr(ref_m.group(0), "idref", i) for i in new_ids)
            opf_text = opf_text[:ref_m.end()] + refs + opf_text[ref_m.end():]
        else:
            print("Avertissement : %s absent du spine" % orig, file=sys.stderr)
    return opf_text


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Découpe les XHTML d'un EPUB à chaque titre (h1 par défaut).")
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", help="EPUB de sortie (défaut : en place)")
    ap.add_argument("--tag", default="h1",
                    help="balise(s) de découpe, séparées par des virgules (défaut : h1 ; ex. h1,h2)")
    ap.add_argument("--only", action="append", default=[],
                    help="ne découper que ce fichier (chemin dans l'archive, "
                         "relatif à l'OPF, ou nom seul) ; option répétable")
    ap.add_argument("--match", metavar="REGEX",
                    help="ne couper qu'aux titres dont le texte correspond "
                         "(ex. --tag h2 --match '^(CHAPITRE|TABLE)')")
    ap.add_argument("--min-parts", type=int, default=2,
                    help="ne découper que si on obtient au moins N morceaux (défaut : 2)")
    ap.add_argument("--titles", action="store_true",
                    help="mettre le texte du titre dans <title> de chaque morceau")
    ap.add_argument("--backup", action="store_true", help="garder une copie .bak (mode en place)")
    ap.add_argument("--dry-run", action="store_true", help="afficher le plan sans écrire")
    opts = ap.parse_args()
    target = "|".join(t.strip().lower() for t in opts.tag.split(",") if t.strip())
    text_filter = re.compile(opts.match) if opts.match else None

    src = opts.epub
    if not zipfile.is_zipfile(src):
        sys.exit("Erreur : %s n'est pas une archive ZIP/EPUB" % src)

    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        names = set(i.filename for i in infos)
        opf_path = find_opf(zin)
        opf_text, opf_enc, opf_bom = decode_text(zin.read(opf_path))
        ver = re.search(r"""<(?:[\w-]+:)?package\b[^>]*\sversion\s*=\s*["']([^"']+)""", opf_text)
        epub3 = bool(ver and ver.group(1).startswith("3"))

        # Documents du manifest : types, et candidats (dans le spine, pas le nav).
        items = {}
        for m in re.finditer(r"<(?:[\w-]+:)?item\b[^>]*>", opf_text):
            href = get_attr(m.group(0), "href")
            if href:
                items[resolve(opf_path, href)] = (
                    (get_attr(m.group(0), "media-type") or "").lower(),
                    get_attr(m.group(0), "properties") or "",
                    get_attr(m.group(0), "id"))
        spine_ids = re.findall(r"""<(?:[\w-]+:)?itemref\b[^>]*\sidref\s*=\s*["']([^"']+)""", opf_text)
        by_id = {v[2]: k for k, v in items.items()}
        candidates = [by_id[i] for i in spine_ids if i in by_id]
        candidates = [p for p in candidates
                      if items[p][0] in ("application/xhtml+xml", "text/html")
                      and "nav" not in items[p][1].split()]
        if opts.only:
            wanted = set()
            for o in opts.only:
                o = o.strip("/")
                for p in candidates:
                    if p == o or p == posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), o)) \
                            or posixpath.basename(p) == o:
                        wanted.add(p)
            candidates = [p for p in candidates if p in wanted]

        # Découpage
        new_data, new_files = {}, {}     # new_files : orig -> [(chemin, bytes)]
        splits, part_of, plans = {}, {}, []
        for path in candidates:
            try:
                text, enc, bom = decode_text(zin.read(path))
            except (UnicodeDecodeError, LookupError) as e:
                print("Avertissement : %s ignoré (%s)" % (path, e), file=sys.stderr)
                continue
            is_html = not path.lower().endswith(".xhtml") and items[path][0] == "text/html"
            parts = split_document(text, target, is_html, text_filter)
            if not parts or len(parts) < max(2, opts.min_parts):
                continue
            base, ext = posixpath.splitext(path)
            paths, n = [path], 2
            for _ in parts[1:]:
                while "%s_%03d%s" % (base, n, ext) in names:
                    n += 1
                paths.append("%s_%03d%s" % (base, n, ext))
                n += 1
            idmap = {}
            for p, (_, own, _) in zip(paths, parts):
                for i in collect_ids(own):
                    idmap.setdefault(i, p)
            splits[path] = idmap
            docs = []
            for p, (doc, _, title) in zip(paths, parts):
                if opts.titles and title:
                    doc = set_title(doc, title)
                docs.append(doc)
                part_of[p] = path
            new_files[path] = list(zip(paths, docs))
            plans.append((path, paths, docs))
            print("%s → %d fichiers" % (path, len(paths)))
            for p, (_, _, title) in zip(paths, parts):
                print("    %-45s %s" % (p, html.unescape(title or "(début)")))
            new_files[path] = [(p, d, enc, bom) for p, d in zip(paths, docs)]

        if not plans:
            print("Aucun fichier à découper (pas de <%s> exploitable) : EPUB inchangé." % target)
            return
        if opts.dry_run:
            print("(--dry-run : rien n'a été écrit)")
            return

        # Réécriture des liens dans tous les documents textuels concernés.
        texts = {}   # chemin -> [texte, enc, bom, orig_of_doc]
        for orig, lst in new_files.items():
            for p, d, enc, bom in lst:
                texts[p] = [d, enc, bom, orig]
        for n in names:
            if n in texts or n in new_files:
                continue
            mt = items.get(n, ("",))[0]
            if n.lower().endswith(XHTML_EXTS + (".ncx",)) or mt in (
                    "application/xhtml+xml", "application/x-dtbncx+xml",
                    "application/oebps-page-map+xml"):
                try:
                    t, enc, bom = decode_text(zin.read(n))
                except (UnicodeDecodeError, LookupError):
                    continue
                texts[n] = [t, enc, bom, None]
        for p, (t, enc, bom, orig) in texts.items():
            nt = rewrite_links(t, p, orig, splits)
            if orig is not None or nt != t:
                new_data[p] = encode_text(nt, enc, bom)

        new_opf = update_opf(opf_text, opf_path, plans, epub3)
        new_opf = rewrite_links(new_opf, opf_path, None, splits)   # <guide>
        new_data[opf_path] = encode_text(new_opf, opf_enc, opf_bom)

        # Écriture de l'archive
        out_path = opts.output or src
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(os.path.abspath(out_path)))
        os.close(fd)
        try:
            ordered = sorted(infos, key=lambda i: i.filename != "mimetype")
            now = datetime.datetime.now().timetuple()[:6]
            with zipfile.ZipFile(tmp, "w") as zout:
                for info in ordered:
                    data = new_data.get(info.filename)
                    if data is None:
                        data = zin.read(info)
                    if info.filename == "mimetype":
                        info.compress_type = zipfile.ZIP_STORED
                    zout.writestr(info, data, compress_type=info.compress_type)
                    for p, _, _, _ in new_files.get(info.filename, [])[1:]:
                        zi = zipfile.ZipInfo(p, now)
                        zi.compress_type = zipfile.ZIP_DEFLATED
                        zi.external_attr = 0o644 << 16
                        zout.writestr(zi, new_data[p])
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
