from pathlib import Path
path = Path('src/ai/config.py')
lines = path.read_text().splitlines()
start = None
end = None
for i, line in enumerate(lines):
    if line.strip().startswith('def _ai_section_name_from_path'):
        start = i
    if start is not None and line.strip().startswith('def _resolve_env_name_for_vision'):
        end = i
        break
if start is None or end is None:
    raise SystemExit('markers not found')
new_lines = lines[:start] + lines[end:]
path.write_text('\n'.join(new_lines) + '\n')
