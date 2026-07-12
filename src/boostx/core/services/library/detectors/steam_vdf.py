class VdfParseError(Exception):
    pass


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char in " \t\r\n":
            i += 1
            continue
        if char == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if char in "{}":
            tokens.append(char)
            i += 1
            continue
        if char == '"':
            i += 1
            buf: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                    continue
                buf.append(text[i])
                i += 1
            i += 1
            tokens.append("".join(buf))
            continue
        start = i
        while i < n and text[i] not in " \t\r\n{}":
            i += 1
        tokens.append(text[start:i])
    return tokens


def parse_vdf(text: str) -> dict:
    tokens = _tokenize(text)
    position = [0]

    def peek() -> str | None:
        return tokens[position[0]] if position[0] < len(tokens) else None

    def advance() -> str:
        token = tokens[position[0]]
        position[0] += 1
        return token

    def parse_block() -> dict:
        result: dict = {}
        while True:
            token = peek()
            if token is None:
                break
            if token == "}":
                advance()
                break
            key = advance()
            value_token = peek()
            if value_token is None:
                raise VdfParseError(f"key '{key}' has no value")
            if value_token == "{":
                advance()
                result[key] = parse_block()
            else:
                result[key] = advance()
        return result

    return parse_block()
