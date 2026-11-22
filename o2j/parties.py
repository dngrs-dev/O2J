"""Identify people and registration numbers using the document's roles."""

import re

from .text import captured, flat

WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:[-’'][A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)*"
PERSON = rf'{WORD}(?:\s+{WORD}){{1,3}}'
PERSON_LINE = rf'{WORD}(?:[ \t]+{WORD}){{1,3}}'
TITLE = r'adw(?:okat(?:a|ka)?)?\.|adwokat(?:a|ka)?|r\.?\s*pr\.|radc(?:a|ę|y)\s+prawn(?:y|ego|ą)|mec\.'
ROLE = r'(?:wiceprezes|prezes|cz[łl]onek|prokurent|dyrektor|w[łl]a[śs]ciciel|wsp[oó]lnik)(?:\w*)'
SIGNATURE = r'(?:[.…_]{5,}|/{2,}|podpis\s*:|\(podpis\))'


def identifier(text: str, label: str, lengths: tuple[int, ...]) -> str | None:
    number = captured(rf'\b(?:{label})\b(?:[ \t:().-]|(?:nr|numer)\b|\n){{0,20}}(\d(?:[ \t-]?\d){{{min(lengths)-1},{max(lengths)-1}}})(?![ \t-]?\d)', text)
    digits = re.sub(r'\D', '', number or '')
    return digits if len(digits) in lengths else None


def ids(text: str) -> dict:
    return {'krs': identifier(text, 'KRS', (10,)), 'nip': identifier(text, 'NIP', (10,)),
            'regon': identifier(text, 'REGON', (9, 14))}


def lawyers(text: str) -> list[dict]:
    start = re.compile(rf'(?i:{TITLE})\s*(?P<name>{PERSON})(?=$|[\s,;:(.])', re.M)
    matches = list(start.finditer(text))
    result = {}
    for i, match in enumerate(matches):
        name = flat(match['name'])
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), match.end() + 100)
        pesel = identifier(text[match.end():end].split('\n\n', 1)[0], 'PESEL', (11,))
        if name not in result or pesel:
            result[name] = {'imie_nazwisko': name, 'pesel': pesel}
    return list(result.values())


def company(text: str) -> str | None:
    value = re.split(r',?\s+(?:ul\.|al\.|os\.|pl\.|z\s+siedzib[ąa]|zamieszka[łl]\w*|'
                     r'\(dalej\b|\(KRS\b|\(NIP\b|(?:KRS|NIP|REGON)\b|(?:reprezentowan\w*|wpisan\w*|'
                     r'prowadz[ąa]c\w*\s+dzia[łl]alno[śs][ćc])\b)|\s*[,;]\s*\d{2}-\d{3}',
                     flat(text), maxsplit=1, flags=re.I)[0]
    value = value.strip(' ,;:„”"')
    return value or None


def signatories(text: str) -> list[dict]:
    text = re.split(r'(?im)^\s*(?:Pe[łl]nomocnictwo przyjmuj\w*|podpis pe[łl]nomocnika)\s*:', text)[0]
    found = re.findall(
        rf'(?m)^[ \t]*(?P<name>{PERSON_LINE})[ \t]*'
        rf'(?:[—–,-][ \t]*|\n[ \t]*)(?i:{ROLE})(?=\s|$)', text
    )
    next_line = rf'(?m)^\s*{SIGNATURE}[ \t]*\n(?:[ \t]*(?:Za|W imieniu)\b[^\n]*\n)?[ \t]*([^\n]+)'
    for name in re.findall(next_line, text, flags=re.I):
        if re.fullmatch(PERSON, name.strip()):
            found.append(name)
    found.extend(re.findall(rf'(?m)^(?i:dokument podpisany przez)[ \t]+({PERSON_LINE})', text))
    combined = rf'(?i:zarz[ąa]du|prokurent|dyrektor)[ \t]+({PERSON_LINE})[ \t]*[–—-][ \t]*(?i:{ROLE})\b'
    found.extend(re.findall(combined, text))
    # Recover reading order when a signer was matched by both formats.
    return [{'imie_nazwisko': name} for name in sorted({flat(n) for n in found}, key=text.find)]


def representatives(text: str) -> list[dict]:
    opening = re.split(r'(?i)\breprezentowan\w+\s*[_–—-]?\s*przez\s*:\s*', text, maxsplit=1)
    if len(opening) == 1:
        return []
    region = re.sub(r'(?<=\w)[ \t]+\.[ \t]*\n(?=[A-ZĄĆĘŁŃÓŚŹŻ])', ' ', opening[1])
    name_and_role = rf'(?:^|[,;]\s*)({PERSON})\s*[–—-]\s*(?i:{ROLE})\b'
    return [{'imie_nazwisko': flat(name)} for name in re.findall(name_and_role, region)]
