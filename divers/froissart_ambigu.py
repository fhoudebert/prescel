#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moteur contextuel V1 pour la modernisation du français médiéval
(adapté notamment à Froissart, XIVe siècle).

Principe :
  - les formes ambiguës ne sont pas remplacées aveuglément ;
  - plusieurs candidats sont évalués selon le contexte ;
  - une modernisation n'est appliquée que si le score et la marge
    sur le second candidat sont suffisants ;
  - les décisions sont journalisées.

Utilisation :
    python froissart_ambigu.py "Il ne fit ains que..."
    python froissart_ambigu.py input.txt -o output.txt --log decisions.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Formes ambiguës et candidats
# ---------------------------------------------------------------------------

CANDIDATES = {
    "ains": ["mais", "plutôt", "ainsi"],
    "ainçois": ["mais", "au contraire", "plutôt"],
    "or": ["or", "maintenant", "à présent", "donc"],
    "si": ["si", "ainsi", "alors"],
    "ja": ["déjà", "jamais", "désormais"],
    "moult": ["beaucoup", "très"],
    "tantost": ["bientôt", "aussitôt"],
    "ores": ["désormais", "maintenant", "à présent"],
    "gent": ["gens", "peuple", "nation"],
    "ost": ["armée", "armée en campagne", "hôte"],
    "mesmes": ["même", "eux-mêmes", "également"],
    "maint": ["maint", "plusieurs", "nombreux"],
    "devers": ["vers", "du côté de", "auprès de"],
    "entour": ["autour", "environ"],
    "voire": ["voire", "vraiment", "et même"],
    "fort": ["fort", "très", "beaucoup"],
    "bien": ["bien", "beaucoup", "fortement"],
    "assez": ["assez", "suffisamment", "très"],
    "tel": ["tel", "un tel", "si grand"],
    "pour ce": ["pour cela", "c'est pourquoi"],
}

# Formes sûres : elles peuvent être modernisées sans analyse complexe.
SAFE = {
    "ainz": "ainsi",
    "ainsi": "ainsi",
    "aprez": "après",
    "après": "après",
    "avecques": "avec",
    "avoit": "avait",
    "avoient": "avaient",
    "avois": "avais",
    "avoit": "avait",
    "ceulx": "ceux",
    "ceulx-ci": "ceux-ci",
    "ceulx-là": "ceux-là",
    "chascun": "chacun",
    "chascune": "chacune",
    "choses": "choses",
    "comme": "comme",
    "demoura": "demeura",
    "demourer": "demeurer",
    "estoit": "était",
    "estoient": "étaient",
    "estoit": "était",
    "estoient": "étaient",
    "fist": "fit",
    "fut": "fut",
    "fu": "fut",
    "furent": "furent",
    "icel": "celui",
    "icelle": "celle",
    "icelles": "celles",
    "icelui": "celui",
    "icelx": "ceux",
    "jaçoit": "quoique",
    "jaçoit que": "quoique",
    "jeunesce": "jeunesse",
    "jusques": "jusqu'à",
    "lorsque": "lorsque",
    "mais": "mais",
    "moult": "moult",       # volontairement ambigu
    "neant": "néant",
    "nient": "rien",
    "nulz": "nuls",
    "parmy": "parmi",
    "pourquoy": "pourquoi",
    "quant": "quand",
    "quar": "car",
    "que": "que",
    "quelquefois": "quelquefois",
    "sanz": "sans",
    "seur": "sur",
    "seurment": "sûrement",
    "tres": "très",
    "tresbien": "très bien",
    "trop": "trop",
    "estoit": "était",
    "estoient": "étaient",
    "veoir": "voir",
    "verité": "vérité",
    "vint": "vint",
    "voirement": "vraiment",
    "vouloit": "voulait",
    "y": "y",
}


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class Context:
    tokens: list[str]
    index: int
    window: int = 7

    @property
    def token(self) -> str:
        return self.tokens[self.index]

    @property
    def left(self) -> list[str]:
        return self.tokens[max(0, self.index - self.window):self.index]

    @property
    def right(self) -> list[str]:
        return self.tokens[
            self.index + 1:min(len(self.tokens), self.index + 1 + self.window)
        ]

    @property
    def before(self) -> str:
        return " ".join(self.left)

    @property
    def after(self) -> str:
        return " ".join(self.right)

    @property
    def full(self) -> str:
        return " ".join(self.left + [self.token] + self.right)


