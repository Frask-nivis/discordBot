import unittest

from cogs.link_converter import _PageMetaParser, _extract_url


class LinkConverterHelpersTests(unittest.TestCase):
    def test_extract_url_strips_trailing_punctuation(self):
        self.assertEqual(
            _extract_url("lihat ini: https://example.com/video?t=1)."),
            "https://example.com/video?t=1",
        )

    def test_extract_url_rejects_non_http_text(self):
        self.assertIsNone(_extract_url("discord.gg/example"))

    def test_page_meta_parser_reads_open_graph_description(self):
        parser = _PageMetaParser()
        parser.feed(
            '<html><head><meta property="og:title" content="Judul">'
            '<meta property="og:description" content="Ringkasan singkat"></head></html>'
        )
        self.assertEqual(parser.og_title, "Judul")
        self.assertEqual(parser.og_description, "Ringkasan singkat")


if __name__ == "__main__":
    unittest.main()
