from pathlib import Path
lines = Path('src/ai/config.py').read_text().splitlines()
for i,line in enumerate(lines[200:280], start=200):
    print(i, repr(line))
