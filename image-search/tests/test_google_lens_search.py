from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from google_lens_search import extract_result_urls, normalize_result_url


class GoogleLensSearchTests(unittest.TestCase):
    def test_normalize_result_url_unwraps_google_redirect(self):
        wrapped = (
            "https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fitem%3Fid%3D7"
            "&sa=U"
        )

        self.assertEqual(
            normalize_result_url(wrapped), "https://example.com/item?id=7"
        )

    def test_extract_result_urls_deduplicates_and_preserves_order(self):
        html = """
        <main>
          <section id="visual-matches">
            <a href="https://one.example/a">First</a>
            <a href="https://two.example/b">Second</a>
            <a href="https://one.example/a">Duplicate</a>
            <a href="https://www.google.com/search?q=ignored">Google navigation</a>
            <a href="https://three.example/c">Third</a>
          </section>
        </main>
        """

        self.assertEqual(
            extract_result_urls(html, limit=2),
            ["https://one.example/a", "https://two.example/b"],
        )


if __name__ == "__main__":
    unittest.main()
