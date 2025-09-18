def test__drive_list_pdfs_paginates(monkeypatch):
    # Importa il modulo target (senza prefisso 'src.' per evitare duplicati mypy)
    import ui.services.drive_runner as dr

    # Costruisce un finto service con paginazione su due pagine
    calls = {"count": 0}

    class FakeRequest:
        def __init__(self, page_token=None):
            self.page_token = page_token

        def execute(self):
            calls["count"] += 1
            if self.page_token is None:
                # Prima pagina
                return {
                    "files": [
                        {"id": "id1", "name": "A.pdf", "mimeType": "application/pdf", "size": "10"}
                    ],
                    "nextPageToken": "T2",
                }
            else:
                # Seconda pagina (finale)
                return {
                    "files": [
                        {"id": "id2", "name": "B.pdf", "mimeType": "application/pdf", "size": "20"}
                    ],
                }

    class FakeFiles:
        def list(self, **kwargs):
            return FakeRequest(page_token=kwargs.get("pageToken"))

    class FakeService:
        def files(self):
            return FakeFiles()

    svc = FakeService()
    out = dr._drive_list_pdfs(svc, parent_id="folder123")
    # Deve avere aggregato entrambe le pagine
    assert [f["id"] for f in out] == ["id1", "id2"]
    assert calls["count"] == 2
