import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw, ImageFont

from o2j.__main__ import main
from o2j.config import load_classes
from o2j.model import ModelError
from o2j.pdf import Document, Page, PdfReader
from o2j.pipeline import Pipeline
from o2j.text import clean, clean_ocr


TRANSFER = """POTWIERDZENIE WYKONANIA PRZELEWU
Rachunek zleceniodawcy: PL02 9081 0000 0001 0002 0003 0004
Rachunek odbiorcy: 13 9081 0000 0001 0002 0003 0005
Kwota przelewu: 1 735,50 PLN
Data wydruku: 12.07.2026
Data realizacji: 10.07.2026
Tytuł przelewu: Wpis od odwołania ABC/2/2026
Numer referencyjny: XYZ-76822
Status: zrealizowano
"""

APPEAL = """Gdynia, dnia 17 czerwca 2026 roku
Prezes Krajowej Izby Odwoławczej
Odwołujący: Dostawca Alfa S.A.
KRS: 0004020161, NIP: 5210000456
reprezentowany przez: adw. Anna Maj
adres do korespondencji: Kancelaria Prawna Spółka z ograniczoną
odpowiedzialnością, ul. Błękitna 7
E-mail: anna@example.org
Zamawiający (zamawiający wspólnie przeprowadzający postępowanie na podstawie art. 38 ust.
1 Pzp):
1) Zamawiający – Lider, prowadzący postępowanie:
Gmina Wzgórza
NIP 0210005390
2) Zamawiający – Partner:
Gmina Świerki
NIP 2780002322
ODWOŁANIE
dotyczy: postępowania pn. „Konserwacja mostu”, nr referencyjny: ZP/18/2026, BZP 2026/BZP 00002145.
Działając w imieniu Dostawca Alfa S.A. wnoszę odwołanie wobec czynności polegających na:
1) zaniechaniu odrzucenia oferty konkurenta z dnia 10 czerwca 2026 r.;
2) wykluczeniu wykonawcy z dnia 11 czerwca 2026 r.
"""

POWER = """PEŁNOMOCNICTWO
Ja, niżej podpisany Piotr Gaj, prowadzący działalność gospodarczą pod firmą Gaj Serwis Piotr Gaj,
ul. Łączna 8, NIP 2270009150, niniejszym udzielam pełnomocnictwa: adw. Anna Maj (PESEL 02110100011).
Pełnomocnictwo obejmuje umocowanie do reprezentacji przed KIO.
................
Piotr Gaj
Właściciel
Pełnomocnictwo przyjmuję:
................
Anna Maj
"""


def document(text: str) -> Document:
    return Document((Page(1, clean(text), 'pdf'),), 1, ())


