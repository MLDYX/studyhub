class Calculator:
    def evaluate(self, expression: str) -> str:
        try:
            allowed = "0123456789.+-*/() "
            if not all(c in allowed for c in expression):
                return "Blad"
            result = str(eval(expression))
        except Exception:
            result = "Blad"
        return result