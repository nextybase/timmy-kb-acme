Fixture PDF cattivi generate a runtime nei test.

Contenuti creati dal test `tests/test_smoke_e2e.py` usando reportlab:
- nome lunghissimo
- caratteri strani (accenti, simboli, emoji)
- testo "malformato" (caratteri di controllo RTL/combining)
- carico grafico pesante (molti rettangoli/pagine)

Nota: non versioniamo binari PDF; il test li genera nel workspace temporaneo.
