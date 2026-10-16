"""Paragraphes coupés par un bloc d'apparat : « … si s'ad-</p> <p class="variantes">…</p> <p>visa … »
→ un seul paragraphe (« s'advisa »), le bloc après lui."""
import re

PAT = re.compile(r'(<p(?: class="a-verifier")?>)((?:(?!</p>)(?!<p[ >]).)*?)</p>'
                 r'(\s*(?:<p class="variantes"[^>]*>(?:(?!</p>).)*</p>\s*)+)'
                 r'<p(?: class="a-verifier")?>(\s*(?:<a id="page-\d+"\s*/>\s*)?)((?:(?!</p>).)*)</p>', re.S)
# mot en trop signalé à la fin du premier morceau (début de l'apparat recopié par l'OCR)
TRAIL = re.compile(r'\s*<span class="a-verifier" title="mot absent de toutes les autres lectures[^"]*">[^<]*</span>\s*$')


def stage(raws):
    out, log = {}, []
    for f, t in raws.items():
        def rep(m):
            first, body1, blocks, anchor, body2 = m.group(1), m.group(2), m.group(3), m.group(4).strip(), m.group(5)
            b1 = TRAIL.sub("", body1)
            end = re.sub(r"<[^>]+>", "", b1).rstrip()
            if not end or end[-1] in ".!?»:;)":
                return m.group(0)                       # vraie fin de paragraphe
            b2 = body2.lstrip()
            if not re.match(r"[a-zà-ÿ«(]|<sup|<a ", b2):
                return m.group(0)
            if end.endswith("-") and re.match(r"[a-zà-ÿ]", b2):
                head = b1.rstrip()[:-1]
                cut = re.search(r"(\S+)$", head)
                # mot coupé : « s'ad- » + « visa » ; l'ancre de page passe devant le mot entier
                merged = head[:cut.start()] + anchor + head[cut.start():] + b2 if anchor else head + b2
            else:
                merged = b1.rstrip() + " " + (anchor + " " if anchor else "") + b2
            log.append((f, end[-30:] + " | " + re.sub(r"<[^>]+>", "", b2)[:30]))
            return first + merged + "</p>" + blocks.rstrip() + "\n  "
        out[f] = PAT.sub(rep, t)
    return out, log