@dataclass
class Candidate:
    text: str
    score: float = 0.0
    reasons: list[tuple[float, str]] = field(default_factory=list)

    def add(self, points: float, reason: str) -> None:
        self.score += points
        self.reasons.append((points, reason))


@dataclass
class Decision:
    original: str
    replacement: str | None
    confidence: float
    margin: float
    candidates: list[dict]
    context: str
    index: int


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"\w+(?:[-’']\w+)*|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def normalize_token(token: str) -> str:
    return token.lower().replace("’", "'")


def is_word(token: str) -> bool:
    return bool(re.match(r"^\w", token, re.UNICODE))


def has_any(words: list[str], *patterns: str) -> bool:
    joined = " ".join(words)
    return any(
        p in words or p in joined
        for p in patterns
    )


# ---------------------------------------------------------------------------
# Règles contextuelles
# ---------------------------------------------------------------------------

def score_candidate(form: str, candidate: Candidate, ctx: Context) -> None:
    """Ajoute des points au candidat selon des règles simples."""

    before = [normalize_token(x) for x in ctx.left]
    after = [normalize_token(x) for x in ctx.right]
    all_words = before + after
    text_before = " ".join(before)
    text_after = " ".join(after)

    # --- AINS ---------------------------------------------------------------
    if form == "ains":
        if has_any(before, "non", "ne", "pas", "point", "oncques"):
            if candidate.text == "mais":
                candidate.add(0.70, "construction d'opposition : non/ne... mais")
        if has_any(after, "mais", "au", "contraire"):
            if candidate.text == "mais":
                candidate.add(0.45, "suite argumentative/oppositive")
        if has_any(after, "que"):
            if candidate.text == "ainsi":
                candidate.add(0.25, "construction pouvant introduire une conséquence")
        if has_any(before, "plutôt"):
            if candidate.text == "plutôt":
                candidate.add(0.35, "contexte de rectification")

    # --- AINÇOIS ------------------------------------------------------------
    elif form == "ainçois":
        if has_any(before, "non", "ne", "pas"):
            if candidate.text in {"mais", "au contraire"}:
                candidate.add(0.70, "opposition après négation")
        if has_any(after, "que"):
            if candidate.text == "plutôt":
                candidate.add(0.25, "rectification")

    # --- MOUlt --------------------------------------------------------------
    elif form == "moult":
        # moult + adjectif/adverbe -> très
        if after and is_word(after[0]):
            if candidate.text == "très":
                candidate.add(0.35, "moult placé avant un qualificatif")
        # verbe + moult -> beaucoup
        if before:
            if re.search(r"(a|e|i|o|u|é|ait|oit|ir|er|re)$", before[-1]):
                if candidate.text == "beaucoup":
                    candidate.add(0.25, "moult suivant vraisemblablement un verbe")
        if has_any(after, "de"):
            if candidate.text == "beaucoup":
                candidate.add(0.20, "moult de : quantification")
        # Froissart emploie très souvent moult comme intensif.
        if candidate.text == "très":
            candidate.add(0.15, "usage fréquent de moult comme intensif")

    # --- JA -----------------------------------------------------------------
    elif form == "ja":
        if has_any(before, "ne", "n", "jamais"):
            if candidate.text == "jamais":
                candidate.add(0.75, "ne ... ja : valeur négative")
        if has_any(before, "avoit", "avait", "estoit", "était",
                   "fut", "fu", "ot", "eut", "a"):
            if candidate.text == "déjà":
                candidate.add(0.40, "contexte verbal accompli")
        if has_any(after, "plus", "encore"):
            if candidate.text == "désormais":
                candidate.add(0.20, "valeur temporelle")

    # --- TANTOST ------------------------------------------------------------
    elif form == "tantost":
        if has_any(after, "fera", "feroit", "ira", "iront", "viendra",
                   "verra", "sera", "auront", "aura"):
            if candidate.text == "bientôt":
                candidate.add(0.55, "événement futur")
        if has_any(before, "aussitôt", "sitôt"):
            if candidate.text == "aussitôt":
                candidate.add(0.35, "valeur immédiate")
        if has_any(before, "vint", "vient", "entra", "arriva",
                   "fut", "fit", "dit"):
            if candidate.text == "aussitôt":
                candidate.add(0.30, "événement immédiatement antérieur")

    # --- OR -----------------------------------------------------------------
    elif form == "or":
        if has_any(after, "mes", "maintenant", "ores"):
            if candidate.text == "à présent":
                candidate.add(0.30, "marqueur temporel")
        if has_any(after, "donc", "ainsi"):
            if candidate.text == "donc":
                candidate.add(0.25, "enchaînement logique")
        # Par défaut, le "or" argumentatif reste moderne.
        if candidate.text == "or":
            candidate.add(0.35, "forme encore usuelle en français moderne")

    # --- SI -----------------------------------------------------------------
    elif form == "si":
        if has_any(after, "que"):
            if candidate.text == "si":
                candidate.add(0.35, "construction conditionnelle")
        if has_any(before, "et", "ainsi", "donc"):
            if candidate.text == "ainsi":
                candidate.add(0.25, "valeur consécutive possible")
        if has_any(after, "fist", "fit", "vint", "vintrent",
                   "entra", "arriva"):
            if candidate.text == "alors":
                candidate.add(0.20, "enchaînement narratif")

    # --- ORES ----------------------------------------------------------------
    elif form == "ores":
        if candidate.text in {"maintenant", "à présent"}:
            candidate.add(0.55, "valeur temporelle actuelle")
        if has_any(before, "désormais"):
            if candidate.text == "désormais":
                candidate.add(0.30, "valeur de changement d'état")

    # --- DEVERS --------------------------------------------------------------
    elif form == "devers":
        if has_any(after, "paris", "la", "le", "les", "ville", "château",
                   "roi", "cour"):
            if candidate.text == "vers":
                candidate.add(0.35, "direction vers un lieu/personne")
        if has_any(before, "près", "auprès"):
            if candidate.text == "du côté de":
                candidate.add(0.20, "localisation")

    # --- ENTOUR --------------------------------------------------------------
    elif form == "entour":
        if has_any(after, "de"):
            if candidate.text == "autour":
                candidate.add(0.45, "construction autour de")
        if has_any(after, "vingt", "trente", "cent", "mille"):
            if candidate.text == "environ":
                candidate.add(0.35, "approximation numérique")

    # --- MESMES --------------------------------------------------------------
    elif form == "mesmes":
        if has_any(before, "eux", "elles", "ceux"):
            if candidate.text == "eux-mêmes":
                candidate.add(0.45, "pronom réfléchi renforcé")
        if has_any(after, "aussi", "encore"):
            if candidate.text == "également":
                candidate.add(0.30, "valeur additive")

    # --- VOIRE ----------------------------------------------------------------
    elif form == "voire":
        if has_any(after, "même"):
            if candidate.text == "et même":
                candidate.add(0.35, "renforcement")

    # --- FORT -----------------------------------------------------------------
    elif form == "fort":
        if has_any(after, "bien", "grand", "bon", "mauvais", "beau",
                   "puissant", "sage"):
            if candidate.text == "très":
                candidate.add(0.30, "intensif devant qualificatif")

    # --- BIEN -----------------------------------------------------------------
    elif form == "bien":
        if has_any(after, "plus", "fort", "grand", "mieux"):
            if candidate.text == "bien":
                candidate.add(0.20, "emploi adverbial moderne conservé")

    # --- POUR CE --------------------------------------------------------------
    elif form == "pour ce":
        if has_any(after, "que"):
            if candidate.text == "c'est pourquoi":
                candidate.add(0.50, "locution causale/conclusive")


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------

