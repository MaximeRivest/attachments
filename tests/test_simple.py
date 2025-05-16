import unittest

class TestSimple(unittest.TestCase):
    def test_truth(self):
        self.assertTrue(True, "This should always pass")

if __name__ == '__main__':
    unittest.main() 