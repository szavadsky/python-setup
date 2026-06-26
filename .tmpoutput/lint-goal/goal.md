# 
Mid session user override 
WRONG: All `sentence_transformers` imports are inside the function / a lazy loader so
that without the extra, `import python_setup_lint` never imports it. Guard with
`ImportError` → fallback to heuristic. Models download on first use (cache in
HF cache); tests must not require network.

User direction

Test need to require network if we use sentence tansformer. 
In porudction, it could be config guarded BUT - all paths must be tested as per coding rule
.gitignored idemponentn simple cache must be added cor checkMeaningful if it is  relies on local models. 
Decision based on fidelity and PoC - and you need to decide based on grounded data, but if  we are doing it - has to be fully tested feature. 
 WRONG:
   `pytest.importorskip("sentence_transformers")`); these are marked
  `@pytest.mark.slow` (model load/download) so they never run in the default
  suite. 
  
  
  only tests that forces bypass of cache can be marked slow

test_consolidated_real_pipeline_smoke MUST NOT be marked slow - it is important enough to be run every time

DoD includes implementation to best possible fidelity, quality and usability; not a brush of a feature

# _ symbols
Apply  CodingRules.md
Implement custom linter to support
Fix all liting vilations 
**Current rule:** Symbol Convention says `_` prefix = file-private, imported only by tests.

 Tests should import `_`-prefixed symbols from their defining submodule, not through the package `__init__`.

**Automated guard:** `test_runner_private_imports.py` — verifies `runner.__all__` has no `_`-prefixed names.

 Add explicit rule to CodingRules.md: "Tests imports  `_`-prefixed symbols only from the defining submodule, not the package `__init__`." CodingRules.md

 Linting rule, custom if required - no _ prefixed symbols in pyi, _ for package local. 

 # Optimize non slow test runs - got slower then it shall. As required, optimize prod/test code to be under 30s

 # minimum project tests/data
   - a simple python project, not part of project liting
   - planted ALL  possible custom linter checked violations  + 1..2 per tool /critival rules
   - list of violations
   - tested by a separate single large test test/integration.py  
      - setup new - run liner, check violations, check all tools run
      - check setup correct
      - edit configs - rules overlay -check lint result
      - check resetup, uppdate
      - dry run hooks for git, results as expect
   - .gitignore everuthing that is added by setup
# reorganize src/python_setup_lint/checkers as per proper folder structure/architecture
# prohibit  
   msgs = {
        "W9701": (
            "Public function '%s' in '%s' is missing @beartype decorator",
            "missing-beartype",
            "All public functions should have @beartype for runtime type enforcement.",
        ),
    }
     msgs: dict[str, MessageDefinitionTuple] = {}
     Prohibit first hand unnamened tuple. shall be (reword as per pythin best practices) named tuple, dataclass, protocol where fields are named.
     dict[str 
        - dict with key a genric type shall be prohibited. If it is bona fide generic, then it has to be a named type that define what it is (LintRuleId). Other wise enum, literal, etc - word as per python best practive

    Specify in CodingRules (keep same semantic compression style) 
    Fix anywhere in the code
    Custom linter

# prohibit 
    def emit_import_contract_violations(checker: StubChecker) -> None:  # pylint: disable=missing-beartype 
    from pylint.lint import PyLinter  # noqa: TC002
  MUST BE A COMMENT WITH TECHNICAL JUSTFIICATION
  Must be linted (custom? or researcg what is available)'
  Common helper checkIfMeangful(Rule (can be Empty, codeContext, comment))
   - wil use in the future

# generic type return 
   ) -> int:
    """Idempotently install python-setup tooling into *project_dir*.

    Returns exit code (0 = success, 1 = errors).
    """

OK ONLY if Returns {meaningful} docstring
eg not ok 
 """Two-phase annotation normalizer for stub-vs-impl comparison.

    Phase 1: Astroid ``infer()`` — resolved type string (~94% hit rate).
    Phase 2: AST-string walking + rewrite rules — fallback for Uninferable (~6%).
    """

    @staticmethod
    def normalize(ann_node: nodes.NodeNG | None) -> str  
# Change DOCSTRING custom linter
   _pyInternalHelper may have a docstring
# Experiment with best way checkIfMeangful given our code base
  - try some NLP not LLLM python library
  - embedder (bge-small)
  - reranker (jina)
#  Project 
  - all linting violations are fixed unless specific exceptions in line with CodingRules 
  - specificy universal exception nnumber of parameters for test only
# Update version
# README.md
  - short, user focused
  - overlays and custom checks -> separate linked docs in docs/

DoD
  - project is perfectly functional, tangible, ready to use /install, code well organized, LoC minimized, no liniting violations excpet small number explicitly expected
  - may have generic expections for tests and py vs pyi if justified as per coding rules