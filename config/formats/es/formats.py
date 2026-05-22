"""Number formatting overrides for Spanish locales.

es-MX uses a period as the decimal separator (not the comma Django's bundled
`es` formats default to). Date/time formats fall back to Django's locale data.
"""

DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ""
NUMBER_GROUPING = 0
