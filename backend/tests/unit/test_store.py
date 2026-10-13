"""Tests for the feedback storage helper."""

import os
from unittest.mock import patch

import pytest

from src.constants import FEEDBACK_DIR
from src.exceptions import NoDataFound
from src.store import Storator3000


class TestStorator:
    """Tests for the feedback storage helper."""

    def test_ensure_directories(self, monkeypatch, tmp_path):
        """Create the feedback and review storage directories."""
        results_dir = tmp_path / "results"
        reviews_dir = tmp_path / "reviews"
        monkeypatch.setattr("src.store.FEEDBACK_DIR", str(results_dir))
        monkeypatch.setattr("src.store.REVIEWS_DIR", str(reviews_dir))

        Storator3000.ensure_directories()

        assert results_dir.is_dir()
        assert reviews_dir.is_dir()

    @patch("os.path.exists")
    def test_get_logs_exists(self, mock_exists, storator):
        """Return each feedback JSON file when storage exists."""
        mock_exists.return_value = True
        expected_files = ["file1.json", "file2.json", "file3.json"]
        expected_files = [os.path.join(FEEDBACK_DIR, file) for file in expected_files]
        expected_files = sorted(expected_files)

        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                (FEEDBACK_DIR, [], ["file1.json"]),
                (FEEDBACK_DIR, [], ["file2.json"]),
                (FEEDBACK_DIR, [], ["file3.json"]),
            ]
            files = storator.get_logs()
            assert files == expected_files

    @patch("os.path.exists")
    def test_get_logs_empty(self, mock_exists, storator):
        """Raise when storage contains no feedback JSON files."""
        mock_exists.return_value = True
        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [(FEEDBACK_DIR, [], [])]
            with pytest.raises(NoDataFound):
                storator.get_logs()

    @patch.object(Storator3000, "get_logs")
    def test_get_stats(self, mock_get_logs, storator):
        """Count the stored feedback files."""
        mock_get_logs.return_value = [
            "/path/123.json",
            "/path/234.json",
            "/path/345.json",
        ]
        expected_stats = {"total_reports": 3}
        stats = storator.get_stats()
        assert stats == expected_stats

    @patch.object(Storator3000, "get_logs")
    def test_get_stats_no_data(self, mock_get_logs, storator):
        """Return zero reports when no feedback data is present."""
        mock_get_logs.side_effect = NoDataFound()
        assert storator.get_stats() == {"total_reports": 0}
