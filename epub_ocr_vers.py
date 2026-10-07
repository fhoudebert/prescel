#!/usr/bin/env python3
"""Corrige les fautes d'OCR typiques d'un poème édité vers par vers (pdf_vers.py), vers par vers.

Règles tirées de la relecture du tome I de Guillaume le Maréchal, appliquées seulement aux
paragraphes de classe « vers » (jamais aux variantes ni au vocabulaire, où « d » ou « h » sont des
lettres citées) :

  guillemets   début de vers « a », « < », « <t », « t », « c », « f », « e », « o », « d »… suivi
               d'une majuscule → « ; fin de vers « D », « B », « s », « c », « r », « p », « d »,
               « > »… après une ponctuation (ou dans un vers ouvert par «) → » ; « <t », « < »
               isolés dans le vers → « ; « > » isolé → »
  li           « h », « H », « ti », « ii », « 11 », « U » isolés → li ; « ! i » → li
  l lu !       « Mo ! t » → Molt, « a ! rei » → al rei (seulement si le mot obtenu est connu)
  restitutions [nJ → [n], comper{r] → comper[r], [i] r → [i]r (mot coupé après le crochet)
  divers       numéro de vers resté en tête du vers (supprimé), fF → ff, 6i → oï, s *en → s’en, Gh → Ch,
               U dans un mot (empU → empli, si connu),
               « 0 » / « 1 » en tête de vers → O / I, marque de folio (/ (~ {f → (f

Les mots « connus » sont ceux du texte lui-même et des EPUB donnés par --vocab (deux occurrences
au moins, sans chiffre ni casse mêlée).

  python3 epub_ocr_vers.py entree.epub -o sortie.epub [--vocab autre.epub ...] [--report r.tsv]
         [--sans guillemets,li,...]
"""
import argparse
import collections
import html
import re
import zipfile

NB = "\u00a0"
L = "a-zà-ÿœæ"
U = "A-ZÀ-ÝŒÆ"
PUNCT = ".,;:?!"
REGLES = ["guillemets", "li", "l-lu", "restitutions", "divers"]

# un repère de balise : caractère privé, ni espace ni lettre
PRIV0 = 0xE000


MINUSCULES = set()                 # mots rencontrés en minuscules (donc pas des noms propres)


def mots_de(text, cnt):
    for w in re.findall(r"[%s%s]+" % (L, U), text):
        if not re.search("[%s].*[%s]" % (L, U), w) or w[0].isupper() and w[1:].islower():
            cnt[w.lower()] += 1
            if w.islower():
                MINUSCULES.add(w)


def vers_lignes(xhtml):
    """Contenus des paragraphes de vers, en texte brut."""
    for m in re.finditer(r'<p class="([^"]*)"[^>]*>(.*?)</p>', xhtml, re.S):
        if "vers" in m.group(1).split():
            yield html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))


def vocabulaire(paths):
    cnt = collections.Counter()
    for p in paths:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith((".xhtml", ".html", ".htm")):
                    t = z.read(n).decode("utf-8", "replace")
                    for l in vers_lignes(t) if "vers" in t else [html.unescape(re.sub(r"<[^>]+>", " ", t))]:
                        mots_de(l, cnt)
    return {w: n for w, n in cnt.items() if n >= 2}


class Ligne:
    """Une ligne de vers : texte, balises remplacées par des caractères privés."""

    def __init__(self, raw):
        self.tags = []

        def prot(m):
            self.tags.append(m.group(0))
            return chr(PRIV0 + len(self.tags) - 1)
        # numéro de vers et manchette entiers (leur contenu n'est pas du texte), puis les balises
        s = re.sub(r'<span class="(?:numvers|manchette)">[^<]*</span>', prot, raw)
        s = re.sub(r"<[^>]+>", prot, s)              # balises d'abord : le texte n'a pas de « < » brut
        self.s = html.unescape(s)

    def out(self):
        s = self.s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        s = re.sub("\x01([^\x02]*)\x02([^\x03]*)\x03",
                   lambda m: '<span class="a-verifier" title="%s">%s</span>' % (m.group(2), m.group(1)), s)
        return re.sub("[\ue000-\uf8ff]", lambda m: self.tags[ord(m.group(0)) - PRIV0], s)


