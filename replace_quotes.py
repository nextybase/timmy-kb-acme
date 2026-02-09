from pathlib import Path
path=Path('docs/developer/test_suite.md')
data=path.read_text(encoding='utf-8')
replacements=[(0x2014,'--'),(0x2018, ),(0x2019, ),(0x201c,' ),(0x201d, ')]
for code,val in replacements:
    data=data.replace(chr(code), val)
path.write_text(data, encoding='utf-8')
