"""Create original, labelled scan cases for OCR experiments.

The references are specified from the authored case data and never read from
extractor output. Development and holdout use distinct layouts and case names.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont


@dataclass(frozen=True)
class Case:
    city: str
    supplier: str
    buyer: str
    counsel: str
    signer: str
    subject: str


DEVELOPMENT = (
    Case('Kalisz', 'Srebrny Szlak S.A.', 'Gmina Brzeziny Dolne', 'Ewa Dawid', 'Witold Kuchta',
         'Modernizacja oświetlenia ulicznego'),
    Case('Szczecin', 'Śnieżny Klon sp. z o.o.', 'Ośrodek Sportu w Szelinach', 'Paweł Rudy', 'Marta Polańska',
         'Utrzymanie nawierzchni boisk miejskich'),
    Case('Łomża', 'Róża Przemysłowa S.A.', 'Gmina Borki Jasne', 'Igor Madej', 'Weronika Wrona',
         'Przegląd urządzeń przeciwpożarowych'),
    Case('Gdańsk', 'Błękitny Żwir sp. z o.o.', 'Szpital Miejski w Sędowie', 'Olga Kot', 'Adam Lesiak',
         'Dostawa wyposażenia do pracowni technicznej'),
)
HOLDOUT = (
    Case('Toruń', 'Złota Kora sp. z o.o.', 'Gmina Zalesie Północne', 'Alicja Mucha', 'Iwona Czajka',
         'Budowa odwodnienia dla ulicy Bukowej'),
    Case('Olsztyn', 'Szafirowy Węzeł S.A.', 'Centrum Kultury w Stawsku', 'Robert Janik', 'Edyta Bąk',
         'Dostawa aparatury nagłośnieniowej'),
    Case('Przemyśl', 'Zielony Wrzos sp. z o.o.', 'Gmina Łęg Wielki', 'Zofia Łoś', 'Joanna Chmiel',
         'Serwis urządzeń wodociągowych'),
    Case('Bielsko-Biała', 'Jasna Nić S.A.', 'Zakład Gospodarki w Milawie', 'Kamil Duda', 'Rafał Szewc',
         'Utrzymanie skwerów i pasa zieleni'),
    Case('Płock', 'Biała Wstęga sp. z o.o.', 'Gmina Różany Brzeg', 'Maja Leśna', 'Dorota Witek',
         'Remont dachu budynku biblioteki'),
    Case('Leszno', 'Zorza Warsztatowa S.A.', 'Gmina Ustronie Małe', 'Jakub Kania', 'Karol Czuba',
         'Przegląd instalacji wentylacji mechanicznej'),
)

PROFILES = {
    'development': ('clean', 'upside-down', 'faint', 'skew'),
    'holdout': ('faint', 'shadow', 'upside-down', 'clean', 'speckle', 'skew'),
}
SIZE = (1240, 1754)


def number(case: int, category: int) -> str:
    return f'90{case:03d}{category:02d}123'


def account(case: int, category: int) -> str:
    body = f'9020{case:04d}{category:04d}123456789012'
    checksum = 98 - int(body + '252100') % 97
    return f'{checksum:02d}{body}'


def spaced(value: str) -> str:
    return ' '.join([value[:2], *(value[i:i + 4] for i in range(2, 26, 4))])


def identifiers(name, krs=None, nip=None):
    return {'nazwa': name, 'krs': krs, 'nip': nip, 'regon': None}


def templates(case: Case, key: int, holdout: bool):
    krs, nip, buyer_nip = (number(key, category) for category in (1, 2, 3))
    reference = f'ZP/{key:02d}/2026'
    filing = 12 + key % 8
    action = filing - 3
    contact = f'kio{key}@kancelaria.example'
    bzp = f'2026/BZP{730000 + key:08d}'
    attorney = {'imie_nazwisko': case.counsel, 'nazwa': 'Kancelaria Rzeczna', 'mail': contact}
    appeal_ref = {
        'OdwolanieKIO': {'miejscowosc': case.city, 'data': f'2026-03-{filing:02d}',
                         'czynnosc_dzien': f'2026-03-{action:02d}', 'czynnosc_powod_id': 5,
                         'czynnosc_opis': 'Modyfikacja treści SWZ'},
        'Odwolujacy': [{**identifiers(case.supplier, krs, nip), 'przez-pelnomocnika': 1,
                       'pelnomocnik': attorney}],
        'Zamawiajacy': [{**identifiers(case.buyer, nip=buyer_nip), 'prowadzacy_postepowanie': None}],
        'ZamowieniePubliczne': {'numer_bzp': bzp, 'numer_ted': None, 'numer_postepowania': reference,
                               'tytul': case.subject},
    }
    date = f'{case.city}, dnia {filing} marca 2026 r.'
    delivery = [f'Odwołujący: {case.supplier}', f'KRS {krs}, NIP {nip}',
                f'reprezentowany przez: adw. {case.counsel}',
                'adres do korespondencji: Kancelaria Rzeczna, ul. Lawendowa 3', f'E-mail: {contact}']
    recipient = [f'Zamawiający: {case.buyer}', f'NIP {buyer_nip}']
    order = [f'Postępowanie pn. „{case.subject}”',
             f'Numer referencyjny: {reference}', f'Ogłoszenie w BZP: {bzp}']
    if holdout:
        appeal = [date, 'Prezes Krajowej Izby Odwoławczej', '', 'ODWOŁANIE', '', *recipient, '',
                  *delivery, '', *order,
                  '', 'Wnoszę odwołanie wobec czynności polegających na:',
                  f'1) modyfikacji treści SWZ w dniu {action} marca 2026 r.',
                  '2) zaniechaniu przedłużenia terminu składania ofert.']
    else:
        appeal = [date, '', *delivery, '', *recipient, '', 'ODWOŁANIE', '',
                  *order, '', f'Zamawiający w dniu {action} marca 2026 r. zmodyfikował treść SWZ.',
                  'Zarzut nr 1 dotyczy nieprawidłowej zmiany warunków.']

    power_ref = {
        'mocodawca': [{
            'data': {'imie_nazwisko': None, 'krs': krs, 'nip': nip, 'nazwa': case.supplier, 'typ': 'osoba_prawna'},
            'podpisujacy': [{'imie_nazwisko': case.signer}],
        }],
        'pelnomocnicy': [{'imie_nazwisko': case.counsel, 'pesel': None}],
    }
    if holdout:
        power = [date, '', 'PEŁNOMOCNICTWO PROCESOWE', '',
                 f'{case.supplier} z siedzibą w {case.city} (KRS {krs}, NIP {nip})',
                 f'reprezentowana przez: {case.signer} — Prezes Zarządu,',
                 'udziela pełnomocnictwa:', f'1. {case.counsel} — adwokat',
                 f'do reprezentowania w sprawie {reference} przed KIO.',
                 '', '', 'Podpisano elektronicznie',
                 f'Dokument podpisany przez {case.signer}']
    else:
        power = ['PEŁNOMOCNICTWO', date, '', 'Mocodawca:', case.supplier, f'KRS {krs}', f'NIP {nip}',
                 '', 'Pełnomocnik:', f'adw. {case.counsel}', '',
                 f'Zakres pełnomocnictwa obejmuje zastępstwo procesowe w sprawie {reference}.', '',
                 '..............................', case.signer, 'Prezes Zarządu']

    source, target = account(key, 1), account(key, 2)
    amount = 1400 + key * 3
    transfer_id = f'ER{2026000 + key}'
    title = f'Wpis od odwołania w postępowaniu {reference}'
    when = f'2026-03-{filing - 1:02d}'
    transfer_ref = {'przelew_bankowy': {'data_operacji': when, 'kwota': amount + 0.25,
                                        'na_rachunek': target, 'numer_transakcji': transfer_id,
                                        'tytul': title, 'z_rachunku': source}}
    if holdout:
        grouped_amount = f'{amount:,d}'.replace(',', ' ')
        transfer = ['Bank Próbny', '', 'POTWIERDZENIE TRANSAKCJI', '',
                    f'Tytułem: {title}', f'Data księgowania: {when}',
                    f'Identyfikator operacji: {transfer_id}', '', 'Dane nadawcy',
                    f'Rachunek płatnika: {spaced(source)}', '', 'Dane odbiorcy',
                    f'Rachunek beneficjenta: {spaced(target)}', '',
                    'Kwota operacji:', f'{grouped_amount},25 PLN', '',
                    'Status: Wykonany']
    else:
        transfer = ['POTWIERDZENIE WYKONANIA PRZELEWU', '', f'Rachunek zleceniodawcy: PL{source}',
                    f'Rachunek odbiorcy: {spaced(target)}', f'Kwota przelewu: {amount},25 PLN',
                    f'Data realizacji: {when}', f'Numer referencyjny: {transfer_id}', '',
                    f'Tytuł przelewu: {title}', 'Status: Wykonany']

    negative = ([date, '', 'ZGŁOSZENIE PRZYSTĄPIENIA', '', 'Prezes Krajowej Izby Odwoławczej',
                 f'W sprawie {reference} wykonawca zgłasza przystąpienie po stronie zamawiającego.',
                 'Poniżej wskazano adres do doręczeń i osoby reprezentujące wykonawcę.']
                if holdout else
                [date, '', 'WYROK', '', 'Krajowa Izba Odwoławcza oddala odwołanie.',
                 f'Sprawa dotyczy postępowania {reference}', 'Stronom doręcza się odpis uzasadnienia.'])
    return ((appeal, appeal_ref), (power, power_ref), (transfer, transfer_ref), (negative, {}))


def page_image(lines, profile, font_path, seed):
    faint = profile in {'faint', 'shadow'}
    paper, ink = (224, 121) if faint else (250, 24)
    image = Image.new('L', SIZE, paper)
    draw = ImageDraw.Draw(image)
    body = ImageFont.truetype(font_path, 28)
    heading = ImageFont.truetype(font_path, 36)
    y = 150
    for line in lines:
        if not line:
            y += 30
            continue
        font = heading if line.isupper() and len(line) < 45 else body
        for wrapped in textwrap.wrap(line, width=65, break_long_words=False):
            draw.text((112, y), wrapped, font=font, fill=ink)
            y += 46
    if profile == 'upside-down':
        return image.rotate(180)
    if profile == 'skew':
        return image.rotate(4, resample=Image.Resampling.BICUBIC, fillcolor=paper)
    if profile == 'shadow':
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 62, SIZE[1]), fill=105)
        draw.rectangle((SIZE[0] - 47, 0, SIZE[0], SIZE[1]), fill=148)
        image = image.filter(ImageFilter.GaussianBlur(0.72))
    if profile == 'speckle':
        randomizer = random.Random(seed)
        for _ in range(5200):
            draw.point((randomizer.randrange(SIZE[0]), randomizer.randrange(SIZE[1])),
                       fill=randomizer.randint(75, 175))
    return image


def generate(output: Path, font: str):
    for split, cases in (('development', DEVELOPMENT), ('holdout', HOLDOUT)):
        root = output / split
        hashes = {}
        profiles = PROFILES[split]
        for index, case in enumerate(cases):
            key = index + (21 if split == 'holdout' else 1)
            directory = root / 'skany' / f'case-{key:02d}'
            directory.mkdir(parents=True, exist_ok=True)
            for doc, (lines, reference) in enumerate(templates(case, key, split == 'holdout')):
                profile = profiles[(index + doc) % len(profiles)]
                filename = directory / f'scan-{doc + 1:02d}'
                pdf = filename.with_suffix('.pdf')
                page_image(lines, profile, font, key * 10 + doc).convert('RGB').save(
                    pdf, 'PDF', resolution=150, quality=88, creationDate=946684800, modDate=946684800,
                )
                target = filename.with_suffix('.json')
                target.write_text(json.dumps(reference, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                for path in (pdf, target):
                    hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / 'manifest.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--font', required=True, help='ścieżka do fontu TrueType z polskimi znakami')
    arguments = parser.parse_args()
    generate(arguments.output, arguments.font)
