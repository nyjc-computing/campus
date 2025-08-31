import wsgi
import unittest

class TestWSGI(unittest.TestCase):
    def test_wsgi_import(self):
        try:
            from wsgi import app
            self.assertIsNotNone(app, "App should not be None")
        except Exception as e:
            self.fail(f"Instantiating WSGI app failed: {e}")

if name == "__main__":
    unittest.main()