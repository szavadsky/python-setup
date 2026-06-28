"""Stub for mod.py — planted violations for stub-impl fidelity checkers."""

_private_var: int = 0  # triggers pyi-underscore-symbol (W9707)

# annotation-mismatch: .pyi says str, .py says int
annot_mismatch_var: str

# impl-missing-annotation: .pyi annotates, .py does not
impl_missing_annot_var: str

# annotation-unverifiable: .pyi uses slice syntax (unverifiable by normalizer)
unverifiable_var: list[1:2]

# signature-mismatch: .pyi has (a: int, b: str), .py has (a: int)
def sig_mismatch_func(a: int, b: str) -> bool: ...

# symbol-kind-mismatch: .pyi says class, .py says function
class KindMismatch: ...

# stub-symbol-missing: declared in .pyi but absent from .py
def stub_only_func() -> None: ...
