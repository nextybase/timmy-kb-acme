from pathlib import Path

path = Path("tools/clean_client_workspace.py")
text = path.read_text(encoding="utf-8")
text = text.replace("from typing import Any, List, Tuple", "from typing_Postfix")
