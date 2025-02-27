from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from unstructured_api_tools.pipelines.api_conventions import get_pipeline_path

from prepline_general.api.app import app
import tempfile

MAIN_API_ROUTE = get_pipeline_path("general")


def test_general_api_health_check():
    client = TestClient(app)
    response = client.get("/healthcheck")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "example_filename, content_type",
    [
        ("fake-email.msg", None),
        ("spring-weather.html.json", None),
        ("alert.eml", None),
        ("announcement.eml", None),
        ("fake-email-attachment.eml", None),
        ("fake-email-image-embedded.eml", None),
        ("fake-email.eml", None),
        ("fake-html.html", "text/html"),
        pytest.param(
            "fake-power-point.ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            marks=pytest.mark.xfail(reason="See CORE-796"),
        ),
        ("fake-text.txt", "text/plain"),
        pytest.param(
            "fake.doc",
            "application/msword",
            marks=pytest.mark.xfail(reason="Encoding not supported yet"),
        ),
        ("fake.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("family-day.eml", None),
        pytest.param("fake-excel.xlsx", None, marks=pytest.mark.xfail(reason="not supported yet")),
        ("layout-parser-paper.pdf", "application/pdf"),
        ("layout-parser-paper-fast.jpg", "image/jpeg"),
    ],
)
def test_general_api(example_filename, content_type):
    client = TestClient(app)
    test_file = Path("sample-docs") / example_filename
    response = client.post(
        MAIN_API_ROUTE, files=[("files", (str(test_file), open(test_file, "rb"), content_type))]
    )
    assert response.status_code == 200
    assert len(response.json()) > 0
    for i in response.json():
        assert i["metadata"]["filename"] == example_filename
    assert len("".join(elem["text"] for elem in response.json())) > 20

    # Just hit the second path (posting multiple files) to bump the coverage
    # We'll come back and make smarter tests
    response = client.post(
        MAIN_API_ROUTE,
        files=[
            ("files", (str(test_file), open(test_file, "rb"), content_type)),
            ("files", (str(test_file), open(test_file, "rb"), content_type)),
        ],
    )
    assert response.status_code == 200
    assert all(x["metadata"]["filename"] == example_filename for i in response.json() for x in i)

    assert len(response.json()) > 0


def test_coordinates_param():
    """
    Verify that responses do not include coordinates unless requested
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper-fast.jpg"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
    )

    assert response.status_code == 200
    response_without_coords = response.json()

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"coordinates": "true"},
    )

    assert response.status_code == 200
    response_with_coords = response.json()

    # Each element should be the same except for the coordinates field
    for i in range(len(response_with_coords)):
        assert "coordinates" in response_with_coords[i]
        del response_with_coords[i]["coordinates"]
        assert response_with_coords[i] == response_without_coords[i]


def test_strategy_param_400():
    """Verify that we get a 400 if we pass in a bad strategy"""
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper.pdf"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
        data={"strategy": "not_a_strategy"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "example_filename",
    [
        "fake-xml.xml",
    ],
)
def test_general_api_returns_400_unsupported_file(example_filename):
    client = TestClient(app)
    test_file = Path("sample-docs") / example_filename
    filetype = "application/xml"
    response = client.post(
        MAIN_API_ROUTE, files=[("files", (str(test_file), open(test_file, "rb"), filetype))]
    )
    assert response.json() == {
        "detail": f"Unable to process {str(test_file)}: " f"File type {filetype} is not supported."
    }
    assert response.status_code == 400


def test_general_api_returns_500_bad_pdf():
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf")
    tmp.write(b"This is not a valid PDF")
    client = TestClient(app)
    response = client.post(
        MAIN_API_ROUTE, files=[("files", (str(tmp.name), open(tmp.name, "rb"), "application/pdf"))]
    )
    assert response.json() == {"detail": f"{tmp.name} does not appear to be a valid PDF"}
    assert response.status_code == 400
    tmp.close()
