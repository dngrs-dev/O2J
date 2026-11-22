"""Extract the KIO appeal header and the first contested action."""

import re

from .parties import company, ids, lawyers
from .text import DATE, captured, flat, folded, iso_date

EMAIL = r'([A-Z0-9.!#$%&*+/=?^_~-]+@[A-Z0-9.-]+\.[A-Z]{2,})'
APPELLANT = r'odwo[łlt]uj[ąa]c(?:y|a|i|e)'
AUTHORITY = r'zamawiaj[ąa]c(?:y|a|i|e)'
APPEAL_TITLE = r'o[ \t]*d[ \t]*w[ \t]*o[ \t]*[łl][ \t]*a[ \t]*n[ \t]*i[ \t]*e'
PARTY_LABEL_SUFFIX = r'(?:[ \t]*\([^)]{1,220}\))?[ \t]*[:\-]'
PARTY_END = (rf'{APPELLANT}{PARTY_LABEL_SUFFIX}|{AUTHORITY}{PARTY_LABEL_SUFFIX}|{APPEAL_TITLE}\b|dotyczy\s*:|'
             r'prezes\w* krajowej izby|krajowa izba odwo[łl]awcza|dzia[łl]aj[ąa]c\b|'
             r'warto[śs][ćc] zam[oó]wienia|post[ęe]powanie\s*:')
REASONS = {
    1: 'Decyzja o odrzuceniu oferty',
    2: 'Ogłoszenie wyboru oferty',
    3: 'Decyzja o wykluczeniu wykonawcy',
    4: 'Publikacja specyfikacji warunków zamówienia (SWZ)',
    5: 'Modyfikacja treści SWZ',
    6: 'Odpowiedzi/wyjaśnienia do SWZ',
    7: 'Zaniechanie odrzucenia oferty',
    8: 'Zaniechanie wykluczenia wykonawcy',
    9: 'Decyzja o unieważnieniu postępowania',
    10: 'Zaniechanie unieważnienia postępowania',
    11: 'Opis przedmiotu zamówienia (OPZ)',
    12: 'Projektowane postanowienia umowy',
}

REASON_PATTERNS = {
    7: r'(?:zaniecha\w+|nie)\s+(?:\w+\s+){0,2}odrzuc\w*',
    8: r'(?:zaniecha\w+|nie)\s+(?:\w+\s+){0,2}wyklucz\w*',
    10: r'(?:zaniecha\w+|nie)\s+(?:\w+\s+){0,2}uniewazni\w*',
    1: r'odrzuc\w*(?:\s+\w+){0,5}\s+ofert\w*',
    2: r'(?:wybor\w*|wybral\w*|wybran\w*)[^;\n]{0,90}ofert\w*|najkorzystniejsz\w+\s+ofert\w*',
    3: r'wyklucz\w*',
    9: r'uniewazni\w*',
    6: r'(?:udziel\w*|opublik\w*|przekaz\w*).{0,100}(?:odpowiedz\w*|wyjasnie\w*)|'
       r'(?:odpowiedz\w*|wyjasnien\w*)\s+(?:na pytani\w*|(?:do (?:tresci )?)?swz)',
    5: r'(?:modyfik\w*|zmodyfik\w*|zmian\w*|zmien\w*).{0,85}(?:swz|specyfikac\w*)',
    11: r'(?:opis|opisu|opisie|opis\w*|okresl\w*)\s+(?:projektowan\w+\s+)?przedmiotu zamowienia|\bopz\b',
    4: (r'(?:publik\w*|opublik\w*|udostepni\w*|ustal\w*).{0,100}(?:swz|specyfikac\w*)|'
        r'\btresc\w*\s+(?:(?:dokument\w*\s+zamowienia)\s+.{0,5})?(?:swz|specyfikac\w*)'),
    12: r'projektowan\w+\s+postanowieni\w+\s+umowy|wzor\w*\s+umowy|projekt\w*\s+umowy',
}
FILING = rf"(?im)^(?:[*_.–-]+[ \t]*)?([A-ZĄĆĘŁŃÓŚŹŻ][^\n,.:\d]{{1,55}}?)(?:[ \t]*,[ \t]*|[ \t]+)(?:dnia[ \t]+)?({DATE})[^\n]{{0,13}}$"