def analyze_form(form: str, ctx: Context) -> tuple[Candidate | None, list[Candidate]]:
    candidates = [Candidate(x) for x in CANDIDATES.get(form, [])]

    for candidate in candidates:
        score_candidate(form, candidate, ctx)

    candidates.sort(key=lambda c: c.score, reverse=True)

    if not candidates:
        return None, []

    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    # Score minimal + marge minimale.
    # Ici les scores sont internes et non des probabilités statistiques.
    margin = best.score - (second.score if second else 0.0)

    # Pour éviter les décisions arbitraires :
    # - score >= 0.80 : décision automatique
    # - score >= 0.65 avec une forte marge : décision prudente
    if best.score >= 0.80 and margin >= 0.15:
        return best, candidates

    if best.score >= 0.65 and margin >= 0.30:
        return best, candidates

    return None, candidates


# ---------------------------------------------------------------------------
# Application au texte
# ---------------------------------------------------------------------------

def restore_spacing(tokens: list[str]) -> str:
    text = ""
    no_space_before = {".", ",", ";", ":", "!", "?", ")", "]", "}", "»"}
    no_space_after = {"(", "[", "{", "«"}

    for token in tokens:
        if not text:
            text = token
        elif token in no_space_before:
            text += token
        elif text[-1:] in no_space_after:
            text += token
        else:
            text += " " + token

    return text


