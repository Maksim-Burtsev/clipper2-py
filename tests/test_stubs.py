"""The .pyi stubs must stay in step with the compiled modules.

Two checks:

* the stubs and the runtime export the same public names, and every stub overload of a
  function or method agrees with the signature pybind11 puts in its ``__doc__`` -- same
  parameter names in the same order, same keyword-only marker, same defaults. A stub
  overload may leave out a runtime parameter that has a default (that is how the 64 family
  drops ``precision``), but between them the overloads must mention every one of them.
* ``mypy --strict`` over tests/typing_sample.py, which pins the interesting return types
  with ``typing.assert_type``.

Dunders are left out: they are pybind11 plumbing (``__eq__``, ``__hash__``,
``_pybind11_conduit_v1_``) or, like ``__iter__``, the Python-level shape of a C-level
protocol slot. ``__init__`` is checked, since a constructor is API.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

import clipper2
import clipper2.z

STUBS = {
    clipper2: Path(clipper2.__file__).with_name("__init__.pyi"),
    clipper2.z: Path(clipper2.__file__).with_name("z.pyi"),
}

# A parameter: its name, whether it is keyword-only, and its default as source text.
Param = tuple[str, bool, str | None]


def _public(name: str) -> bool:
    return not name.startswith("_") or name == "__version__"


# --- the runtime side: pybind11 renders signatures into __doc__ -------------------------


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise AssertionError(f"unbalanced parentheses in {text!r}")


def _split_top_level(text: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [part.strip() for part in parts if part.strip()]


def _index_top_level(text: str, char: str) -> int:
    depth = 0
    for i, c in enumerate(text):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == char and depth == 0:
            return i
    return -1


def _parse_param_list(text: str) -> list[Param]:
    params: list[Param] = []
    keyword_only = False
    for token in _split_top_level(text):
        if token.startswith("*"):  # '*', '*args', '**kwargs'
            keyword_only = True
            continue
        if token == "/":
            continue
        eq = _index_top_level(token, "=")
        default = token[eq + 1 :].strip() if eq >= 0 else None
        head = token[:eq] if eq >= 0 else token
        params.append((head.split(":", 1)[0].strip(), keyword_only, default))
    return params


def runtime_signatures(obj: object, name: str) -> list[list[Param]]:
    """The parameter lists pybind11 documents for `obj`, one per overload."""
    doc = getattr(obj, "__doc__", None) or ""
    lines = doc.splitlines()
    if not lines:
        return []
    if len(lines) > 1 and lines[1].strip() == "Overloaded function.":
        prefix = re.compile(rf"^\d+\. {re.escape(name)}\(")
        sigs = [line.split(". ", 1)[1] for line in lines if prefix.match(line.strip())]
    elif lines[0].startswith(f"{name}("):
        sigs = [lines[0]]
    else:
        sigs = []  # not a pybind11 signature (e.g. object.__init__'s docstring)
    out = []
    for sig in sigs:
        open_paren = sig.index("(")
        out.append(_parse_param_list(sig[open_paren + 1 : _matching_paren(sig, open_paren)]))
    return out


def runtime_members(cls: type) -> dict[str, object]:
    return {n: getattr(cls, n) for n in vars(cls) if _public(n)}


# --- the stub side ----------------------------------------------------------------------


def stub_params(node: ast.FunctionDef) -> list[Param]:
    args = node.args
    positional = args.posonlyargs + args.args
    defaults: list[str | None] = [None] * (len(positional) - len(args.defaults))
    defaults += [ast.unparse(d) for d in args.defaults]
    params: list[Param] = [
        (arg.arg, False, default) for arg, default in zip(positional, defaults)
    ]
    for arg, default_node in zip(args.kwonlyargs, args.kw_defaults):
        params.append(
            (arg.arg, True, None if default_node is None else ast.unparse(default_node))
        )
    return params


def stub_scope(body: list[ast.stmt]) -> tuple[dict[str, list[ast.FunctionDef]], set[str]]:
    """Functions (grouped by name, in overload order) and every name the scope binds."""
    functions: dict[str, list[ast.FunctionDef]] = {}
    names: set[str] = set()
    for node in body:
        if isinstance(node, ast.FunctionDef):
            functions.setdefault(node.name, []).append(node)
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # PEP 484: only `import X as X` re-exports; a plain import is stub-private.
            names.update(a.asname for a in node.names if a.asname == a.name)
    return functions, names


def stub_classes(body: list[ast.stmt]) -> dict[str, ast.ClassDef]:
    classes = {n.name: n for n in body if isinstance(n, ast.ClassDef)}
    # `PolyTree64 = PolyPath64` is upstream's alias, and so it is at runtime.
    for node in body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            target = node.targets[0]
            if isinstance(target, ast.Name) and node.value.id in classes:
                classes[target.id] = classes[node.value.id]
    return classes


# --- comparison --------------------------------------------------------------------------


def _compatible(stub: list[Param], runtime: list[Param]) -> bool:
    """A stub overload agrees with one runtime overload."""
    found: dict[str, Param] = {}
    cursor = 0
    for name, kw_only, default in stub:
        while cursor < len(runtime) and runtime[cursor][0] != name:
            cursor += 1
        if cursor == len(runtime):
            return False  # unknown, or out of order
        if runtime[cursor][1] != kw_only:
            return False
        if default is not None and default != runtime[cursor][2]:
            return False
        found[name] = runtime[cursor]
        cursor += 1
    # Only optional parameters may be left out of an overload.
    return all(p[0] in found or p[2] is not None for p in runtime)


def check_signature(what: str, obj: object, name: str, overloads: list[ast.FunctionDef]) -> None:
    runtime = runtime_signatures(obj, name)
    if not runtime:
        return
    stubs = [stub_params(node) for node in overloads]
    for params in stubs:
        assert any(_compatible(params, sig) for sig in runtime), (
            f"{what}: stub overload ({', '.join(p[0] for p in params)}) matches no "
            f"runtime signature {[[p[0] for p in s] for s in runtime]}"
        )
    for sig in runtime:
        assert any(_compatible(params, sig) for params in stubs), (
            f"{what}: runtime overload ({', '.join(p[0] for p in sig)}) is not covered "
            f"by the stub"
        )
    stub_names = {p[0] for params in stubs for p in params}
    runtime_names = {p[0] for sig in runtime for p in sig}
    assert stub_names == runtime_names, (
        f"{what}: parameter names differ, stub {sorted(stub_names)} vs runtime "
        f"{sorted(runtime_names)}"
    )


@pytest.fixture(scope="module", params=list(STUBS), ids=lambda m: m.__name__)
def module_and_stub(request: pytest.FixtureRequest) -> tuple[types.ModuleType, ast.Module]:
    module = request.param
    return module, ast.parse(STUBS[module].read_text(encoding="utf-8"))


def test_module_names_match(module_and_stub: tuple[types.ModuleType, ast.Module]) -> None:
    module, tree = module_and_stub
    _, declared = stub_scope(tree.body)
    assert {n for n in declared if _public(n)} == {n for n in dir(module) if _public(n)}


def test_class_members_match(module_and_stub: tuple[types.ModuleType, ast.Module]) -> None:
    module, tree = module_and_stub
    classes = stub_classes(tree.body)
    for name, node in classes.items():
        runtime_cls = getattr(module, name)
        _, declared = stub_scope(node.body)
        assert {n for n in declared if _public(n)} == set(runtime_members(runtime_cls)), (
            f"{module.__name__}.{name}"
        )


def test_function_signatures_match(module_and_stub: tuple[types.ModuleType, ast.Module]) -> None:
    module, tree = module_and_stub
    functions, _ = stub_scope(tree.body)
    for name, overloads in functions.items():
        check_signature(f"{module.__name__}.{name}", getattr(module, name), name, overloads)


def test_method_signatures_match(module_and_stub: tuple[types.ModuleType, ast.Module]) -> None:
    module, tree = module_and_stub
    for name, node in stub_classes(tree.body).items():
        runtime_cls = getattr(module, name)
        methods, _ = stub_scope(node.body)
        for method, overloads in methods.items():
            if method.startswith("_") and method != "__init__":
                continue
            check_signature(
                f"{module.__name__}.{name}.{method}",
                getattr(runtime_cls, method),
                method,
                overloads,
            )


def test_mypy_strict_on_the_sample() -> None:
    pytest.importorskip("mypy")
    sample = Path(__file__).with_name("typing_sample.py")
    # The directory that holds the clipper2 package, editable checkout or site-packages.
    # mypy finds an installed package by itself and refuses site-packages in MYPYPATH.
    root = STUBS[clipper2].parent.parent
    env = dict(os.environ)
    if root.name != "site-packages":
        env["MYPYPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(sample)],
        capture_output=True,
        text=True,
        env=env,
        cwd=sample.parent,
    )
    assert result.returncode == 0, result.stdout + result.stderr
