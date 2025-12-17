from pathlib import Path
lines = Path('src/ai/config.py').read_text().splitlines()
for i in range(360, 460):
    print(i, repr(lines[i]))
