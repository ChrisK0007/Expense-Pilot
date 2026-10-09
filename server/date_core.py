"""Australian manual date input, normalised without guessing missing components."""
import re
from datetime import date


def normalise_date(value):
    text = str(value or '').strip()
    if re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}', text):
        year, month, day = map(int, text.split('-'))
    else:
        if re.fullmatch(r'\d{6}|\d{8}', text):
            parts = (text[:2], text[2:4], text[4:])
        else:
            match = re.fullmatch(r'(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})', text)
            if not match:
                raise ValueError('Enter a valid date, for example 8/10/2026 or 081026.')
            parts = match.groups()
        day, month, year = map(int, parts)
        if len(parts[2]) == 2:
            year += 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        raise ValueError('Enter a real calendar date as DD/MM/YYYY.') from None
