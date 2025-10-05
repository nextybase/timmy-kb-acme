from pathlib import Path

path = Path("src/ui/app.py")
text = path.read_text(encoding="utf-8")
if "st.rerun()" not in text:
    raise SystemExit("expected rerun calls")
if "st.experimental_rerun()" in text:
    raise SystemExit("unexpected experimental rerun calls")
old = "                    st.success(f\"Cliente '{slug}' eliminato. {message}\")\n"
if old not in text:
    raise SystemExit("success line not found")
text = text.replace(old, "                    st.toast(f\"Cliente '{slug}' eliminato.\")\n")
path.write_text(text, encoding="utf-8")
