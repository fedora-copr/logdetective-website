"""
Test the API /download endpoint.
"""

import tarfile
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api import app


class TestDownloadEndpoint:
    """Tests for the /download endpoint - with and without `since` parameter."""

    def test_download_serves_prebuilt_archive(self, tmp_path, monkeypatch):
        """Test that the /download endpoint serves a prebuilt archive if it exists.
        Archives sit in the parent of FEEDBACK_DIR (i.e. /persistent/)"""

        results_dir = str(tmp_path / "results")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", results_dir)
        archive = tmp_path / "results-2026-07-14.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            dummy = tmp_path / "dummy.txt"
            dummy.write_text("hello")
            tar.add(dummy, arcname="results/results/dummy.txt")

        client = TestClient(app)
        resp = client.get("/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-tar"

    def test_download_no_archive_returns_404(self, tmp_path, monkeypatch):
        """Return 404 for /download if no archive exists."""

        results_dir = tmp_path / "results"
        results_dir.mkdir()
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download")
        assert resp.status_code == 404

    @patch("src.api.date")
    def test_download_since_returns_filtered_archive(
        self, mock_date, tmp_path, monkeypatch
    ):
        """Return a filtered archive for /download?since=<date> and valid date."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        (results_dir / "2026-07-10" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-10" / "copr" / "123" / "a.json").write_text("{}")
        (results_dir / "2026-07-12" / "copr" / "456").mkdir(parents=True)
        (results_dir / "2026-07-12" / "copr" / "456" / "b.json").write_text("{}")
        (results_dir / "2026-07-05" / "koji" / "789").mkdir(parents=True)
        (results_dir / "2026-07-05" / "koji" / "789" / "c.json").write_text("{}")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2026-07-10"})
        assert resp.status_code == 200

        archive_path = tmp_path / "response.tar.gz"
        archive_path.write_bytes(resp.content)
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert any("2026-07-10" in n for n in names)
        assert any("2026-07-12" in n for n in names)
        assert not any("2026-07-05" in n for n in names)

    @patch("src.api.date")
    def test_download_since_includes_boundary_date(
        self, mock_date, tmp_path, monkeypatch
    ):
        """Make sure that results from `since` date are included."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        (results_dir / "2026-07-10" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-10" / "copr" / "123" / "a.json").write_text("{}")
        (results_dir / "2026-07-09" / "copr" / "456").mkdir(parents=True)
        (results_dir / "2026-07-09" / "copr" / "456" / "b.json").write_text("{}")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2026-07-10"})
        assert resp.status_code == 200

        archive_path = tmp_path / "response.tar.gz"
        archive_path.write_bytes(resp.content)
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert any("2026-07-10" in n for n in names)
        assert not any("2026-07-09" in n for n in names)

    @patch("src.api.date")
    def test_download_since_skips_empty_and_non_json_dirs(
        self, mock_date, tmp_path, monkeypatch
    ):
        """Return 204 when matching date dirs exist but contain no JSON files."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        # Empty directory
        (results_dir / "2026-07-10").mkdir(parents=True)
        # Directory with only non-JSON files
        (results_dir / "2026-07-11" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-11" / "copr" / "123" / "notes.txt").write_text("hello")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2026-07-10"})
        assert resp.status_code == 204

    @patch("src.api.date")
    def test_download_since_empty_returns_204(self, mock_date, tmp_path, monkeypatch):
        """Return 204 for /download?since=<date> if no results exist since that date.
        This also applies if the date is in the future."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        (results_dir / "2026-07-01" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-01" / "copr" / "123" / "a.json").write_text("{}")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2099-01-01"})
        assert resp.status_code == 204

    def test_download_since_invalid_date_returns_422(self, tmp_path, monkeypatch):
        """Return 422 for /download?since=<date> if the date is invalid."""

        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(tmp_path / "results"))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "not-a-date"})
        assert resp.status_code == 422

    def test_download_since_too_old_returns_400(self, tmp_path, monkeypatch):
        """Return 400 if the since date is older than DOWNLOAD_SINCE_MAX_DAYS."""

        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(tmp_path / "results"))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2020-01-01"})
        assert resp.status_code == 400
        assert "The 'since' date must be within" in resp.json()["description"]
