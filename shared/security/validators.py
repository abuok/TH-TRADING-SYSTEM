"""
Input validation and sanitization utilities.

Prevents injection attacks, XSS, and invalid data types.
"""

import html
import re
from typing import Pattern


class SecurityValidators:
    """Common security validation patterns."""

    # Patterns for validation
    PRICE_PATTERN: Pattern = re.compile(r"^-?[0-9]+(\.[0-9]{1,8})?$")
    QUANTITY_PATTERN: Pattern = re.compile(r"^[0-9]+(\.[0-9]{1,8})?$")
    SYMBOL_PATTERN: Pattern = re.compile(r"^[A-Z0-9]{1,20}$")

    @staticmethod
    def validate_positive_price(value: float, field_name: str = "price") -> float:
        """Validate price is positive.

        Args:
            value: Price value to validate
            field_name: Name of field for error message

        Returns:
            Validated price

        Raises:
            ValueError: If price is negative or zero
        """
        if value is None:
            return value
        if value <= 0:
            raise ValueError(f"{field_name} must be positive, got {value}")
        if value > 1_000_000:
            raise ValueError(f"{field_name} exceeds maximum (1,000,000), got {value}")
        return value

    @staticmethod
    def validate_price_range(value: float, field_name: str = "price") -> float:
        """Validate price is within reasonable range."""
        if value is None:
            return value
        if value < 0.00001 or value > 999_999.99:
            raise ValueError(f"{field_name} out of acceptable range: {value}")
        return value

    @staticmethod
    def validate_quantity(value: float, field_name: str = "quantity") -> float:
        """Validate quantity is positive.

        Args:
            value: Quantity to validate
            field_name: Name of field

        Returns:
            Validated quantity

        Raises:
            ValueError: If quantity is non-positive or unreasonable
        """
        if value is None:
            return value
        if value <= 0:
            raise ValueError(f"{field_name} must be positive, got {value}")
        if value > 1_000_000:
            raise ValueError(f"{field_name} exceeds maximum, got {value}")
        return value

    @staticmethod
    def validate_r_multiple(value: float, field_name: str = "R multiple") -> float:
        """Validate R multiple (risk multiple in trading).

        Args:
            value: R multiple value
            field_name: Name of field

        Returns:
            Validated R multiple

        Raises:
            ValueError: If R multiple is unreasonable
        """
        if value is None:
            return value
        if value < -100 or value > 100:
            raise ValueError(f"{field_name} must be between -100 and 100, got {value}")
        return value

    @staticmethod
    def escape_html(value: str, field_name: str = "value") -> str:
        """Escape HTML to prevent XSS.

        Args:
            value: String to escape
            field_name: Name of field

        Returns:
            Escaped string safe for HTML output
        """
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be string, got {type(value)}")
        return html.escape(value, quote=True)

    @staticmethod
    def sanitize_text(value: str, max_length: int = 1000) -> str:
        """Sanitize text input by removing dangerous characters.

        Args:
            value: Text to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("Input must be string")
        if len(value) > max_length:
            raise ValueError(f"Input exceeds maximum length ({max_length})")

        # Remove control characters
        value = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")
        return value.strip()

    @staticmethod
    def validate_symbol(value: str) -> str:
        """Validate trading symbol format.

        Args:
            value: Symbol to validate (e.g., "EURUSD")

        Returns:
            Validated symbol

        Raises:
            ValueError: If symbol format invalid
        """
        if not value:
            raise ValueError("Symbol cannot be empty")
        if not SecurityValidators.SYMBOL_PATTERN.match(value):
            raise ValueError(f"Invalid symbol format: {value}")
        return value.upper()


def escape_html_output(html_content: str) -> str:
    """
    Escape HTML content for safe output.

    Note: For HTML templates, use Jinja2's auto-escaping instead.
    This is for when you need to manually escape string content.
    """
    return html.escape(html_content, quote=True)
