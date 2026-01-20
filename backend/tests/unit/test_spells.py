import responses

from src.spells import (
    ensure_text,
    fetch_text,
    read_json_file,
    read_text_file,
    write_json_file,
)


class TestEnsureText:
    def test_bytes_decoded_as_utf8(self):
        """Bytes should be decoded as UTF-8."""
        utf8_bytes = "Příliš žluťoučký kůň".encode("utf-8")
        result = ensure_text(utf8_bytes)
        assert result == "Příliš žluťoučký kůň"
        assert isinstance(result, str)

    def test_string_passed_through(self):
        """String input should be returned as-is."""
        text = "Příliš žluťoučký kůň"
        result = ensure_text(text)
        assert result == text
        assert isinstance(result, str)

    def test_empty_bytes(self):
        """Empty bytes should return empty string."""
        assert ensure_text(b"") == ""

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert ensure_text("") == ""


class TestFetchText:
    @responses.activate
    def test_encoding_set_to_utf8(self):
        """Response encoding should be set to UTF-8."""
        url = "http://example.com/log.txt"
        # server returns UTF-8 content but doesn't specify charset
        responses.add(
            responses.GET,
            url,
            body="Příliš žluťoučký kůň".encode("utf-8"),
            status=200,
            content_type="text/plain",  # no charset specified
        )

        response = fetch_text(url)

        assert response.encoding == "utf-8"
        assert response.text == "Příliš žluťoučký kůň"


class TestJsonFileIO:
    def test_roundtrip_with_czech_characters(self, tmp_path):
        data = {
            "fail_reason": "Chyba při kompilaci",
            "how_to_fix": "Přidejte závislost na balíček",
            "nested": {"message": "Žluťoučký kůň úpěl ďábelské ódy"},
        }
        file_path = tmp_path / "test.json"

        write_json_file(file_path, data)
        result = read_json_file(file_path)

        assert result == data

    def test_unicode_not_escaped(self, tmp_path):
        data = {"text": "šěčřžýáíé"}
        file_path = tmp_path / "test.json"

        write_json_file(file_path, data)

        # read raw file content to verify no escaping
        raw_content = file_path.read_text(encoding="utf-8")
        assert "šěčřžýáíé" in raw_content
        assert "\\u" not in raw_content


class TestReadTextFile:
    def test_reads_utf8_content(self, tmp_path):
        content = "Příliš žluťoučký kůň úpěl ďábelské ódy"
        file_path = tmp_path / "test.txt"
        file_path.write_text(content, encoding="utf-8")

        result = read_text_file(file_path)

        assert result == content
