"""Two-phase annotation normalizer for stub-vs-impl comparison.

Phase 1: Astroid ``infer()`` — resolved type string (~94% hit rate).
Phase 2: AST-string walking + rewrite rules — fallback for Uninferable (~6%).
"""

from astroid import nodes

class AnnotationNormalizer:
    """Two-phase annotation normalizer for stub-vs-impl comparison.

    Phase 1: Astroid ``infer()`` — resolved type string (~94% hit rate).
    Phase 2: AST-string walking + rewrite rules — fallback for Uninferable (~6%).
    """

    @staticmethod
    def normalize(ann_node: nodes.NodeNG | None) -> str | None: ...
