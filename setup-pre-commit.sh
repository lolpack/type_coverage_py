# 1. Once per clone
pip install pre-commit          # or pipx install pre‑commit
pre-commit install              # writes .git/hooks/pre-commit

# 2. Upgrade hooks when you bump versions in YAML
pre-commit autoupdate

# 3. Manual full run (good before the first push or when you add the hook)
pre-commit run --all-files
