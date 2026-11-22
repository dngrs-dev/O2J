"""Extract Polish bank transfer details from labelled fields."""

import re

from .text import DATE, captured, flat, iso_date

ACCOUNT = r'(?<!\d)(?:PL[ \t]*)?(\d{2}(?:[\s.-]*\d{4}){6})(?!\d)'
SOURCE = (r'(?:rachune[kx]|konto|nr rachunku)\s+(?:obci[ąa][żz]an[ey]|nadawcy|p[łl]atnika|[zsc]leceniodawcy|'
          r'zleceniodawca)|z\s+rachunku')
DESTINATION = r'(?:rachunek|konto|nr rachunku)\s+(?:uznawany|odbiorcy|beneficjenta|adresata|kontrahenta)|na\s+rachunek'
AMOUNT = r'(?:kwota|warto[śs][ćc])(?:\s+(?:operacji|przelewu|transakcji|obci[ąa][żz]enia))?'
DATE_LABELS = (r'(?:zlecona\s+)?da[tl]a\s+(?:operacji|realizacji|wykonania|transakcji|przelewu)',
               r'data\s+(?:ksi[ęe]gowania|waluty|rozliczenia)', r'data\s+(?:zlecenia|z[łl]o[żz]enia)')
REFERENCE = (r'(?:identyfikator|numer|nr\.?)\s*(?:referencyjny|ref\.?|transakcji|operacji|dokumentu)(?:\s+(?:operacji|transakcji))?'
             r'|identyfikator\s+(?:bankowy|zlecenia)')
TITLE = r'tytu[łl](?:em|\s+(?:przelewu|p[łl]atno[śs]ci|operacji))?|szczeg[oó][łl]y p[łl]atno[śs]ci'
END = '|'.join((SOURCE, DESTINATION, AMOUNT, *DATE_LABELS, REFERENCE,
                r'status\b|waluta\b|data (?:wydruku|wygenerowania|wystawienia)\b|op[łl]ata\s*(?:[:/]|\d)|prowizja\b',
                r'zrealizowano\b|potwierdzenie (?:ma|zosta[łl]o)\b|dokument (?:zosta[łl]|wygenerowano|jest|podpisa|elektroniczny)\w*',
                r'w razie pyta[ńn]\b|bank nie ponosi\b|wygenerowano\b|strona \d|typ (?:operacji|przelewu|transakcji)\b|tryb\b|kana[łl]\b',
                r'(?:dane\s+)?(?:odbiorca|nadawca)\b|p[łl]atnik\b|beneficjent\b|adresat przelewu\b|z powa[żz]aniem',
                r's[i:]gnature\b|numer\s+\d+\s*\ntransakcji\b'))
FIELD_SEPARATOR = r'(?:[ \t]*[:|>–-][ \t]*|[ \t]+|\n)[ \t|>:.–-]*'
DECIMAL = r'((?:[+-]\s*)?\d(?:[\d .]*\d)?[,\.]\d{2})'
MONEY = re.compile(r'(?P<whole>\d+|\d{1,3}(?P<group>[ .,])\d{3}(?:(?P=group)\d{3})*)'
                   r'(?P<fraction>[,.]\d{1,2})?')


def field(text: str, label: str, value: str) -> str | None:
    return captured(rf'^(?:{label}){FIELD_SEPARATOR}\s*{value}', text)


def account(text: str, label: str, section: str) -> str | None:
    value = field(text, label, ACCOUNT)
    if not value:
        value = captured(rf'\b(?:{label})[\s:|>.-]*(?:nr\.?\s*)?{ACCOUNT}', text)
    if not value:
        block = re.search(rf'^(?:{section})\b', text, re.I | re.M)
        if block:
            lines = text[block.start():].splitlines()[:5]
            for i, line in enumerate(lines):
                if i and re.match(rf'(?:{END}|dane\s+(?:nadawcy|odbiorcy|zleceniodawcy|kontrahenta))', line, re.I):
                    lines = lines[:i]
                    break
            value = captured(ACCOUNT, '\n'.join(lines))
    return re.sub(r'\D', '', value) if value else None


def amount(text: str) -> float | None:
    number = r'(?:PLN\s+|zł\s+)?((?:[+-]\s*)?\d(?:[\d .,]*\d)?)'
    value = (field(text, AMOUNT, number)
             or captured(rf'\b(?:w\s+)?kwocie\s+{number}', text)
             or captured(rf'^(?:[^\n]*?\s)?{DECIMAL}\s*(?:PLN|z[łl])\b', text))
    if not value:
        return None
    match = MONEY.fullmatch(value.lstrip('+- '))
    if not match:
        # OCR can turn a decimal comma into a space. Invalid groups are ambiguous.
        return None
    whole = re.sub(r'[ .,]', '', match['whole'])
    fraction = (match['fraction'] or '').replace(',', '.')
    return float(whole + fraction)


def transfer_title(text: str) -> str | None:
    for label in (TITLE, r'opis(?:\s+(?:transakcji|operacji))?(?![ \t]+kwota\b)'):
        title = re.search(rf'^(?:{label}){FIELD_SEPARATOR}[ \t]*\n?[ \t]*(?!{END})'
                          rf'([\s\S]+?)(?=^(?:{END})|\Z)', text, re.I | re.M)
        if title:
            lines = [line.rstrip(' *|~') for line in title[1].splitlines() if re.search(r'\w', line)]
            value = flat('\n'.join(lines)).lstrip('„“"_: ')
            if title[1].lstrip()[:1] in ('„', '“', '"'):
                value = re.sub(r'[”"]\.?$', '', value)
            return value or None
    return None


def transfer(text: str) -> dict:
    text = re.sub(r'(?m)^[\t ._–—-]{4,}$\n?', '', text)
    text = re.sub(r'[ .·]{4,}', ' ', text)
    ref_value = r'([A-Z0-9][A-Z0-9./_-]*[A-Z0-9])'
    table = re.search(rf'(?im)^kwota\s+data\s+transakcji[^\n]*\n[^\n]*?({DATE})[ \t|*"]+{ref_value}', text)
    dates = (iso_date(field(text, label, rf'({DATE})')) for label in DATE_LABELS)
    prose_date = captured(rf'\b(?:bank\s+)?potwierdza[,\s]+(?:że\s+)?w\s+dniu\s+({DATE})', text)
    stacked_date = captured(rf'^data[ \t|:]+({DATE})\s*\nwykonania\b', text)
    elixir_date = captured(rf'^data\s+operacji[^\n]{{1,130}}\n({DATE})\b', text)
    when = (next((value for value in dates if value), None)
            or iso_date(table[1] if table else prose_date or stacked_date or elixir_date))
    ref = (field(text, REFERENCE, ref_value)
           or captured(r'^\W{0,5}numer[ \t|:]+(\d{3,})\s*\ntransakcji\b', text)
           or (table[2] if table else None))
    source = account(text, SOURCE, r'(?:dane\s+)?(?:nadawc(?:a|y)|p[łl]atnik|zleceniodawc(?:a|y))')
    if not source and re.search(r'\bprzelew z rachunku\b', text, re.I):
        source = account(text, r'(?:numer|nr) rachunku', r'w[łl]a[śs]ciciel')
    return {'przelew_bankowy': {
        'data_operacji': when,
        'kwota': amount(text),
        'na_rachunek': account(text, DESTINATION, r'(?:dane\s+)?(?:odbiorc(?:a|y)|kontrahent(?:a)?|beneficjent|adresat przelewu)'),
        'numer_transakcji': ref,
        'tytul': transfer_title(text),
        'z_rachunku': source,
    }}
