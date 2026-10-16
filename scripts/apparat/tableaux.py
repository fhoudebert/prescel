"""Prose prise pour un tableau par l'OCR (<table class="tableau"> au milieu d'une phrase) : les lignes
sont remises bout à bout et recollées aux paragraphes qui l'entourent."""
import re


def row_text(row, first):
    cells = [c for c in re.findall(r"<td>(.*?)</td>", row, re.S)]
    out = []
    for k, c in enumerate(cells):
        c = c.strip()
        # lettre isolée en tête de ligne (guillemet « mal lu) : retirée
        c = re.sub(r'^<span class="a-verifier" title="Lettres isolées \w">\w</span>\s*', "", c)
        c = re.sub(r"^a\s+(?=[A-ZÀ-Ý])", "« ", c)
        if k == 0:
            # guillemet de début de ligne (« en tête de chaque ligne d'une citation) : retiré
            c = re.sub(r"^(?:«\s*|a\s+(?=[a-zé]))", "", c) if not first else re.sub(r"^a\s+(?=[a-zé])", "", c)
        out.append(c)
    return " ".join(x for x in out if x)


def stage(raws, files=None):
    out = dict(raws)
    files = files or list(raws)
    log = []
    for f in files:
        t = out[f]
        while True:
            m = re.search(r'<table class="tableau">(.*?)</table>', t, re.S)
            if not m:
                break
            rows = re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S)
            lines = [row_text(r, k == 0) for k, r in enumerate(rows)]
            text = ""
            for ln in lines:
                if text.endswith("-") and re.match(r"(?:il|ils|elle|elles|on|je|nous|vous|y|en|là|ce)\b", ln):
                    text = text + ln                # « est- il » : trait d'union gardé
                elif text.endswith("-") and re.match(r"[a-zàâäéèêëîïôöûüç]", ln):
                    text = text[:-1] + ln            # « Lin- desée » → « Lindesée »
                else:
                    text = (text + " " + ln).strip()
            # paragraphe précédent (en sautant un bloc d'apparat) et paragraphe suivant
            before = t[:m.start()]
            prev = re.search(r"(<p(?: [^>]*)?>)((?:(?!<p[ >]).)*?)</p>(\s*(?:<p class=\"[^\"]*variantes[^\"]*\"[^>]*>(?:(?!</p>).)*</p>\s*)?)$", before, re.S)
            nxt = re.match(r"\s*<p>((?:(?!</p>).)*)</p>", t[m.end():], re.S)
            if not prev or not nxt:
                break
            body_next = re.sub(r"^«\s*", "", nxt.group(1).strip())
            merged = prev.group(1) + prev.group(2).rstrip() + " " + text
            if merged.endswith("-") and re.match(r"[a-zàâäéèêëîïôöûüç]", body_next):
                merged = merged[:-1] + body_next
            else:
                merged += " " + body_next
            block = prev.group(3).strip()
            new = merged + "</p>" + ("\n  " + block if block else "")
            s0 = prev.start()
            e0 = m.end() + nxt.end()
            log.append((f, re.sub(r"<[^>]+>", "", text)[:80]))
            t = t[:s0] + new + t[e0:]
        out[f] = t
    return out, log