def replace_safe(tokens: list[str]) -> list[str]:
    result = []
    for token in tokens:
        key = normalize_token(token)
        replacement = SAFE.get(key)
        if replacement is None:
            result.append(token)
        else:
            # Respect la majuscule initiale.
            if token[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            result.append(replacement)
    return result


def modernize(
    text: str,
    *,
    min_window: int = 7,
) -> tuple[str, list[Decision]]:
    tokens = tokenize(text)
    decisions: list[Decision] = []

    # Pass 1 : expressions à deux mots.
    # On ne fusionne pas les tokens : on travaille sur des indices.
    replacements: dict[int, str] = {}

    for i in range(len(tokens) - 1):
        pair = f"{normalize_token(tokens[i])} {normalize_token(tokens[i+1])}"
        if pair not in CANDIDATES:
            continue

        # Cette forme n'est pas actuellement dans CANDIDATES, mais la
        # structure est prévue pour les futures expressions ambiguës.
        ctx = Context(tokens, i, min_window)
        best, candidates = analyze_form(pair, ctx)

        if best:
            replacements[i] = best.text
            replacements[i + 1] = ""
            decisions.append(
                Decision(
                    original=pair,
                    replacement=best.text,
                    confidence=best.score,
                    margin=best.score - (
                        candidates[1].score if len(candidates) > 1 else 0
                    ),
                    candidates=[
                        {
                            "text": c.text,
                            "score": round(c.score, 3),
                            "reasons": c.reasons,
                        }
                        for c in candidates
                    ],
                    context=ctx.full,
                    index=i,
                )
            )

    # Pass 2 : formes ambiguës simples.
    for i, token in enumerate(tokens):
        form = normalize_token(token)
        if form not in CANDIDATES:
            continue
        if i in replacements:
            continue

        ctx = Context(tokens, i, min_window)
        best, candidates = analyze_form(form, ctx)

        if best:
            replacements[i] = best.text
            decisions.append(
                Decision(
                    original=token,
                    replacement=best.text,
                    confidence=best.score,
                    margin=best.score - (
                        candidates[1].score if len(candidates) > 1 else 0
                    ),
                    candidates=[
                        {
                            "text": c.text,
                            "score": round(c.score, 3),
                            "reasons": c.reasons,
                        }
                        for c in candidates
                    ],
                    context=ctx.full,
                    index=i,
                )
            )

    # Pass 3 : dictionnaire sûr.
    result = []
    for i, token in enumerate(tokens):
        if i in replacements:
            if replacements[i] != "":
                result.append(replacements[i])
        else:
            key = normalize_token(token)
            replacement = SAFE.get(key)
            if replacement is not None:
                if token[:1].isupper():
                    replacement = replacement[:1].upper() + replacement[1:]
                result.append(replacement)
            else:
                result.append(token)

    return restore_spacing(result), decisions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def decision_to_dict(d: Decision) -> dict:
    return {
        "original": d.original,
        "replacement": d.replacement,
        "confidence": round(d.confidence, 3),
        "margin": round(d.margin, 3),
        "candidates": d.candidates,
        "context": d.context,
        "index": d.index,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Modernisation contextuelle du français médiéval."
    )
    parser.add_argument(
        "input",
        help="texte à analyser, ou fichier .txt",
    )
    parser.add_argument(
        "-o", "--output",
        help="fichier texte de sortie",
    )
    parser.add_argument(
        "--log",
        help="fichier JSON contenant les décisions",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=7,
        help="nombre de mots de contexte de chaque côté (défaut : 7)",
    )
    args = parser.parse_args()

    source = Path(args.input)
    if source.exists() and source.is_file():
        text = source.read_text(encoding="utf-8")
    else:
        text = args.input

    modern, decisions = modernize(text, min_window=args.window)

    if args.output:
        Path(args.output).write_text(modern, encoding="utf-8")
    else:
        print(modern)

    if args.log:
        data = [decision_to_dict(d) for d in decisions]
        Path(args.log).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