P = "[\\s\ue000-\uf8ff]*"           # espaces et repères de balises éventuels
SP = "[ %s\u202f]" % NB


class Correcteur:
    def __init__(self, vocab, actives):
        self.v = vocab
        self.on = set(actives)
        self.log = []

    def connu(self, w, n=2):
        return self.v.get(re.sub(r"[\[\]]", "", w).lower(), 0) >= n

    def sub(self, regle, pat, rep, s, ctx, flags=0):
        def f(m):
            r = rep(m) if callable(rep) else m.expand(rep)
            if r is None or r == m.group(0):
                return m.group(0)
            self.log.append((ctx, regle, m.group(0).strip(), r.strip()))
            return r
        return re.sub(pat, f, s, flags=flags)

    def ligne(self, s, ctx, ouvert):
        """Corrige une ligne ; ouvert = un discours ouvert par « dans le vers précédent."""
        on = self.on
        if "divers" in on:
            s = self.sub("divers", r"fF", "ff", s, ctx)
            # numéro de vers imprimé resté en tête du vers (il est déjà en marge) : « 10944 E chivalchout »
            s = self.sub("divers", r"^(%s)\d(?: ?\d){2,5}%s+(?=[%s«&])" % (P, SP, U), lambda m: m.group(1), s, ctx)
            s = self.sub("divers", r"(?<![\d])6i(?=[%s]|\b)" % L, "oï", s, ctx)
            s = self.sub("divers", r"(?<=[%s])%s?\*(?=[%s])" % (L + U, SP, L), "’", s, ctx)
            s = self.sub("divers", r"\bGh(?=[aeiou])", "Ch", s, ctx)
            s = self.sub("divers", r"^(%s)([01])(?=%s[%s])" % (P, SP, L),
                         lambda m: m.group(1) + {"0": "O", "1": "I"}[m.group(2)], s, ctx)
            s = self.sub("divers", r"[({]%s?[/~](?=[%s\s\d.]|$)" % (SP, NB), "(f", s, ctx)
            s = self.sub("divers", r"\{f\b", "(f", s, ctx)
            s = self.sub("divers", r"\b([%s]*[%s])U([%s]*)" % (L + U, L, L), self.u_interne, s, ctx)
        if "restitutions" in on:
            s = self.sub("restitutions", r"\[([%s']{1,4})J(?=[%s\s,.;:!?\]]|$)" % (L, L), r"[\1]", s, ctx)
            s = self.sub("restitutions", r"\{([%s]{1,4})\]" % L, r"[\1]", s, ctx)
            s = self.sub("restitutions", r"(?<=[%s])\[([%s]{1,3})\]%s([%s]{1,2})\b" % (L, L, SP, L),
                         self.crochet_coupe, s, ctx)
        if "guillemets" in on:                 # d'abord : « a H reis » → « li reis (et non « a li reis »)
            s, ouvert = self.guillemets(s, ctx, ouvert)
        if "li" in on:
            s = self.sub("li", r"^(%s(?:«%s)?)11(?=%s+[%s%s])" % (P, SP, SP, L, U), lambda m: m.group(1) + "Il", s, ctx)
            s = self.sub("li", r"(?<![\S])(?:h|ti|ii|11|H(?!\.))(?=%s+[%s%s\[])" % (SP, L, U), "li", s, ctx)
            # « U » en tête de vers ou après « est « où » ; ailleurs devant un mot, c'est « li »
            s = self.sub("li", r"(?<=[%s%s.,]%s)U(?=%s+[%s%s])" % (L, U, SP, SP, L, U), "li", s, ctx)
            s = self.sub("li", r"(?<=[%s])%s+!%s+[iI](?=%s)" % (L + U + ".", SP, SP, SP), " li", s, ctx)
        if "l-lu" in on:
            s = self.sub("l-lu", r"(?<![\S])([%s]+)%s*!%s+([%s][%s\[\]]*)" % (L + U, SP, SP, L, L), self.l_lu, s, ctx)
        return s, ouvert

    def u_interne(self, m):
        a, b = m.group(1), m.group(2)
        for r in ("li", "ll", "il", "l"):
            if self.connu(a + r + b):
                return a + r + b
        return None

    def crochet_coupe(self, m):          # bruis[i] ée → bruis[i]ée si le mot recollé est connu
        # m.string est la ligne : retrouver le début du mot
        start = m.start()
        w = re.search(r"[%s\[\]]*$" % (L + U), m.string[:start]).group(0)
        if self.connu(re.sub(r"[\[\]]", "", w + m.group(1) + m.group(2))):
            return "[%s]%s" % (m.group(1), m.group(2))
        return None

    EXCLAM = {"a", "ha", "ahi", "ohi", "fei", "veir", "las", "dex", "deus", "dieu", "deu", "oï", "o", "e", "voir"}
    VOCATIF = {"sire", "sires", "dame", "seignor", "seignors", "seingnors", "beals", "beal", "bele", "frère", "amis", "dex", "deus"}

    def l_lu(self, m):                   # « ! » lu pour « l »
        a, b = m.group(1), m.group(2)
        if m.string[m.end():m.end() + 1] == "»" or a.lower() in self.EXCLAM - {"a"} \
                or (a.lower() == "a" and b.lower() in self.VOCATIF):
            return None
        for r in (a + "l" + b, a + "l " + b, a + " l" + b):
            ws = r.split()             # deux mots : chacun fréquent (au moins 10 fois)
            if all(self.connu(w, 2 if len(ws) == 1 else 10) and len(w) > 1 for w in ws):
                return "\x01%s\x02OCR : « %s ! %s » lu « %s »\x03" % (r, a, b, r)
        return None

    FORT = {"D", "B", ">", "})", "])", "!)", "`~"}          # jamais un mot en fin de vers

    def guillemets(self, s, ctx, ouvert):
        # début de vers : lettre ou signe lu pour « devant une majuscule (ou devant « : »)
        m = re.match(r"(%s)(a\.?|<[tfc]?|[tcfeoida])%s*(:%s*)?(?=[%s&])" % (P, SP, SP, U), s) \
            or re.match(r"(%s)(<\[|<|a|o|c)%s*[:!]%s*(?=\S)" % (P, SP, SP), s) \
            or re.match(r"(%s)(<\[)(?=[%s][%s]*[\s,]|[%s][^\]\s]*$)" % (P, U, L, U), s)
        if m:
            self.log.append((ctx, "guillemets", m.group(0).strip(), "«"))
            s = m.group(1) + "«" + NB + s[m.end():]
        elif re.match(r"%s\.%s+(?=[%s])(?![IVXLCM]+\.)" % (P, SP, U), s):   # point parasite en tête
            m = re.match(r"(%s)\.%s+" % (P, SP), s)
            self.log.append((ctx, "guillemets", ".", ""))
            s = m.group(1) + s[m.end():]
        # « et » isolés dans le vers
        s = self.sub("guillemets", r"(?<=%s)<[tfc]?%s*:?%s*(?=[%s%s])" % (SP, SP, SP, U, L), "«" + NB, s, ctx)
        s = self.sub("guillemets", r"(?<=%s)[ijï]?%s?>(?=%s+[%s«]|%s+[\ue000-\uf8ff]*$)" % (SP, SP, SP, U, SP),
                     "»", s, ctx)
        # incises : « Dieu D dist li Mar. » → « Dieu » dist ; « li dist a Si Dex » → « dist « Si Dex »
        inc = r"(?:dist|distrent|dit|dient|fait|font|fist|respont|respondi|cria|crie|crient)\b"
        s = self.sub("guillemets", r"(?<=\S)%s+(?:[DB]|(?<=[%s]%s)[scrpn])(?=%s+%s)" % (SP, PUNCT, SP, SP, inc),
                     NB + "»", s, ctx)
        s = self.sub("guillemets", r"\b(%s)(,?)%s+a%s*:?%s+(?=([%s][%s]*))" % (inc, SP, SP, SP, U, L),
                     lambda m: m.group(1) + m.group(2) + " «" + NB if m.group(3).lower() in MINUSCULES
                     or m.group(3) in ("Dex", "Deus", "Dieu", "Deu", "Damledeu") else None, s, ctx)
        debut = "«" in s
        # fin de vers
        m = re.search(r"(\S)(%s+)(\}\)|\]\)|!\)|`~|[ijï]%s?>|[DBscrpnfFQVuzted1&°`>])(%s)$" % (SP, SP, P), s)
        if m and "»" not in s[m.start():]:
            avant, tok = m.group(1), m.group(3)
            tok1 = ">" if tok.endswith(">") else tok
            ponct = avant in PUNCT
            if tok1 in self.FORT or (ponct and (debut or ouvert)) \
                    or (not ponct and debut and tok1 in "scrpnfFQVz"):
                rep = ("!" + NB if tok == "!)" else "") + "»"
                self.log.append((ctx, "guillemets", tok, rep))
                s = s[:m.start(2)] + NB + rep + m.group(4)
        ouvert = (ouvert or debut) and "»" not in s
        return s, ouvert


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--vocab", nargs="*", default=[], help="EPUB d'où tirer les mots connus (en plus du texte)")
    ap.add_argument("--report", help="journal TSV des corrections (fichier, règle, avant, après, vers)")
    ap.add_argument("--sans", default="", help="règles à ne pas appliquer : " + ",".join(REGLES))
    opts = ap.parse_args()
    actives = [r for r in REGLES if r not in opts.sans.split(",")]
    vocab = vocabulaire([opts.epub] + opts.vocab)
    c = Correcteur(vocab, actives)
    zin = zipfile.ZipFile(opts.epub)
    zout = zipfile.ZipFile(opts.output, "w")
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith(".xhtml"):
            t = data.decode("utf-8")

            def para(m):
                if "vers" not in m.group(2).split():
                    return m.group(0)
                parts = re.split(r"(<br\s*/>)", m.group(4))
                ouvert = False
                for i in range(0, len(parts), 2):
                    li = Ligne(parts[i])
                    txt = re.sub(r"[\ue000-\uf8ff]", "", li.s).strip()
                    ctx = (item.filename.rsplit("/", 1)[-1], txt[:60])
                    li.s, ouvert = c.ligne(li.s, ctx, ouvert)
                    parts[i] = li.out()
                return m.group(1) + "".join(parts) + m.group(5)
            t = re.sub(r'(<p class="([^"]*)"([^>]*)>)(.*?)(</p>)', para, t, flags=re.S)
            data = t.encode("utf-8")
        zi = zipfile.ZipInfo(item.filename, item.date_time)
        zi.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
        zout.writestr(zi, data)
    zout.close()
    n = collections.Counter(r for _, r, _, _ in c.log)
    print("%d corrections : %s" % (len(c.log), ", ".join("%s %d" % kv for kv in n.most_common())))
    if opts.report:
        with open(opts.report, "w", encoding="utf-8") as f:
            f.write("fichier\trègle\tavant\taprès\tvers\n")
            for (fn, txt), r, a, b in c.log:
                f.write("%s\t%s\t%s\t%s\t%s\n" % (fn, r, a, b, txt))


if __name__ == "__main__":
    main()
