from pathlib import Path
lines = Path('src/ai/config.py').read_text().splitlines()
for i in range(440, 520):
    if i < len(lines):
        print(i, repr(lines[i]))
