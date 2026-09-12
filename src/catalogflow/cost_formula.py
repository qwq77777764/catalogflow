"""Small arithmetic grammar applied to product cost; never executes user code."""

from __future__ import annotations

import re
from decimal import Decimal, DecimalException, localcontext

MAX_FORMULA_LENGTH = 120
MAX_FORMULA_OPERATORS = 32
MAX_FORMULA_VALUE = Decimal("100000000")
_TOKEN = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)|[+*/()\-]")


class CostFormulaError(ValueError):
    """Stable, localizable errors with no echoed formula or supplier data."""


def _calculate(tokens: list[Decimal | str], cost: Decimal, *, bounded: bool) -> Decimal:
    values: list[Decimal] = []
    try:
        with localcontext() as context:
            context.prec = 28
            for symbol in tokens:
                if isinstance(symbol, Decimal):
                    values.append(symbol)
                    continue
                if symbol == "cost":
                    values.append(cost)
                    continue
                right, left = values.pop(), values.pop()
                if symbol == "+":
                    value = left + right
                elif symbol == "-":
                    value = left - right
                elif symbol == "*":
                    value = left * right
                else:
                    if right == 0:
                        raise CostFormulaError("cost_formula_division_by_zero")
                    value = left / right
                if bounded and abs(value) > MAX_FORMULA_VALUE:
                    raise CostFormulaError("cost_formula_result_out_of_range")
                values.append(value)
    except DecimalException as exc:
        raise CostFormulaError("cost_formula_result_out_of_range") from exc
    return values[0]


def _compile(source: str) -> tuple[str, list[Decimal | str]]:
    if not isinstance(source, str) or not 1 <= len(source) <= MAX_FORMULA_LENGTH:
        raise CostFormulaError("cost_formula_invalid")
    text = source.strip()
    if not text:
        raise CostFormulaError("cost_formula_invalid")
    # A bare multiplier remains convenient, while the visible UI prefixes product cost.
    if re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", text):
        text = "*" + text
    if text[0] not in "+-*/":
        raise CostFormulaError("cost_formula_invalid")
    lexed: list[str] = ["cost"]
    position = 0
    for match in _TOKEN.finditer(text):
        if text[position:match.start()].strip():
            raise CostFormulaError("cost_formula_invalid")
        lexed.append(match.group())
        position = match.end()
    if text[position:].strip() or sum(t in "+-*/" for t in lexed) > MAX_FORMULA_OPERATORS:
        raise CostFormulaError("cost_formula_invalid")
    index = 0
    output: list[Decimal | str] = []

    def expression(depth: int = 0) -> None:
        nonlocal index
        term(depth)
        while index < len(lexed) and lexed[index] in ("+", "-"):
            operator = lexed[index]
            index += 1
            term(depth)
            output.append(operator)

    def term(depth: int) -> None:
        nonlocal index
        factor(depth)
        while index < len(lexed) and lexed[index] in ("*", "/"):
            operator = lexed[index]
            index += 1
            factor(depth)
            output.append(operator)

    def factor(depth: int) -> None:
        nonlocal index
        if index >= len(lexed) or depth > 12:
            raise CostFormulaError("cost_formula_invalid")
        symbol = lexed[index]
        index += 1
        if symbol == "cost":
            output.append(symbol)
        elif symbol == "(":
            expression(depth + 1)
            if index >= len(lexed) or lexed[index] != ")":
                raise CostFormulaError("cost_formula_invalid")
            index += 1
        elif symbol in ("+", "-"):
            output.append(Decimal(0))
            factor(depth + 1)
            output.append(symbol)
        elif symbol[0] in "0123456789.":
            number = Decimal(symbol)
            if number > 1_000_000:
                raise CostFormulaError("cost_formula_invalid")
            output.append(number)
        else:
            raise CostFormulaError("cost_formula_invalid")

    expression()
    if index != len(lexed):
        raise CostFormulaError("cost_formula_invalid")
    # All divisors are constant expressions; validate them independently of sample cost.
    _calculate(output, Decimal(0), bounded=False)
    return "".join(lexed[1:]), output


def normalize_cost_formula(source: str) -> str:
    return _compile(source)[0]


def apply_cost_formula(source: str, product_cost: float) -> float:
    _, tokens = _compile(source)
    cost = Decimal(str(product_cost))
    if not cost.is_finite() or not 0 <= cost <= 1_000_000:
        raise CostFormulaError("cost_formula_result_out_of_range")
    result = _calculate(tokens, cost, bounded=True)
    if not 0 <= result <= MAX_FORMULA_VALUE:
        raise CostFormulaError("cost_formula_result_out_of_range")
    return float(result)
