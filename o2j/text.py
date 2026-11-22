"""Common text and Polish date handling for local extractors."""

from datetime import date
import re
import unicodedata


def clean(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).replace('\u00ad', '').replace('\x00', '')
    text = re.sub(r'\r+\n|\r', '\n', text)
    text = re.sub(r'(?m)^\s*(?:Strona\s+\d+\s+z\s+\d+|\d+\s*/\s*\d+)\s*$', '', text)
    return '\n'.join(line.strip() for line in text.splitlines() if line.strip())


def flat(text: str) -> str:
    return ' '.join(text.split())


def folded(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold().replace('ł', 'l'))
                   if not unicodedata.combining(c))


MONTHS = ('stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia',
          'września', 'października', 'listopada', 'grudnia')
DATE = (r'(?<!\d)(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{1,2} \d{1,2} \d{4}|'
        r'\d{1,2}\s+(?:' + '|'.join(MONTHS + ('wrzesnia', 'pazdziernika')) + r')\s+\d{4})(?!\d)')


def clean_ocr(text: str) -> str:
    text = clean(text)
    text = re.sub(r'(?im)^[ \t]*[.‘’…„“”"©*•_~;|]+[ \t]*(?=[^\W\d_])', '', text)
    text = re.sub(r'(?i)(\bsp\.\s+)[zZ]\s+[o0]\.\s*[o0]\.', r'\1z o.o.', text)
    text = re.sub(
        r'(?im)(\be-?mail\s*:[ \t]*)((?:[a-z][ .])?[a-z0-9._+-]+)[Q@]([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b',
        lambda m: m[1] + m[2].replace(' ', '.') + '@' + m[3], text,
    )
    return text


def iso_date(text: str | None) -> str | None:
    match = re.search(DATE, text or '', re.I)
    if not match:
        return None
    parts = re.split(r'[\s.\-/]+', match[0].lower())
    try:
        if len(parts[0]) == 4:
            year, month, day = map(int, parts)
        else:
            day, year = int(parts[0]), int(parts[2])
            month = int(parts[1]) if parts[1].isdigit() else tuple(map(folded, MONTHS)).index(folded(parts[1])) + 1
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def captured(pattern: str, text: str, flags: int = re.I | re.M) -> str | None:
    match = re.search(pattern, text, flags)
    return flat(match[1]).strip(' ,;:') if match else None
