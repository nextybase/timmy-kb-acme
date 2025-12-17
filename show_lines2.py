from pathlib import Path
lines = Path('src/ai/config.py').read_text().splitlines()
for i in range(265, 360):
    print(i, repr(lines[i]))
