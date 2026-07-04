Implement M10 — Documentation alignment

Read {F}/plan1.md:69-70 for the full spec.

## What to do

1. **Fix `docs/troubleshooting.md:22-28`**: The "Expected" symlink example shows an absolute path (`-> /home/.../python-setup/config/.pylintrc`) — change to a relative target (`-> .venv/lib/python3.14/site-packages/python_setup_lint/config/.pylintrc`) and clarify the symlink is gitignored/local.

2. **Add a troubleshooting entry** for "standalone tool differs from runner" pointing at root config symlinks (M3) as the parity mechanism.

3. **Update `docs/overlays.md`** if it references absolute symlink expectations — check for any absolute path references.

## Acceptance
- `grep -rn /home/slava docs/` → no hardcoded absolute paths
- Troubleshooting doc shows relative symlink examples
- All changes committed with descriptive message
