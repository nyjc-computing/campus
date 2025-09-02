import unittest
import os

class TestWSGI(unittest.TestCase):
    def test_wsgi_import(self):
        for deploy_mode in ("apps", "vault"):
            os.environ["DEPLOY"] = deploy_mode
            import wsgi 
            from wsgi import app
            self.assertIsNotNone(app, "App should not be None")


if __name__ == "__main__":
    unittest.main()