def sections(text: str, label: str) -> list[str]:
    pattern = rf'(?im)^{label}{PARTY_LABEL_SUFFIX}[ \t]*\n?'
    output = []
    for start in re.finditer(pattern, text):
        block = re.split(rf'(?im)^(?:{PARTY_END})|{FILING.replace("(?im)", "")}', text[start.end():],
                         maxsplit=1)[0].strip()
        if block:
            output.append(block)
    return output


def party_name(text: str) -> str | None:
    lines = text.strip().splitlines()
    if not lines:
        return None
    first = re.sub(r'^(?:\d+[.)]\s*|[-–•_]\s*)', '', lines[0])
    if len(lines) > 1 and not re.match(
        r'(?:ul\.|al\.|pl\.|os\.|\d{2}-\d{3}|KRS|NIP|REGON|reprezentowan|adres|kontakt|e-?mail|siedziba)',
        lines[1], re.I
    ) and not re.search(r'\b(?:sp\.[^.]*[ojk]\.|S\.A\.|sp\.\s*z\s*o\.o\.)\s*$', first, re.I):
        if re.search(r'\b(?:sp\.|S\.A\.|Gospodarczej)\s*', lines[1], re.I) or re.search(
                r'\b(?:w|we|im\.|i|z|ograniczon[ąa])\s*$', first, re.I):
            first += ' ' + lines[1]
    return company(re.sub(r'\s*[\[(][^\])]*(?:lider|prowadz[ąa]c)[^\])]*[\])]\s*$', '', first, flags=re.I))


def appellant(block: str) -> dict | None:
    primary = re.split(r'(?im)^\s*(?:\d+[.)]\s*)?lider(?:\s+konsorcjum)?\s*:\s*', block, maxsplit=1)[-1]
    primary = re.split(r'(?im)^\s*(?:\d+[.)]\s*)?(?:partner|cz[łl]onek)(?:\s+konsorcjum)?\s*:', primary, maxsplit=1)[0]
    if re.match(r'(?i)konsorcjum\b', primary):
        members = re.split(r'(?im)(?:^|[:;])\s*[1-9][.)]\s*', primary, maxsplit=2)
        if len(members) >= 2:
            primary = members[1]
    name = party_name(primary)
    if not name:
        return None
    agent_block = re.split(r'(?i)\b(?:reprezentowan\w*\s+przez(?:\s+pe[łl]nomocnik\w*)?|'
                           r'pe[łl]nomocnik(?:\s+odwo[łl]uj[ąa]cego)?\s*:)\s*:?', block, maxsplit=1)
    agents = lawyers(agent_block[-1])
    office = captured(
        r'adres do (?:korespondencji|dor[ęe]cze[ńn])\s*:\s*(.+?)(?=[, \t]*\n[.\s©*_]*(?:\d[ \t]+[a-z]?[ \t]+)?(?:ul\.|al\.|pl\.|os\.)|'
        r',\s*(?:ul\.|al\.|pl\.|os\.|\d)|\n[^\n]{0,6}\b(?:tel\.|e-?mail)|\Z)',
        agent_block[-1], re.I | re.S,
    )
    if not office:
        office = captured(r'^([^\n]*\bkancelaria\b[^\n]+)', agent_block[-1])
    party_info = re.split(r'(?i)reprezentowan\w*\s+przez|adres do (?:korespondencji|dor[ęe]cze[ńn])', primary)[0]
    return {**ids(party_info), 'nazwa': name, 'przez-pelnomocnika': int(bool(agents or len(agent_block) > 1)),
            'pelnomocnik': {
                'imie_nazwisko': agents[0]['imie_nazwisko'] if agents else None,
                'nazwa': office,
                'mail': captured(EMAIL, agent_block[-1]) if agents or len(agent_block) > 1 else None,
            }}


