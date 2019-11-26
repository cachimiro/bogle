def make_grid(height, width):
    """
    create a grid
    """
    return{(row, col): '' for row in range(height)
        for col in range(width)
    }
    