"""Read PDF text and use local Tesseract on pages without usable text."""

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
from threading import Lock

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from .text import clean, clean_ocr

# PDFium's API is process-global and cannot be called from two threads at once.
PDFIUM_LOCK = Lock()


class DocumentError(Exception):
    """A PDF or its OCR could not be processed."""


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    source: str
    ocr_method: str | None = None


@dataclass(frozen=True)
class Document:
    pages: tuple[Page, ...]
    total_pages: int
    warnings: tuple[str, ...]

    @property
    def text(self) -> str:
        return '\n'.join(page.text for page in self.pages if page.text)


@dataclass(frozen=True)
class PdfReader:
    tesseract: str = 'tesseract'
    language: str = 'pol+eng'
    tessdata: str | None = None
    ocr_pages: int = 5
    native_pages: int = 12
    dpi: int = 260
    timeout: float = 24

    @classmethod
    def from_env(cls, ocr_pages: int = 5) -> 'PdfReader':
        path = os.getenv('O2J_TESSERACT')
        if not path and os.name == 'nt':
            conventional = Path(os.getenv('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tesseract.exe'
            path = str(conventional) if conventional.is_file() else None
        return cls(path or 'tesseract', os.getenv('O2J_OCR_LANG', 'pol+eng'), os.getenv('O2J_TESSDATA'), ocr_pages)

    def ocr(self, image, psm: str = '3', *, dpi: int | None = None, timeout: float | None = None) -> str:
        command = [self.tesseract, 'stdin', 'stdout', '-l', self.language, '--psm', psm, '--dpi', str(dpi or self.dpi)]
        if self.tessdata:
            command.extend(['--tessdata-dir', self.tessdata])
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        try:
            process = subprocess.run(
                command, input=buffer.getvalue(), capture_output=True, timeout=timeout or self.timeout,
                env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
            )
        except FileNotFoundError as exc:
            raise DocumentError('Zainstaluj Tesseract i pakiet języka polskiego (pol).') from exc
        except subprocess.TimeoutExpired as exc:
            raise DocumentError('Przekroczono limit czasu OCR strony.') from exc
        except OSError as exc:
            raise DocumentError('Nie można uruchomić Tesseract.') from exc
        if process.returncode or b'Failed loading language' in process.stderr:
            raise DocumentError('Tesseract zgłosił błąd. Sprawdź instalację pakietów językowych pol i eng.')
        return clean_ocr(process.stdout.decode('utf-8', 'replace'))

    def retry(self, source: Path | bytes, number: int, method: str) -> Page:
        dpi = 300
        try:
            with PDFIUM_LOCK, pdfium.PdfDocument(source) as pdf:
                page = pdf[number - 1]
                try:
                    image = render_scan(page, dpi)
                finally:
                    page.close()
        except (pdfium.PdfiumError, OSError) as exc:
            raise DocumentError('Nie można ponownie odczytać strony PDF.') from exc
        if method == 'rotate_180':
            image = image.transpose(Image.Transpose.ROTATE_180)
        corrected = deskew(ImageOps.autocontrast(image, cutoff=0.7))
        text = self.ocr(corrected, '6' if method == 'single_block' else '3', dpi=dpi, timeout=min(10, self.timeout))
        return Page(number, text, 'ocr', method)

    def preview(self, source: bytes, number: int) -> tuple[bytes, int]:
        try:
            with PDFIUM_LOCK, pdfium.PdfDocument(source) as pdf:
                total = len(pdf)
                if not 1 <= number <= total:
                    raise DocumentError('Wskazana strona nie istnieje w dokumencie.')
                page = pdf[number - 1]
                try:
                    scale = min(2.5, 1600 / max(page.get_size()))
                    bitmap = page.render(scale=scale, draw_annots=True)
                    try:
                        image = bitmap.to_pil().copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        except (pdfium.PdfiumError, OSError) as exc:
            raise DocumentError('Nie można przygotować podglądu PDF.') from exc
        with BytesIO() as buffer:
            image.save(buffer, format='PNG')
            return buffer.getvalue(), total

    def read(self, source: Path | bytes) -> Document:
        try:
            with PDFIUM_LOCK:
                pdf = pdfium.PdfDocument(source)
                total = len(pdf)
        except (pdfium.PdfiumError, OSError) as exc:
            raise DocumentError('Nie można otworzyć PDF. Sprawdź format i zabezpieczenie hasłem.') from exc
        pages = []
        warnings = []
        used_ocr = 0
        try:
            indices = sorted(set(range(min(total, self.native_pages))) | set(range(max(0, total - 2), total)))
            for index in indices:
                with PDFIUM_LOCK:
                    page = pdf[index]
                    try:
                        textpage = page.get_textpage()
                        try:
                            native = clean(textpage.get_text_bounded())
                        finally:
                            textpage.close()
                        low_text = not usable(native)
                        image = None
                        if low_text and used_ocr < self.ocr_pages:
                            image = render_scan(page, self.dpi)
                    finally:
                        page.close()
                if image is None:
                    pages.append(Page(index + 1, native, 'pdf'))
                    continue
                used_ocr += 1
                try:
                    scanned = self.ocr(image)
                    if not usable(scanned) and image.width > image.height * 1.2:
                        options = [scanned, self.ocr(image.rotate(90, expand=True)),
                                   self.ocr(image.rotate(270, expand=True))]
                        scanned = max(options, key=text_quality)
                except DocumentError as exc:
                    if str(exc) not in warnings:
                        warnings.append(str(exc))
                    pages.append(Page(index + 1, native, 'pdf'))
                    continue
                pages.append(Page(index + 1, scanned or native, 'ocr'))
        except pdfium.PdfiumError as exc:
            raise DocumentError('Nie można odczytać strony PDF.') from exc
        finally:
            with PDFIUM_LOCK:
                pdf.close()
        if warnings and not usable('\n'.join(page.text for page in pages)):
            raise DocumentError(warnings[0])
        if total > len(indices):
            warnings.append(f'Odczytano {len(indices)} z {total} stron.')
        if sum(not usable(page.text) for page in pages if page.source == 'pdf') and used_ocr >= self.ocr_pages > 0:
            warnings.append('Osiągnięto limit stron OCR dla dokumentu.')
        return Document(tuple(pages), total, tuple(warnings))


def render_scan(page, dpi: int) -> Image.Image:
    scale = min(dpi / 72, 3300 / max(page.get_size()))
    bitmap = page.render(scale=scale, grayscale=True, draw_annots=True)
    try:
        return bitmap.to_pil().copy()
    finally:
        bitmap.close()


def deskew(image: Image.Image) -> Image.Image:
    thumbnail = image.copy()
    thumbnail.thumbnail((420, 600))
    width, height = thumbnail.size
    margin = max(1, min(width, height) // 12)
    if min(width, height) < 24:
        return image

    def alignment(angle: float) -> int:
        rotated = thumbnail.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255)
        middle = rotated.crop((margin, margin, width - margin, height - margin))
        bits = middle.point(lambda shade: 0 if shade < 145 else 255).tobytes()
        stride = middle.width
        rows = [bits.count(0, offset, offset + stride) for offset in range(0, len(bits), stride)]
        return sum((current - previous) ** 2 for previous, current in zip(rows, rows[1:]))

    angles = (0, -2, 2, -4, 4, -6, 6)
    scores = {angle: alignment(angle) for angle in angles}
    best = max(scores, key=scores.get)
    if not best or scores[best] <= scores[0] * 1.12:
        return image
    return image.rotate(best, resample=Image.Resampling.BICUBIC, fillcolor=255)


def text_quality(value: str) -> int:
    return sum(len(word) for word in re.findall(r'[^\W\d_]{3,}', value))


def usable(value: str) -> bool:
    return text_quality(value) >= 30 and '\ufffd' not in value and len(re.findall(r'\(cid:\d+\)', value)) < 3
