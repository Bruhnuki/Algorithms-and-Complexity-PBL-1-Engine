"""ScrumScript interpreter. No imports, no I/O, no host objects, hard step limit.

Grammar (whitespace-insensitive):
  program   := function
  function  := 'function' NAME '(' [NAME {',' NAME}] ')' block
  block     := '{' {stmt} '}'
  stmt      := 'return' expr | 'if' expr block ['else' block] | NAME '=' expr
  expr      := cmp ;  cmp := sum ['==' sum] ;  sum := term {('+'|'-') term}
  term      := unary {('*'|'/') unary} ; unary := '-' unary | atom
  atom      := NUMBER | STRING | NAME | NAME '(' args ')' | '(' expr ')'
Only builtin: clean(s) -> s without quote characters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALL_KEYWORDS = {"function", "return", "if", "else", "while", "for", "and", "or", "not", "true", "false"}


class ScrumError(Exception):
    """Parse or runtime error in ScrumScript (never a Python-level crash)."""


_TOKEN = re.compile(r'\s*(?:(\d+(?:\.\d+)?)|("[^"]*")|([A-Za-z_][A-Za-z_0-9]*)|(==|[=+\-*/(){},]))')


def tokenize(src: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = _TOKEN.match(src, pos)
        if not m:
            raise ScrumError(f"Unexpected character near {src[pos:pos + 10].strip()!r}")
        num, string, name, op = m.groups()
        if num is not None:
            out.append(("num", num))
        elif string is not None:
            out.append(("str", string[1:-1]))
        elif name is not None:
            out.append(("kw" if name in ALL_KEYWORDS else "name", name))
        else:
            out.append(("op", op))
        pos = m.end()
    return out


class _Return(Exception):
    def __init__(self, value):
        self.value = value


@dataclass
class _Func:
    name: str
    params: list[str]
    body: list


class _Parser:
    def __init__(self, tokens, allowed):
        self.t = tokens
        self.i = 0
        self.allowed = allowed

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ("eof", "")

    def take(self, kind=None, val=None):
        tok = self.peek()
        if (kind and tok[0] != kind) or (val is not None and tok[1] != val):
            raise ScrumError(f"Expected {val or kind} but found {tok[1] or 'end of code'!r}")
        self.i += 1
        return tok

    def kw(self, word):
        if word not in self.allowed:
            raise ScrumError(f"'{word}' is not allowed yet in this sprint")
        return self.take("kw", word)

    def function(self):
        self.kw("function")
        name = self.take("name")[1]
        self.take("op", "(")
        params = []
        if self.peek() != ("op", ")"):
            params.append(self.take("name")[1])
            while self.peek() == ("op", ","):
                self.take()
                params.append(self.take("name")[1])
        self.take("op", ")")
        body = self.block()
        if self.peek()[0] != "eof":
            raise ScrumError("Extra code after the function")
        return _Func(name, params, body)

    def block(self):
        self.take("op", "{")
        stmts = []
        while self.peek() != ("op", "}"):
            if self.peek()[0] == "eof":
                raise ScrumError("Missing closing brace")
            stmts.append(self.stmt())
        self.take("op", "}")
        return stmts

    def stmt(self):
        kind, val = self.peek()
        if (kind, val) == ("kw", "return"):
            self.kw("return")
            return ("return", self.expr())
        if (kind, val) == ("kw", "if"):
            self.kw("if")
            cond = self.expr()
            then = self.block()
            other: list = []
            if self.peek() == ("kw", "else"):
                self.kw("else")
                other = self.block()
            return ("if", cond, then, other)
        if kind == "name":
            self.take()
            self.take("op", "=")
            return ("assign", val, self.expr())
        if kind == "kw":
            raise ScrumError(f"'{val}' is not allowed yet in this sprint")
        raise ScrumError(f"Unexpected {val or 'end of code'!r}")

    def expr(self):
        left = self.sum()
        if self.peek() == ("op", "=="):
            self.take()
            left = ("bin", "==", left, self.sum())
        return left

    def sum(self):
        left = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            left = ("bin", op, left, self.term())
        return left

    def term(self):
        left = self.unary()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            left = ("bin", op, left, self.unary())
        return left

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        return self.atom()

    def atom(self):
        kind, val = self.peek()
        if kind == "num":
            self.take()
            return ("lit", float(val))
        if kind == "str":
            self.take()
            return ("lit", val)
        if kind == "name":
            self.take()
            if self.peek() == ("op", "("):
                self.take()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.expr())
                    while self.peek() == ("op", ","):
                        self.take()
                        args.append(self.expr())
                self.take("op", ")")
                return ("call", val, args)
            return ("var", val)
        if (kind, val) == ("op", "("):
            self.take()
            e = self.expr()
            self.take("op", ")")
            return e
        raise ScrumError(f"Unexpected {val or 'end of code'!r}")


class _Machine:
    def __init__(self, step_limit: int):
        self.steps = 0
        self.limit = step_limit

    def tick(self):
        self.steps += 1
        if self.steps > self.limit:
            raise ScrumError("The program ran too long (step limit)")

    def ev(self, node, env):
        self.tick()
        k = node[0]
        if k == "lit":
            return node[1]
        if k == "var":
            if node[1] not in env:
                raise ScrumError(f"'{node[1]}' is not defined")
            return env[node[1]]
        if k == "neg":
            v = self.ev(node[1], env)
            if not isinstance(v, float):
                raise ScrumError("Cannot negate text")
            return -v
        if k == "call":
            if node[1] != "clean" or len(node[2]) != 1:
                raise ScrumError(f"Unknown function '{node[1]}'")
            v = self.ev(node[2][0], env)
            if not isinstance(v, str):
                raise ScrumError("clean() needs text")
            return v.replace("'", "").replace('"', "").replace(";", "")
        a, b = self.ev(node[2], env), self.ev(node[3], env)
        op = node[1]
        if op == "==":
            return a == b
        if op == "+":
            if isinstance(a, str) and isinstance(b, str):
                return a + b
            self._nums(a, b)
            return a + b
        self._nums(a, b)
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if b == 0:
            raise ScrumError("Divided by zero")
        return a / b

    @staticmethod
    def _nums(a, b):
        if isinstance(a, bool) or isinstance(b, bool) or not (isinstance(a, float) and isinstance(b, float)):
            raise ScrumError("Cannot mix text and numbers")

    def run(self, stmts, env):
        for s in stmts:
            self.tick()
            if s[0] == "return":
                raise _Return(self.ev(s[1], env))
            if s[0] == "assign":
                env[s[1]] = self.ev(s[2], env)
            else:
                branch = s[2] if self.ev(s[1], env) else s[3]
                self.run(branch, env)


def call(source: str, args: list, *, allowed: set[str], step_limit: int = 2000):
    """Parse `source` and call its function with `args`. Raises ScrumError on any problem."""
    func = _Parser(tokenize(source), allowed).function()
    if len(args) != len(func.params):
        raise ScrumError("Wrong number of inputs")
    env = {p: (float(a) if isinstance(a, (int, float)) and not isinstance(a, bool) else a) for p, a in zip(func.params, args)}
    m = _Machine(step_limit)
    try:
        m.run(func.body, env)
    except _Return as r:
        return r.value
    except RecursionError as e:  # pragma: no cover - defensive
        raise ScrumError("Too deeply nested") from e
    raise ScrumError("The function never returned a value")


def same(actual, expected) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, float):
        return abs(actual - float(expected)) < 1e-9
    return actual == expected


def fmt(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else f"{v:.4g}"
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def run_examples(source: str, examples: list[dict], params: list[str], *, allowed: set[str], step_limit: int = 2000) -> list[dict]:
    """Run every example. Never raises: returns one plain-English record per run."""
    out = []
    for n, ex in enumerate(examples, 1):
        given = ", ".join(f"{p}={fmt(a)}" for p, a in zip(params, ex["input"]))
        rec = {"run": n, "input": ex["input"], "expected": ex["expected"], "actual": None, "error": None}
        try:
            actual = call(source, ex["input"], allowed=allowed, step_limit=step_limit)
            rec["actual"] = actual
            rec["pass"] = same(actual, ex["expected"])
            rec["text"] = (f"Run {n}: with {given} it gave {fmt(actual)}, expected {fmt(ex['expected'])}. "
                           + ("Pass." if rec["pass"] else "Fail."))
        except ScrumError as e:
            rec["error"] = str(e)
            rec["pass"] = False
            rec["text"] = f"Run {n}: with {given} the program crashed: {e}. Fail."
        out.append(rec)
    return out
