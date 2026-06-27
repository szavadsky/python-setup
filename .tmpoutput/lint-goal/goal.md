# extra note
  Semantic meaningful checker with decided threshold shall be testes with a test with large > 50 number of calls on realistic "meaningful" and meaningless comments. threadholds and algo mau need afdjustment once test is implemented

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
  - project is perfectly functional, self linting wih all rules and tools, tangible, ready to use /install, code well organized, LoC minimized, no liniting violations excpet small number explicitly expected
  - may have generic expections for tests and py vs pyi if justified as per coding rules


  ---- FEEDBACK ACCUMULATED from previous iterations

  # Another critical feedback
  - WE MUST retain ability to chek pyi<->py as per coding rules and implemented checkes 
  I understand pyi was excluded from pylint and it created issues with false positive duplciates
  They must be run, test shall not be used for linting (as we deliver linter, not tests)
  Research and consider options. Eg, we can run pylint twice as part of pipeline
  BUT - ALL CHECKS MUST BE EXECUTED, NO checks masked.

# ANOTHER USE CORRECTION PAST ITER 5
gitignored idemponentn simple cache must be added cor checkMeaningful if it is  relies on local models. 
MEANS: use deffault hugging face models cache, document how to pre-load them as fallback if needed
+ Cache results (based on function arguments) - .gitignored cache to avoid expensive emebdder/reranker calls 
Conider: do we need both embedder and reranker or only 1? because currently emebdder is just quick fail for reranler, make sense only if substantiallu cheaper

Document how end user need to configure (shall be easy) use vs no use of semantic, and depedenency shall be as seamless to user as possible
# 
Mid session user override 
WRONG: All `sentence_transformers` imports a (ImportError fallback to heuristic)

User direction

Test need to require network if we use sentence tansformer. 
In porudction, it must  be config guarded, enabled by default  BUT - all paths must be tested as per coding rule
.
Decision based on fidelity and PoC - and you need to decide based on grounded data, but if  we are doing it - has to be fully tested feature. 
 WRONG:
   `pytest.importorskip("sentence_transformers")`); these are marked
  `@pytest.mark.slow` (model load/download) so they never run in the default
  suite. 
  
  
  only tests that forces bypass of cache can be marked slow

test_consolidated_real_pipeline_smoke MUST NOT be marked slow - it is important enough to be run every time

DoD includes implementation to best possible fidelity, quality and usability; not a brush of a feature