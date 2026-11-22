"""Extract principals, attorneys and signatures from powers of attorney."""

import re

from .parties import PERSON, TITLE, company, identifier, lawyers, representatives, signatories
from .text import captured, flat, folded, iso_date

HEADING = r'p\s*e\s*[łl]\s*n\s*o\s*m\s*o\s*c\s*n\s*i\s*c\s*t\s*w\s*o(?:[ \t]+(?:procesowe|szczeg[oó]lne|og[oó]lne))?'
GRANT_VERB = (r'(?:udziel\w*\s+(?:(?:niniejszego|niniejszym)\s+)?pe[łl]nomocnictwa|'
              r'ustanawi\w*\s+pe[łl]nomocnikiem|upowa[żz]nia(?:m|my)?(?:\s+niniejszym)?)')
GRANT = rf'(?:{GRANT_VERB}|pe[łl]nomocni(?:k|cy)\s*:?)'


def principals(text: str) -> list[dict]:
    parts = re.split(rf'(?im)^{HEADING}[ \t]*$', text, maxsplit=1)
    after_heading = parts[-1].strip()
    opening = re.split(rf'(?i)\b(?:{GRANT}|do reprezentowania)\b', after_heading, maxsplit=1)[0]
    consortium = re.search(r'(?is)konsorcjum\)?\s*:\s*1[.)]\s*(.+?)(?=\(dalej|$)', opening)
    person = captured(rf'(?i:ni[żz]ej podpisan(?:y|a)(?:/a)?)\s+({PERSON})(?=\s*[,;(])', opening, re.M)
    if consortium:
        sections = re.split(r'\s*;\s*\d+[.)]\s*|\n\s*\d+[.)]\s*', consortium[1])
    elif person:
        sections = [opening]
    else:
        block = opening
        if len(parts) == 2 and not identifier(opening, 'KRS|NIP', (10,)):
            block = parts[0] + '\n' + opening
        explicit = re.search(r'(?im)^mocodawc[ąa] jest[ \t]+', block)
        if not explicit:
            explicit = re.search(r'(?im)^(?:§\s*\d+\.[ \t]*)?mocodawca(?:[ \t]*[:–-][ \t]*|[ \t]+|\n)', block)
        if explicit:
            block = block[explicit.end():]
        sections = [block]
    output = []
    for section in sections:
        if person:
            name = company(captured(r'\b(?:pod firm[ąa]|pod nazw[ąa])\s+[„"]?(.+?)(?=[„”"]|,\s*(?:ul\.|al\.|NIP\b)|$)',
                                    flat(section)) or '')
        else:
            labelled = captured(r'(?:dzia[łl]aj\w+\s+w\s+imieniu|do reprezentacji|reprezentuj[ąa]c)\s+(.+)',
                                flat(section))
            if labelled:
                name = company(labelled)
            else:
                lines = [line.strip() for line in section.splitlines() if line.strip()]
                while lines and (iso_date(lines[0]) or re.match(r'^(?:§|mocodawca\b|pe[łl]nomocnictwo\b)', lines[0], re.I)):
                    lines.pop(0)
                opening_name = '\n'.join(lines[:3])
                name = company(opening_name)
                if name and not any(char.isalpha() for char in name):
                    name = None
        krs = identifier(section, 'KRS', (10,))
        nip = identifier(section, 'NIP', (10,))
        legal = krs or (name and re.search(r'\b(?:sp\.?|s\.a\.?|fundacja|stowarzyszenie|gmina)\b', name, re.I))
        if not (name or person or krs or nip):
            continue
        output.append({
            'data': {'imie_nazwisko': person, 'krs': krs, 'nazwa': name, 'nip': nip,
                     'typ': 'osoba_fizyczna' if person else 'osoba_prawna' if legal else None},
            'podpisujacy': representatives(section),
        })
    return output


def merge_signatures(declared: list[dict], actual: list[dict]) -> list[dict]:
    written = {folded(row['imie_nazwisko']): row for row in actual}
    ordered = {folded(row['imie_nazwisko']): row for row in declared}
    return list((ordered | written).values())


def attorneys(text: str) -> list[dict]:
    opening = re.split(
        r'(?im)^(?:§\s*\d+\.\s*)?(?:zakres|post[ęe]powanie|pe[łl]nomocnictwo (?:udzielone|obejmuje|dotyczy))\b',
        text, maxsplit=1,
    )[0]
    grant = re.search(rf'(?i)\b{GRANT_VERB}\b[ \t:]*', opening)
    region = opening[grant.end():] if grant else opening
    region = re.split(r'(?i)\bdo\s+(?:reprezentowania|zast[ęe]powania|wyst[ęe]powania)\b', region, maxsplit=1)[0]
    candidates = lawyers(region)
    if not grant:
        return candidates
    people = list(re.finditer(
        rf'(?m)(?:^|[,;]|\b(?:oraz|i)\b)\s*(?:[/|][ \t]*)?(?:\d+[.)][ \t]*)?({PERSON})'
        rf'(?=[ \t]*(?:\(|[–—-]\s*(?i:{TITLE})|,?\s*PESEL\b|\n|$))',
        region,
    ))
    proposed = {row['imie_nazwisko']: row['pesel'] for row in candidates}
    for i, match in enumerate(people):
        name = flat(match[1])
        if name not in proposed:
            end = people[i + 1].start() if i + 1 < len(people) else len(region)
            details = re.split(r'[);]+', region[match.end():min(end, match.end() + 160)], maxsplit=1)[0]
            proposed[name] = identifier(details, 'PESEL', (11,))
    if not proposed:
        roster = re.search(rf'(?ims)^pe[łl]nomocni(?:k|cy)[ \t:]*\n(.+?)(?=^{HEADING}[ \t]*$|\Z)', opening[:grant.start()])
        return lawyers(roster[1]) if roster else []
    return [{'imie_nazwisko': name, 'pesel': proposed[name]} for name in sorted(proposed, key=flat(region).find)]


def power(text: str) -> dict:
    parties = principals(text)
    accepting = re.split(r'(?im)^\s*pe[łl]nomocnictwo przyjmuj\w*\s*:', text)[0]
    signatures = list(re.finditer(r'(?im)^(?:w imieniu|za)\s+([^\n]+?)\s*:?\s*$', accepting))
    if len(parties) == 1:
        parties[0]['podpisujacy'] = merge_signatures(parties[0]['podpisujacy'], signatories(accepting))
    elif signatures:
        for i, section in enumerate(signatures):
            end = signatures[i + 1].start() if i + 1 < len(signatures) else len(accepting)
            for party in parties:
                name = party['data']['nazwa']
                if name and folded(flat(section[1])).rstrip('.:') == folded(name).rstrip('.:'):
                    party['podpisujacy'] = merge_signatures(party['podpisujacy'], signatories(accepting[section.end():end]))
                    break
    return {'mocodawca': parties, 'pelnomocnicy': attorneys(text)}
