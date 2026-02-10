from pathlib import Path
path = Path('.pre-commit-config.yaml')
text = path.read_text(encoding='utf-8')
marker = 'minimum_pre_commit_version: " "3.6.0'
if marker not in text:
    raise SystemExit('marker missing')
if 'default_stages: [pre-commit]' not in text:
    text = text.replace(marker, marker + '\\n\\ndefault_stages: [pre-commit]', 1)
hook = '      - id: forbid-control-chars\\n'
if hook not in text:
    raise SystemExit('hook missing')
files_pattern = '(src/.*|tests/.*|docs/.*|.*\\.(md|txt|json|ya?ml|py))$'
insert = hook + '      - id: forbid-smart-quotes\\n        name: Forbid smart quotes/dashes (unicode punctuation)\\n        entry: python tools/replace_quotes.py --check\\n        language: system\\n        pass_filenames: true\\n        types: [text]\\n        files: " + files_pattern + "\\n        stages: [pre-commit]\\n\\n      - id: fix-smart-quotes\\n        name: Fix smart quotes/dashes (manual)\\n        entry: python tools/replace_quotes.py\\n        language: system\\n        pass_filenames: true\\n        types: [text]\\n        files: " + files_pattern + "\\n        stages: [manual]\\n'
text = text.replace(hook, insert, 1)
path.write_text(text, encoding='utf-8')
