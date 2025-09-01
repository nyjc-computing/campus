import wsgi
import unittest
import os

class TestWSGI(unittest.TestCase):
    def test_wsgi_import(self):
        os.environ["DEPLOY"] = "apps"
        from wsgi import app
        self.assertIsNotNone(app, "App should not be None")

if __name__ == "__main__":
    unittest.main()