def authorities(blocks: list[str]) -> list[dict]:
    output = []
    for block in blocks:
        # Explicitly numbered contracting authorities may share a single heading.
        pieces = re.split(r'(?im)^\s*(?:\d+[.)]\s*|(?:wsp[oó][łl])?zamawiaj[ąa]cy\s+\d+\s*:\s*)', block)
        for piece in filter(str.strip, pieces):
            if re.fullmatch(rf'[\s_–-]*{AUTHORITY}\s+wsp[oó]lnie\b[^:\n]*:\s*', piece, re.I):
                continue
            body = re.sub(rf'(?im)^{AUTHORITY}\b[ \t]*[-–—][^:\n]*:[ \t]*\n?', '', piece)
            if not (name := party_name(body)):
                continue
            lead = bool(re.search(r'(?i)prowadz[ąa]c\w+\s+post[ęe]powanie|lider(?:\s+post[ęe]powania|\s*[,:\n])', piece))
            output.append({**ids(piece), 'nazwa': name, 'prowadzacy_postepowanie': int(lead)})
    if len(output) == 1:
        output[0]['prowadzacy_postepowanie'] = None
    return output


def trailing_labels(header: str, text: str, appellant_blocks: list[str]) -> tuple[list[dict], list[dict]] | None:
    """Some two-column scans place both role labels after the party blocks."""
    if len(appellant_blocks) != 1 or not re.search(
            rf'(?im)^{AUTHORITY}\s*:\s*\n\s*dotyczy\s*:', header):
        return None
    declaration = captured(
        r'\bw imieniu\s+(?:wykonawcy|odwo[łl]uj[ąa]cego)\s+([^;]{4,200}?),\s*wnosz(?:[ęe]|imy)\b',
        flat(text[:9500]),
    )
    name = company(declaration.replace('” ', ' ').replace('„', '')) if declaration else None
    authority = party_name(appellant_blocks[0])
    if not name or not authority or folded(name) == folded(authority):
        return None
    represented = bool(re.search(r'\breprezentowan\w+\s+przez\b', header.split(appellant_blocks[0], 1)[0], re.I))
    return ([{**ids(''), 'nazwa': name, 'przez-pelnomocnika': int(represented),
              'pelnomocnik': dict.fromkeys(('imie_nazwisko', 'nazwa', 'mail'))}],
            authorities(appellant_blocks))


def reason(text: str) -> int | None:
    text = folded(flat(text))
    return next((key for key, pattern in REASON_PATTERNS.items() if re.search(pattern, text)), None)


def action(text: str) -> tuple[int | None, str | None]:
    intro = re.search(
        r'(?is)polegaj[ąa]c\w+\s+na\s*:\s*(?:1[.)]\s*)?(.+?)(?=;\s*(?:[2-9][.)]|zamawiaj)|'
        r'\n\s*[2-9][.)]\s|\n\s*zarzut\b|\Z)', text,
    )
    if not intro:
        intro = re.search(
            r'(?ims)\bwnosz\w+\s+(?:niniejsze\s+)?odwo[łl]anie\s+wobec\b.{0,600}?'
            r'(?:^|:)\s*1[.)]\s*(.+?)(?=^\s*[2-9][.,)]\s|^\s*zaskar[żz]onym|\Z)', text,
        )
    if not intro:
        intro = re.search(r'(?is)\bwnosz\w+\s+odwo[łl]anie\b.{0,700}?\btj\.\s*:\s*wobec\s+(.+?)'
                          r'(?=\n\s*odwo[łl]anie jest\b|\n\s*zarzut\b|\Z)', text)
    first = intro[1][:850] if intro else ''
    kind = reason(first)
    when = iso_date(first) if kind else None
    heading = re.search(r'(?im)^\s*(?:zarzut(?:\s+nr)?\s+1\b|pierwszy zarzut\b)', text)
    opening = text[:heading.start()] if heading else text[:10000]
    dated = re.finditer(rf'(?is)(?:zamawiaj[ąa]cy|o czym|informacj\w+\s+o)\s+(?:[^\n]{{0,50}}?\s+)?'
                         rf'(?:w\s+dniu|z\s+dnia|dnia)\s+({DATE})(.{{0,220}}?)(?=\.\s+(?-i:[A-ZĄĆĘŁŃÓŚŹŻ])|\n|$)',
                         opening)
    for match in dated:
        candidate = reason(match[2])
        if candidate and (kind is None or kind == candidate):
            return candidate, when or iso_date(match[1])
    if not kind and heading:
        first = re.split(r'(?im)^\s*zarzut(?:\s+nr)?\s+[2-9]\b', text[heading.start():], maxsplit=1)[0][:650]
        kind = reason(first)
        when = iso_date(first) if kind else None
    if kind and not when:
        deadline = captured(rf'\b(?:powzi[ąa][łl]\w* wiadomo[śs][ćc]|informacj\w+ o (?:wyborze|zaskar[żz]onej czynno[śs]ci))\b'
                            rf'[^;]{{0,220}}?({DATE})', flat(text[:11000]))
        when = iso_date(deadline)
    if kind == 4 and not when:
        published = captured(rf'\bzamawiaj[ąa]cy\s+(?:zamie[śs]ci[łl]|opublikowa[łl]|udost[ęe]pni[łl])\s+'
                             rf'(?:og[łl]oszenie|dokumenty|specyfikacj[ęe]|SWZ)[^;]{{0,110}}?\bw dniu\s+({DATE})',
                             flat(text[:11000]))
        when = iso_date(published)
    return kind, when


