class MedievalAnalyzer:

    def __init__(
        self,
        safe,
        context,
        expressions,
        patterns,
    ):
        self.safe = safe
        self.context = context
        self.expressions = expressions
        self.patterns = patterns

    def analyze(self, tokens, position):
        """Analyse une forme selon son contexte."""

        word = tokens[position]

        # 1. Forme sûre
        if word in self.safe:
            return {
                "original": word,
                "modern": self.safe[word],
                "confidence": 1.0,
                "status": "safe",
            }

        # 2. Forme contextuelle
        if word in self.context:
            return self.analyze_context(
                tokens,
                position,
            )

        # 3. Rien trouvé
        return {
            "original": word,
            "modern": word,
            "confidence": 0.0,
            "status": "unchanged",
        }


    def analyze_context(self, tokens, i):

    word = tokens[i]

    if word == "ains":
        return self.analyse_ains(tokens, i)

    if word == "or":
        return self.analyse_or(tokens, i)

    if word == "moult":
        return self.analyse_moult(tokens, i)

    if word == "tantost":
        return self.analyse_tantost(tokens, i)

    return {
        "original": word,
        "modern": word,
        "confidence": 0.0,
        "status": "ambiguous",
    }


    def analyze_context(self, tokens, i):

    word = tokens[i]

    if word == "ains":
        return self.analyse_ains(tokens, i)

    if word == "or":
        return self.analyse_or(tokens, i)

    if word == "moult":
        return self.analyse_moult(tokens, i)

    if word == "tantost":
        return self.analyse_tantost(tokens, i)

    return {
        "original": word,
        "modern": word,
        "confidence": 0.0,
        "status": "ambiguous",
    }
