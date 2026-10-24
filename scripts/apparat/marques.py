"""Marques de relecture : celles que les corrections ont rendues sans objet sont retirées ; lettre
isolée juste après un appel (reste de l'appel mal lu : « pont¹⁵ S avaler », « joieulx¹⁴ l' et »)
retirée."""
import re

# lettre(s) isolée(s) marquée(s), absente(s) des autres lectures, collée(s) à un appel ; « a », « à »,
# « y » (mots d'une lettre) sont laissés
ISOLEE = re.compile(r'(<sup class="var">\d+</sup>)\s*((?:<span class="a-verifier" title="(?:Lettres isolées|lettre '
                    r'isolée absente)[^"]*">)+)(?!(?:a|à|y)</span>)([^\W\d_]{1,2})((?:</span>)+)[\'’]?(\s*(?=[.,])|)')

SPAN = re.compile(r'<span class="a-verifier" title="([^"]*)">((?:(?!<span class="a-verifier")(?!</span>).)*)</span>', re.S)


def resolved(title, content):
    plain = re.sub(r'<sup class="var">.*?</sup>', "", content)
    plain = re.sub(r"<[^>]+>", "", plain)
    if not plain.strip() and not content.strip():
        return "vide"
    if title.startswith(("Chiffres dans un mot", "chiffre dans le récit", "chiffre collé au mot")):
        return "levée" if not re.search(r"\d", plain) else None
    if title.startswith(("Casse mélangée dans un mot", "nombre romain mal lu", "exposant d'un nombre romain")) \
            or (title.startswith("lectures en désaccord") and re.search(r"Google : [IVXLC]+", title)):
        return "levée" if "<sup>" in content else None
    if title.startswith(("Lettres isolées", "lettre isolée absente")):
        if not plain.strip():
            return "levée"          # il ne reste que l'appel
        return None
    return None


def stage(raws):
    out, log = {}, []
    for f, t in raws.items():
        def isolee(m):
            if m.group(2).count("<span") != m.group(4).count("</span>"):
                return m.group(0)
            log.append((f, "lettre isolée après un appel", m.group(3)))
            return m.group(1)
        t = ISOLEE.sub(isolee, t)
        while True:
            changed = False

            def rep(m):
                nonlocal changed
                r = resolved(m.group(1), m.group(2))
                if r:
                    changed = True
                    log.append((f, m.group(1)[:50], re.sub(r"<[^>]+>", "", m.group(2))[:30]))
                    return m.group(2)
                return m.group(0)
            t = SPAN.sub(rep, t)
            if not changed:
                break
        out[f] = t
    return out, log
