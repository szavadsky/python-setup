"""Module with planted duplicate for R0801 detection."""


def _duplicate_b():
    """Second half of planted duplicate for R0801 detection."""
    a = 1
    b = 2
    c = a + b
    d = c * 2
    e = d - a
    f = e // 3
    g = f + b
    h = g * a
    i = h - c
    j = i * 2
    k = j // d
    return k
