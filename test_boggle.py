import unittest
import boggle

class TestBoggle(unittest.TestCase):
    """
    our test suit for boggle
    """
    def test_can_create_an_empty_grid(self):
        """
        test to see if we can create an empty grid
        """
        grid = boggle.make_grid(0,0)
        self.assertEqual(len(grid),0)   
        
    def test_grid(self):
        """
        make a grid test of 6 dimensions
        """
        grid = boggle.make_grid(2,3)
        self.assertEqual(len(grid),6)
        
        
    def test_grid_coordinates(self):
        grid = boggle.make_grid(2, 2)
        self.assertIn((0, 0), grid)
        self.assertIn((0, 1), grid)
        self.assertIn((1, 0), grid)
        self.assertIn((1, 1), grid)
        self.assertNotIn((2, 2), grid)
    

