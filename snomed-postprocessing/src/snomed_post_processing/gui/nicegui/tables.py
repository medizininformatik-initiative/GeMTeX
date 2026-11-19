"""Shared styling for vertically resizable NiceGUI AG Grid tables."""


def resizable_table(grid, *, min_height=160):
    # Do not set inline height: browser drag height must survive grid data updates.
    grid.style(f"resize:vertical;overflow:auto;min-height:{min_height}px;max-width:100%;")
    return grid