def procurement(text: str) -> dict:
    head = re.split(r'(?im)^dzia[łl]aj[ąa]c|^\s*wnosz[ęe]\b', text, maxsplit=1)[0]
    bzp = captured(r'\b(\d{4}\s*/\s*BZP\s*\d{8}(?:\s*/\s*\d{2})?)', head)
    ted = re.search(r'\b(\d{4})\s*/\s*S\s*\d{1,3}\s*[-–]\s*(\d{5,7})\b', head, re.I)
    ted_number = f'{ted[2]}-{ted[1]}' if ted else captured(
        r'\b(?:TED|Dzienniku Urzędowym(?: Unii Europejskiej| UE)?)\b.{0,55}?\b(\d{5,7}-\d{4})\b', flat(head)
    )
    reference = captured(r'\b(?:(?:nr\.?|numer|znak)\s+(?:referencyjn\w+(?:\s+sprawy)?|post[ęe]powania|'
                         r'sprawy|wewn[ęe]trzn\w+)|post[ęe]powanie\s+(?:nr\.?|numer))'
                         r'\s*[:–-]?\s*([A-Z0-9]+(?:(?:[._–-]|\s*/\s*)[A-Z0-9]+)*)',
                         flat(head))
    reference = re.sub(r'\s+', '', reference) if reference and any(c.isdigit() for c in reference) else None
    title = captured(r'(?:\bpn\.|\bpod\s+nazw[ąa]|tytu[łl](?:\s+zam[oó]wienia)?\s*:)\s*[„“"]([^”"\n]+)[”"]',
                     flat(head))
    if not title:
        title = captured(r'\bprzedmiotem\s+jest\s*[„“"]([^”"]{4,500})[”"]', flat(text))
    if not title:
        title = captured(r'(?:\bpn\.|tytu[łl] zam[oó]wienia\s*:)\s*(.+?)(?=,\s*(?:nr|numer|znak)|'
                         r'\s+(?:nr|numer)\s+referencyjn|$)', head)
    return {'numer_bzp': re.sub(r'\s', '', bzp).upper() if bzp else None,
            'numer_postepowania': reference, 'numer_ted': ted_number, 'tytul': title}


def appeal(text: str) -> dict:
    header = re.split(r'(?im)^dzia[łl]aj[ąa]c|^\s*zarzut\b', text, maxsplit=1)[0][:8000]
    filing = re.search(FILING, header)
    kind, when = action(text[:18000])
    city = filing[1].strip() if filing else None
    appellant_blocks = sections(header, APPELLANT)
    buyers = authorities(sections(header, AUTHORITY))
    challengers = [party for block in appellant_blocks if (party := appellant(block))]
    if not buyers and (corrected := trailing_labels(header, text, appellant_blocks)):
        challengers, buyers = corrected
    return {
        'OdwolanieKIO': {
            'data': iso_date(filing[2]) if filing else None,
            'czynnosc_dzien': when,
            'czynnosc_powod_id': kind,
            'czynnosc_opis': REASONS.get(kind),
            'miejscowosc': city[0].upper() + city[1:] if city else None,
        },
        'Odwolujacy': challengers,
        'Zamawiajacy': buyers,
        'ZamowieniePubliczne': procurement(text[:18000]),
    }
