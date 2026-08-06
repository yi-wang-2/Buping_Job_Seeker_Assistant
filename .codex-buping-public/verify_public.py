import requests

payload = {
    "style_name": "",
    "resume_language": "zh",
    "resume_content": "personal_information:\n  name: SessionMarker9482\n",
}
response = requests.post("http://127.0.0.1:8000/api/resume/preview", json=payload, timeout=30)
print("preview_status", response.status_code, "marker", "SessionMarker9482" in response.text)

schema = requests.get("http://127.0.0.1:8000/openapi.json", timeout=30).json()
properties = schema["components"]["schemas"]["GenerateResumeResponse"]["properties"]
print("response_fields", sorted(properties))

edited = requests.post(
    "http://127.0.0.1:8000/api/resume/save-edited",
    json={"html": "<!doctype html><html><body>RandomArtifactMarker</body></html>"},
    timeout=120,
)
result = edited.json()
print("edited_status", edited.status_code, "pdf", result.get("pdf_filename"), "html", result.get("html_filename"))
assert result["pdf_filename"].startswith("public_") and len(result["pdf_filename"]) == 43
assert result["html_filename"] == result["pdf_filename"].replace(".pdf", ".html")
