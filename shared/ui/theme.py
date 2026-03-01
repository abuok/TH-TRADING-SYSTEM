"""
shared/ui/theme.py
Official Dashboard Theme for TradeHall Trading System.
Based on the Network Timeline accent palette.
"""

from typing import Dict

ACCENTS = {
    "orange": "#F2994A",
    "yellow": "#F2C94C",
    "purple": "#9B51E0",
    "cyan":   "#56CCF2",
    "green":  "#27AE60",
    "pink":   "#EB2F96",
}

NEUTRALS = {
    "background": "#0B0B10",
    "surface":    "#12121A",
    "border":     "#2A2A35",
    "text":       "#E6E6F0",
    "muted":      "#A1A1B3",
}

def hex_to_rgb(hex_str: str) -> tuple:
    """Converts #RRGGBB to (R, G, B)."""
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def rgba(hex_str: str, alpha: float) -> str:
    """Returns an rgba() CSS string."""
    r, g, b = hex_to_rgb(hex_str)
    return f"rgba({r}, {g}, {b}, {alpha})"

def glow(accent_key_or_hex: str) -> str:
    """
    Returns a CSS style string for the 'neon ring' look.
    Accepts either an accent name (e.g. 'green') or a hex code.
    """
    color = ACCENTS.get(accent_key_or_hex.lower(), accent_key_or_hex)
    
    # Glow Rings:
    # Outer: 35% alpha
    # Inner: 20% alpha
    outer = rgba(color, 0.35)
    inner = rgba(color, 0.20)
    
    return (
        f"border: 1px solid {color}; "
        f"box-shadow: 0 0 8px {outer}, inset 0 0 4px {inner};"
    )