def text_pdf(path: Path, lines: str) -> None:
    content = 'BT /F1 12 Tf 50 760 Td 17 TL\n' + '\n'.join(
        f'({line}) Tj T*' for line in lines.splitlines()
    ) + '\nET'
    stream = content.encode('ascii')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream',
    ]
    data = io.BytesIO(b'%PDF-1.4\n')
    data.seek(0, io.SEEK_END)
    offsets = [0]
    for index, item in enumerate(objects, 1):
        offsets.append(data.tell())
        data.write(f'{index} 0 obj\n'.encode() + item + b'\nendobj\n')
    xref = data.tell()
    data.write(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.write(f'{offset:010d} 00000 n \n'.encode())
    data.write(f'trailer\n<< /Root 1 0 R /Size {len(offsets)} >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    path.write_bytes(data.getvalue())


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = Pipeline(load_classes(), PdfReader.from_env())

    def test_transfer_uses_operation_date_and_preserves_account_zeros(self):
        result = self.pipeline.analyze(document(TRANSFER), trace=True)
        self.assertEqual(result.class_id, 'przelew')
        self.assertEqual(result.data['przelew_bankowy'], {
            'data_operacji': '2026-07-10', 'kwota': 1735.50,
            'z_rachunku': '02908100000001000200030004', 'na_rachunek': '13908100000001000200030005',
            'numer_transakcji': 'XYZ-76822', 'tytul': 'Wpis od odwołania ABC/2/2026',
        })
        self.assertEqual(result.evidence['/przelew_bankowy/z_rachunku']['page'], 1)

    def test_appeal_uses_first_action_and_multiple_authorities(self):
        data = self.pipeline.analyze(document(APPEAL)).data
        self.assertEqual(data['OdwolanieKIO']['czynnosc_powod_id'], 7)
        self.assertEqual(data['OdwolanieKIO']['czynnosc_dzien'], '2026-06-10')
        self.assertEqual(data['OdwolanieKIO']['data'], '2026-06-17')
        self.assertEqual(data['Odwolujacy'][0]['pelnomocnik']['nazwa'],
                         'Kancelaria Prawna Spółka z ograniczoną odpowiedzialnością')
        self.assertEqual([row['nazwa'] for row in data['Zamawiajacy']], ['Gmina Wzgórza', 'Gmina Świerki'])
        self.assertEqual([row['prowadzacy_postepowanie'] for row in data['Zamawiajacy']], [1, 0])
        self.assertEqual(data['ZamowieniePubliczne']['numer_bzp'], '2026/BZP00002145')

    def test_appeal_uses_explicit_declaration_when_ocr_flattens_trailing_labels(self):
        data = self.pipeline.analyze(document("""Gdynia, 11.05.2026 r.
Prezes Krajowej Izby Odwoławczej
reprezentowany przez pełnomocnika
Odwołujący:
Gmina Północna Spółka z ograniczoną
odpowiedzialnością
Zamawiający:
Dotyczy: (postępowanie nr IR/42/2026)
ODWOŁANIE
Działając w imieniu wykonawcy Dostawca Zorza S.A., wnoszę odwołanie wobec czynności, tj.: wobec treści
dokumentów zamówienia — Specyfikacji Warunków Zamówienia.
Odwołanie jest wniesione w terminie.
Zamawiający zamieścił ogłoszenie wraz z dokumentami w dniu 8 maja 2026 r.
""")).data
        self.assertEqual(data['Odwolujacy'][0]['nazwa'], 'Dostawca Zorza S.A.')
        self.assertEqual(data['Zamawiajacy'][0]['nazwa'], 'Gmina Północna Spółka z ograniczoną odpowiedzialnością')
        self.assertEqual(data['OdwolanieKIO']['czynnosc_dzien'], '2026-05-08')
        self.assertEqual(data['ZamowieniePubliczne']['numer_postepowania'], 'IR/42/2026')

    def test_power_roles_and_pesel(self):
        data = self.pipeline.analyze(document(POWER)).data
        self.assertEqual(data['mocodawca'][0]['data']['typ'], 'osoba_fizyczna')
        self.assertEqual(data['mocodawca'][0]['podpisujacy'], [{'imie_nazwisko': 'Piotr Gaj'}])
        self.assertEqual(data['pelnomocnicy'], [{'imie_nazwisko': 'Anna Maj', 'pesel': '02110100011'}])

    def test_transfer_with_bank_columns_and_flattened_reading_order(self):
        result = self.pipeline.analyze(document("""Potwierdzenie transakcji
Opis
Wpis od odwołania ZP-55
Kwota Data transakcji Numer referencyjny transakcji
7 500,00 PLN 21.05.2026 ID-9854
Dane nadawcy
Nazwa i adres Numer rachunku Nazwa banku
FIRMA A PL02 9081 0000 0001 0002 0003 0004 BANK A
Dane odbiorcy
Nazwa i adres Numer rachunku Nazwa banku
FIRMA B PL13 9081 0000 0001 0002 0003 0005 BANK B
Dokument wygenerowano elektronicznie
"""))
        self.assertEqual(result.data['przelew_bankowy'], {
            'data_operacji': '2026-05-21', 'kwota': 7500.0, 'numer_transakcji': 'ID-9854',
            'tytul': 'Wpis od odwołania ZP-55', 'z_rachunku': '02908100000001000200030004',
            'na_rachunek': '13908100000001000200030005',
        })

    def test_ambiguous_ocr_amount_is_not_interpreted_as_an_integer(self):
        for raw, expected in (
            ('1 463 25', None), ('1 463,25', 1463.25), ('1.463,25', 1463.25),
            ('1,463.25', 1463.25), ('146325', 146325.0),
        ):
            with self.subTest(raw=raw):
                result = self.pipeline.analyze(document(TRANSFER.replace('1 735,50', raw)))
                self.assertEqual(result.data['przelew_bankowy']['kwota'], expected)

    def test_ocr_retry_can_recover_an_unclassified_scan(self):
        class Reader:
            def read(self, source):
                return Document((Page(1, 'W3VINZ0d', 'ocr'),), 1, ())

            def retry(self, source, number, method):
                return Page(number, clean(TRANSFER), 'ocr', method)

        pipeline = Pipeline(self.pipeline.classes, Reader())
        result = pipeline.process(b'scan', trace=True)
        self.assertEqual(result.class_id, 'przelew')
        self.assertEqual(result.ocr_retries, 1)
        self.assertEqual(result.pages[0]['ocr_method'], 'rotate_180')
        self.assertEqual(result.data['przelew_bankowy']['kwota'], 1735.50)

    def test_ocr_retry_retains_existing_values(self):
        class Reader:
            def read(self, source):
                text = TRANSFER.replace('Data realizacji: 10.07.2026\n', '')
                return Document((Page(1, clean(text), 'ocr'),), 1, ())

            def retry(self, source, number, method):
                text = TRANSFER.replace('1 735,50', '1 785,50') if method == 'deskew' else TRANSFER
                return Page(number, clean(text), 'ocr', method)

        pipeline = Pipeline(self.pipeline.classes, Reader())
        result = pipeline.process(b'scan')
        self.assertEqual(result.ocr_retries, 2)
        self.assertEqual(result.pages[0]['ocr_method'], 'single_block')
        self.assertEqual(result.data['przelew_bankowy']['kwota'], 1735.50)
        self.assertEqual(result.data['przelew_bankowy']['data_operacji'], '2026-07-10')

    def test_scan_normalization_and_year_abbreviation(self):
        text = clean_ocr("""ODWOŁANIE
Odwołujący: Dostawca Promień SA.
reprezentowany przez: adw. Anna Maj
E-mail: anna @ kancelaria.example
Zamawiający: Gmina Dobrze
Zamawiający w dniu 18 maja 2026 r. zmodyfikował treść SWZ.
Zarzut nr 1 dotyczy opublikowanych zmian.
""")
        data = self.pipeline.analyze(document(text)).data
        self.assertEqual(data['OdwolanieKIO']['czynnosc_dzien'], '2026-05-18')
        self.assertEqual(data['OdwolanieKIO']['czynnosc_powod_id'], 5)
        self.assertEqual(data['Odwolujacy'][0]['nazwa'], 'Dostawca Promień S.A.')
        self.assertEqual(data['Odwolujacy'][0]['pelnomocnik']['mail'], 'anna@kancelaria.example')

    def test_negative_document_produces_zero_bytes(self):
        result = self.pipeline.analyze(document('WYROK\nKrajowa Izba Odwoławcza oddala odwołanie w całości.'))
        self.assertIsNone(result.class_id)
        self.assertEqual(result.json(), '')

    def test_model_error_uses_local_result(self):
        class Unavailable:
            def extract(self, spec, context):
                raise ModelError('Test timeout')

        pipeline = Pipeline(self.pipeline.classes, self.pipeline.reader, Unavailable())
        result = pipeline.analyze(document(APPEAL))
        self.assertIn('Test timeout', result.warnings)
        self.assertEqual(result.data['OdwolanieKIO']['czynnosc_powod_id'], 7)

    def test_model_identifiers_must_be_present_in_document(self):
        class Model:
            model = 'test-model'

            def extract(self, spec, context):
                return {'Odwolujacy': [{'nazwa': 'Dostawca Alfa S.A.', 'nip': '1111111111', 'krs': '0004020161'}]}

        pipeline = Pipeline(self.pipeline.classes, self.pipeline.reader, Model())
        result = pipeline.analyze(document(APPEAL))
        self.assertEqual(result.data['Odwolujacy'][0]['nip'], '5210000456')
        self.assertEqual(result.data['Odwolujacy'][0]['krs'], '0004020161')

    def test_new_class_and_field_need_configuration_only(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sample.toml').write_text("""id = 'sample'
label = 'Protokół'
description = 'Protokół kontroli'
schema = 'sample.json'
prompt = 'sample.md'
[[signals]]
pattern = '^PROTOKÓŁ KONTROLI$'
weight = 1
[fields]
"kontrola.numer" = '^Numer: (.+)$'
""", encoding='utf8')
            (root / 'sample.md').write_text('Zwróć numer protokołu.', encoding='utf8')
            (root / 'sample.json').write_text(json.dumps({
                'type': 'object', 'required': ['kontrola'], 'additionalProperties': False,
                'properties': {'kontrola': {'type': 'object', 'required': ['numer'],
                                            'properties': {'numer': {'type': ['string', 'null']}}}},
            }), encoding='utf8')
            pipeline = Pipeline(load_classes(root), self.pipeline.reader)
            result = pipeline.analyze(document('PROTOKÓŁ KONTROLI\nNumer: A-42'))
            self.assertEqual(result.data, {'kontrola': {'numer': 'A-42'}})

    def test_batch_mirrors_paths_and_ignores_filenames_for_classification(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            inputs, outputs = root / 'input', root / 'output'
            (inputs / 'case1').mkdir(parents=True)
            text_pdf(inputs / 'case1/odwolanie.pdf', 'POTWIERDZENIE PRZELEWU\nKwota 24,00 PLN\nZ rachunku 02908100000001000200030004')
            text_pdf(inputs / 'case1/przelew.pdf', 'WYROK\nKrajowa Izba Odwolawcza oddala w calosci rozpatrywane odwolanie.')
            self.assertEqual(main(['extract', '-i', str(inputs), '-o', str(outputs), '--engine', 'rules']), 0)
            data = json.loads((outputs / 'case1/odwolanie.json').read_text(encoding='utf8'))
            self.assertEqual(data['przelew_bankowy']['kwota'], 24)
            self.assertEqual((outputs / 'case1/przelew.json').read_bytes(), b'')

    def test_preview_renders_the_source_page(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'source.pdf'
            text_pdf(path, 'POTWIERDZENIE PRZELEWU\nKwota 24,00 PLN')
            image, pages = self.pipeline.reader.preview(path.read_bytes(), 1)
            self.assertEqual(pages, 1)
            with Image.open(io.BytesIO(image)) as rendered:
                self.assertEqual(rendered.format, 'PNG')
                self.assertGreater(rendered.width, 1000)

    def test_image_only_pdf_uses_ocr(self):
        reader = self.pipeline.reader
        if not shutil.which(reader.tesseract):
            self.skipTest('Tesseract is unavailable')
        image = Image.new('L', (1200, 600), 255)
        ImageDraw.Draw(image).text(
            (70, 70), 'POTWIERDZENIE PRZELEWU\nKwota 100,00 PLN\nData operacji 2026-01-20',
            fill=0, font=ImageFont.load_default(size=45), spacing=25,
        )
        with io.BytesIO() as buffer:
            image.convert('RGB').save(buffer, 'PDF', resolution=144)
            result = self.pipeline.process(buffer.getvalue())
        self.assertEqual(result.pages[0]['source'], 'ocr')
        self.assertEqual(result.data['przelew_bankowy']['kwota'], 100)


if __name__ == '__main__':
    unittest.main()
