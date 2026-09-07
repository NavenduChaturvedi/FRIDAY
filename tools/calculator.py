"""Arithmetic FRIDAY can trust — safe expression evaluation, no eval()."""

from __future__ import annotations

import ast
import math
import operator

TOOL = {
    "name": "calculate",
    "description": (
        "Evaluate a arithmetic expression and return the result. Use for any "
        "sum, percentage, or conversion the user asks for out loud — models "
        "get arithmetic wrong. Supports + - * / // % **, parentheses, and "
        "sqrt, sin, cos, log, pi, e, round, abs. Example: '15% of 240' -> "
        "'240 * 0.15'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A math expression, e.g. '(3 + 4) * 2' or 'sqrt(2)'.",
            },
        },
        "required": ["expression"],
    },
}

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp,
    "floor": math.floor, "ceil": math.ceil, "round": round, "abs": abs,
    "min": min, "max": max,
}


def _eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("only numbers allowed")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"unknown function {node.func.id!r}")
        return fn(*[_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def run(expression: str = "") -> str:
    expr = (expression or "").strip()
    if not expr:
        return "Give me something to calculate."
    try:
        result = _eval(ast.parse(expr, mode="eval").body)
    except ZeroDivisionError:
        return "That's a division by zero."
    except Exception as exc:  # noqa: BLE001
        return f"I couldn't work that out: {exc}"
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    if isinstance(result, float):
        result = round(result, 6)
    return f"{expr} = {result}"
