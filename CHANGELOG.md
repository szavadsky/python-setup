# Changelog

## v0.5.0 (2026-06-21) — ty config-file fix + RunnerConfig.config_paths stub published + portable PYI048 + pylint rcfile auto-discovery contract + README sections

Adds `ty check` `--config-file` flag (previous `--config` was rejected by ty>=0.0.49).
The `RunnerConfig.config_paths` field — present in source since T9 — now ships in the published `runner/types.pyi`.
Portable ruff `*.pyi` per-file-ignores gains `PYI048` (docstring + `...` is two statements; allowed in stubs).
Adds the 4-test contract for `_PylintLintTool._resolve_pylintrc` auto-discovery/explicit-override/missing-None/build-injects-rcfile.
README gains the 3 user-facing sections: 'Custom lint steps via pyproject.toml', 'Using python-setup in another project', 'Re-baselining'.

**NOTE:** the v0.4.0 tag existed in git but the wheel was never rebuilt from it — v0.5.0 supersedes both v0.3.0's published wheel and the v0.4.0 tag.
