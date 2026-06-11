import io
import json
import unittest

import fitz
from fastapi.testclient import TestClient

from app import app


def make_pdf_bytes(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=12)
        y += 24
    data = doc.tobytes()
    doc.close()
    return data


class LocateBatchApiTest(unittest.TestCase):
    def test_locates_multiple_queries_in_one_pdf(self):
        pdf_bytes = make_pdf_bytes([
            "Alpha project scope",
            "Beta delivery terms",
        ])
        payload = {
            "queries": [
                {"id": "a", "text": "Alpha project scope"},
                {"id": "missing", "text": "Not in this document"},
            ]
        }

        client = TestClient(app)
        response = client.post(
            "/locate/batch",
            files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"queries": json.dumps(payload)},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["filename"], "sample.pdf")
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["found_count"], 1)
        self.assertEqual(body["not_found_count"], 1)

        first = body["results"][0]
        self.assertEqual(first["id"], "a")
        self.assertEqual(first["query"], "Alpha project scope")
        self.assertTrue(first["found"])
        self.assertEqual(first["page"], 1)
        self.assertEqual(first["match_layer"], 1)
        self.assertGreater(first["width"], 0)
        self.assertGreater(first["height"], 0)
        self.assertGreater(len(first["bboxes"]), 0)

        second = body["results"][1]
        self.assertEqual(second["id"], "missing")
        self.assertEqual(second["query"], "Not in this document")
        self.assertFalse(second["found"])
        self.assertEqual(second["message"], "Sentence not found in PDF.")

    def test_accepts_simple_json_string_array(self):
        pdf_bytes = make_pdf_bytes(["Simple array query"])

        client = TestClient(app)
        response = client.post(
            "/locate/batch",
            files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"queries": json.dumps(["Simple array query"])},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["results"][0]["query"], "Simple array query")
        self.assertTrue(body["results"][0]["found"])

    def test_rejects_empty_batch_queries(self):
        pdf_bytes = make_pdf_bytes(["Anything"])

        client = TestClient(app)
        response = client.post(
            "/locate/batch",
            files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"queries": json.dumps([])},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("queries", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
