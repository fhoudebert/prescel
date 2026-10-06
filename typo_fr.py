# -*- coding: utf-8 -*-
"""
typo_fr.py — Règles d'espacement de la typographie française.

  signe        avant               après
  . , … ) ]    aucune espace       une espace si un mot suit
  ; : ! ? »    espace insécable    une espace si un mot suit
  « ( [        —                   espace insécable après « ; rien après ( [
  ...          → …                 (trois points exactement)
  - entouré d'espaces → — (tiret) ; « — » ou « - » en tête de paragraphe → « — » + une espace
  —            une espace           une espace (« Gens.—3-4 » → « Gens. — 3-4 »)

Le texte peut être découpé en morceaux (italique, gras…) : on le passe sous forme de
liste de chaînes, les règles s'appliquent par-dessus les limites et chaque morceau est
rendu à sa place. Aucune lettre n'est ajoutée ni retirée : seuls les espaces, « ... » et
le tiret changent. Les nombres (« 10:30 », « 1,5 ») ne sont pas touchés.
"""

import re

M = "\ue000"                 # limite entre deux morceaux (invisible pour les règles)
NBSP = "\u00a0"
SP = "[ \u00a0\u202f\t]"     # espaces ordinaires et insécables
_M = "(?:%s)*" % M
LETTER = "A-Za-zÀ-ÖØ-öø-ÿŒœÆæ"


def _rules(s):
    # « ... » → « … »
    s = re.sub(r"(?<!\.)\.\.\.(?!\.)", "…", s)
    # tiret : « - » entouré d'espaces, ou en tête de paragraphe (dialogue)
    s = re.sub(r"(?<=\S)(%s)%s+-%s+" % (_M, SP, SP), r"\1 — ", s)
    s = re.sub(r"^(%s)[-—]%s*" % (_M, SP), r"\1— ", s)
    # aucune espace avant . , … ) ]  (sauf « … » en début de citation)
    s = re.sub(r"(?<=[^\s%s])(%s)%s+(%s)([.,)\]])" % (M, _M, SP, _M), r"\1\2\3", s)
    s = re.sub(r"(?<=[%s%s])(%s)%s+(%s)(…)" % (LETTER, "»", _M, SP, _M), r"\1\2\3", s)
    # aucune espace après ( [
    s = re.sub(r"([(\[])(%s)%s+" % (_M, SP), r"\1\2", s)
    # espace insécable avant ; : ! ?  (pas entre deux chiffres : « 10:30 »)
    s = re.sub(r"(?<=[^\s;:!?%s])(%s)%s*(%s)([;!?])" % (M, _M, SP, _M), r"\1\2" + NBSP + r"\3", s)
    s = re.sub(r"(?<=[^\s;:!?\d%s])(%s)%s*(%s)(:)" % (M, _M, SP, _M), r"\1\2" + NBSP + r"\3", s)
    # espace insécable avant » et après «
    s = re.sub(r"(?<=[^\s%s«])(%s)%s*(%s)(»)" % (M, _M, SP, _M), r"\1\2" + NBSP + r"\3", s)
    s = re.sub(r"(«)(%s)%s*(?=\S)" % (_M, SP), r"\1" + NBSP + r"\2", s)
    # une espace après . , ; : ! ? … ) ] » quand un mot (ou « ( [ ) suit directement
    s = re.sub(r"([.,;:!?…)\]»])(%s)(?=[%s«(\[])" % (_M, LETTER), r"\1\2 ", s)
    # tiret « — » collé (« France.— 1-2 », « Gens.—3-4 ») : une espace de chaque côté
    s = re.sub(r"(?<=[^\s—(\[%s])(%s)—" % (M, _M), r"\1 —", s)
    s = re.sub(r"—(%s)(?=[^\s—.,;:)\]%s])" % (_M, M), r"—\1 ", s)
    # espaces multiples
    s = re.sub(r"(?<=\S)(%s)[ ]{2,}" % _M, r"\1 ", s)
    s = re.sub(r" +(%s)%s" % (_M, NBSP), r"\1" + NBSP, s)          # « x \u00a0; » → insécable seule
    return s


def typo_pieces(pieces):
    """Applique les règles à une suite de morceaux de texte ; renvoie autant de morceaux."""
    joined = M.join(pieces)
    out = _rules(joined).split(M)
    if len(out) != len(pieces):           # sécurité : en cas de doute, on ne touche à rien
        return list(pieces)
    return out


def typo(text):
    return typo_pieces([text])[0]


def letters_only(s):
    """Pour la vérification : le texte sans espaces, et « … » compté comme « ... »."""
    return re.sub(r"[\s\u00a0\u202f]", "", s.replace("…", "...").replace("—", "-"))
