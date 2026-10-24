"""EPUB maître : paragraphes, page imprimée de chaque position, blocs d'apparat, appels."""
import html, re, zipfile

OFFSET = 4          # ancre page-N = page imprimée N-4
FILES = []          # fichiers du texte, dans l'ordre (rempli par load)


def load(path):
    z = zipfile.ZipFile(path)
    FILES[:] = sorted(n for n in z.namelist() if re.match(r"OEBPS/Text/texte-\d+\.xhtml$", n))
    return z, {f: z.read(f).decode("utf-8") for f in FILES}


def paragraphs(raws):
    """[(f, start, end, attrs, inner_start, inner_end, page_at_start, pages_inside)]"""
    out = []
    for f in FILES:
        t = raws[f]
        page = None
        anchors = [(m.start(), int(m.group(1)) - OFFSET) for m in re.finditer(r'id="page-(\d+)"', t)]
        ai = 0
        for m in re.finditer(r"<(p|h\d)(\s[^>]*)?>(.*?)</\1>", t, re.S):
            while ai < len(anchors) and anchors[ai][0] < m.start():
                page = anchors[ai][1]
                ai += 1
            inside = [p for a, p in anchors if m.start() <= a < m.end()]
            attrs = m.group(2) or ""
            cls = re.search(r'class="([^"]*)"', attrs)
            title = re.search(r'title="p\. (\d+)"', attrs)
            out.append(dict(f=f, s=m.start(), e=m.end(), tag=m.group(1), attrs=attrs, cls=cls.group(1) if cls else "",
                            title=int(title.group(1)) if title else None, i0=m.start(3), i1=m.end(3),
                            page=page, inside=inside))
    return out


def plain(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))
