# SPDX-License-Identifier: GPL-3.0-only
# scripts/peek_folder_terms.py
import sqlite3
import sys

db = sys.argv[1]
folder = sys.argv[2]

con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
cur = con.cursor()
rows = cur.execute(
    """
SELECT t.canonical, ft.weight, ft.status
FROM folder_terms ft JOIN terms t ON t.id=ft.term_id
JOIN folders f ON f.id=ft.folder_id
WHERE f.path=? ORDER BY ft.weight DESC LIMIT 20
""",
    (folder,),
).fetchall()
for r in rows:
    print(f"{r['canonical']}\t{r['weight']:.3f}\t{r['status']}")
con.close()
