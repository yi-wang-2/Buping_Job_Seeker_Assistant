from src.utils import chrome_utils


class _FakeChromeDriver:
    def __init__(self):
        self.commands = []
        self.urls = []

    def execute_cdp_cmd(self, command, params):
        self.commands.append((command, params))
        if command == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "main-frame"}}}
        if command == "Page.printToPDF":
            return {"data": "cGRm"}
        return {}

    def get(self, url):
        self.urls.append(url)
        assert url == "about:blank"


def test_html_to_pdf_injects_document_without_file_navigation(monkeypatch):
    monkeypatch.setattr(chrome_utils.time, "sleep", lambda _seconds: None)
    driver = _FakeChromeDriver()

    result = chrome_utils.HTML_to_PDF("<main>resume</main>", driver)

    assert result == "cGRm"
    assert driver.urls == ["about:blank"]
    command_names = [command for command, _params in driver.commands]
    assert command_names == [
        "Page.enable",
        "Page.getFrameTree",
        "Page.setDocumentContent",
        "Page.printToPDF",
    ]
    injected = driver.commands[2][1]
    assert injected["frameId"] == "main-frame"
    assert "<main>resume</main>" in injected["html"]
    assert "buping-pdf-centering-fix" in injected["html"]
