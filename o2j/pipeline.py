"""Coordinate content classification, extraction, validation and provenance."""

from collections.abc import Iterator
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
import re
from time import perf_counter

from jsonschema import ValidationError

from .appeal import REASONS, appeal
from .config import DocumentClass
from .model import ModelClient, ModelError
from .pdf import Document, DocumentError, PdfReader, usable
from .power import power
from .text import DATE, flat, folded, iso_date
from .transfer import transfer

EXTRACTORS = {'appeal': appeal, 'power': power, 'transfer': transfer}


@dataclass(frozen=True)
class Result:
    class_id: str | None
    label: str
    data: dict | None
    engine: str
    scores: dict[str, int]
    pages: tuple[dict, ...]
    total_pages: int
    evidence: dict[str, dict]
    warnings: tuple[str, ...]
    seconds: float
    ocr_retries: int = 0

    def as_dict(self) -> dict:
        return asdict(self)

    def json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2, allow_nan=False) + '\n' if self.data is not None else ''


@dataclass(frozen=True)
class RuleAssessment:
    key: str | None
    scores: dict[str, int]
    data: dict | None


def classify(document: Document, classes: dict[str, DocumentClass]) -> tuple[str | None, dict[str, int]]:
    # Classification uses document openings: attachments and legal quotations can mention every class.
    opening = '\n'.join(page.text for page in document.pages if page.number <= 2)[:8500]
    scores = {key: sum(s.weight for s in spec.signals if s.pattern.search(opening))
              for key, spec in classes.items()}
    eligible = sorted((key for key, score in scores.items() if score >= classes[key].minimum_score),
                      key=scores.get, reverse=True)
    if not eligible or len(eligible) > 1 and scores[eligible[0]] == scores[eligible[1]]:
        return None, scores
    return eligible[0], scores


def source_context(document: Document, budget: int, include_tail: bool = True) -> str:
    pages = [page for page in document.pages if page.text]
    if not pages:
        return ''
    tail = pages[-2:] if include_tail and len(pages) > 3 else []
    head = pages[:-2] if tail else pages
    tail_budget = min(budget // 5, 3800) if tail else 0
    prefix = '\n\n'.join(f'[Strona {page.number}]\n{page.text}' for page in head)
    suffix = '\n\n'.join(f'[Strona {page.number}]\n{page.text}' for page in tail)
    if tail and len(suffix) > tail_budget:
        suffix = f'[Końcowe fragmenty stron {tail[0].number}–{tail[-1].number}]\n' + suffix[-tail_budget:]
    return prefix[:budget - tail_budget] + ('\n\n' + suffix if tail else '')


def configured_fields(text: str, spec: DocumentClass, result: dict) -> None:
    for name, pattern in spec.fields.items():
        match = pattern.search(text)
        if not match or match[1] is None:
            continue
        path = name.split('.')
        schema = spec.schema
        output = result
        for part in path[:-1]:
            schema = schema['properties'][part]
            output = output.setdefault(part, {})
        schema = schema['properties'][path[-1]]
        types = schema.get('type', [])
        value = flat(match[1])
        try:
            if schema.get('format') == 'date':
                value = iso_date(value)
            elif 'integer' in types and 'string' not in types:
                value = int(value)
            elif 'number' in types and 'string' not in types:
                value = float(value.replace(',', '.'))
        except ValueError:
            continue
        output[path[-1]] = value


def item_identity(value) -> str:
    if not isinstance(value, dict):
        return ''
    details = value.get('data')
    item = details if isinstance(details, dict) else value
    name = item.get('nazwa') or item.get('imie_nazwisko')
    return folded(flat(name)) if isinstance(name, str) else ''


def conform(value, fallback, schema, validator, source: str | None = None, key: str = ''):
    """Fill missing keys and check inferred identifiers against the source text."""
    if schema.get('type') == 'object' and 'properties' in schema:
        value = value if isinstance(value, dict) else {}
        fallback = fallback if isinstance(fallback, dict) else {}
        output = {} if schema.get('additionalProperties') is False else dict(value or fallback)
        for name, child in schema['properties'].items():
            if name in value or name in fallback or name in schema.get('required', ()):
                output[name] = conform(value.get(name), fallback.get(name), child, validator, source, name)
        return output
    if schema.get('type') == 'array' and 'items' in schema:
        if not isinstance(value, list) or not value and fallback:
            return fallback if isinstance(fallback, list) else []
        matches = {identity: item for item in (fallback or []) if (identity := item_identity(item))}
        return [conform(item, matches.get(item_identity(item)), schema['items'], validator, source) for item in value]
    if isinstance(value, str):
        value = flat(value) or None
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    if source and key in {'krs', 'nip', 'regon', 'pesel', 'z_rachunku', 'na_rachunek'} and value is not None:
        digits = re.sub(r'\D', '', str(value))
        pattern = r'(?<!\d)' + r'[ \t.-]*'.join(digits) + r'(?!\d)'
        if not digits or not re.search(pattern, source):
            value = None
    check = validator.evolve(schema=schema)
    if value is not None and check.is_valid(value):
        return value
    return fallback if fallback is not None and check.is_valid(fallback) else None


def scalar_fields(value, path: str = '') -> Iterator[tuple[str, str, str | int | float]]:
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = key.replace('~', '~0').replace('/', '~1')
            yield from scalar_fields(item, f'{path}/{escaped}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from scalar_fields(item, f'{path}/{index}')
    elif value is not None:
        yield path, path.rsplit('/', 1)[-1], value


def evidence_for(data: dict | None, document: Document) -> dict[str, dict]:
    if not data:
        return {}
    pages = [(page, flat(page.text)) for page in document.pages]
    normalized = [(page, text, folded(text)) for page, text in pages]
    evidence = {}
    for path, key, value in scalar_fields(data):
        if key in {'czynnosc_powod_id', 'prowadzacy_postepowanie', 'przez-pelnomocnika', 'typ'}:
            continue
        literal = str(value)
        for page, raw, text in normalized:
            index = text.find(folded(literal)) if len(literal) >= 3 else -1
            end = index + len(literal)
            if index < 0 and literal.isdigit() and len(literal) >= 9:
                match = re.search(r'(?<!\d)' + r'[ .-]*'.join(literal) + r'(?!\d)', text)
                if match:
                    index, end = match.span()
            if index < 0 and re.fullmatch(r'\d{4}-\d{2}-\d{2}', literal):
                match = next((date for date in re.finditer(DATE, raw, re.I) if iso_date(date[0]) == literal), None)
                if match:
                    index, end = match.span()
            if index >= 0:
                evidence[path] = {'page': page.number, 'source': page.source,
                                  'text': raw[max(0, index - 38):end + 45]}
                break
    return evidence


def has_field(value, path: str) -> bool:
    for part in path.split('.'):
        if isinstance(value, list) and part.isascii() and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return False
    return value is not None and value != '' and value != []


class Pipeline:
    def __init__(self, classes: dict[str, DocumentClass], reader: PdfReader, model: ModelClient | None = None,
                 *, retry_ocr: bool = True):
        self.classes = classes
        self.reader = reader
        self.model = model
        self.retry_ocr = retry_ocr
        for spec in classes.values():
            if spec.extractor and spec.extractor not in EXTRACTORS:
                raise ValueError(f'Nieznany ekstraktor w klasie {spec.id}: {spec.extractor}')

    def process(self, source: Path | bytes, *, trace: bool = False) -> Result:
        started = perf_counter()
        document = self.reader.read(source)
        assessment = self.assess(document)
        retries = 0
        if self.retry_ocr:
            document, assessment, retries = self.retry_scan(source, document, assessment)
        return self.analyze(document, trace=trace, started=started, assessment=assessment, ocr_retries=retries)

    def rule_data(self, key: str, text: str) -> dict:
        spec = self.classes[key]
        baseline = EXTRACTORS[spec.extractor](text) if spec.extractor else {}
        configured_fields(text, spec, baseline)
        return conform(baseline, None, spec.schema, spec.validator)

    def assess(self, document: Document) -> RuleAssessment:
        key, scores = classify(document, self.classes)
        return RuleAssessment(key, scores, self.rule_data(key, document.text) if key else None)

    def missing_fields(self, assessment: RuleAssessment) -> tuple[str, ...]:
        if not assessment.key:
            return ()
        return tuple(path for path in self.classes[assessment.key].review_fields if not has_field(assessment.data, path))

    def improved(self, baseline: RuleAssessment, candidate: RuleAssessment) -> bool:
        if not candidate.key or not self.classes[candidate.key].validator.is_valid(candidate.data):
            return False
        if not baseline.key:
            paths = self.classes[candidate.key].review_fields
            if paths:
                coverage = len(paths) - len(self.missing_fields(candidate))
                return coverage >= min(2, len(paths))
            return bool(next(scalar_fields(candidate.data), None))
        if candidate.key != baseline.key or len(self.missing_fields(candidate)) >= len(self.missing_fields(baseline)):
            return False
        # A different OCR transcript may fill gaps only when all known values agree.
        return set(scalar_fields(baseline.data)) <= set(scalar_fields(candidate.data))

    def retry_scan(self, source: Path | bytes, document: Document, baseline: RuleAssessment
                   ) -> tuple[Document, RuleAssessment, int]:
        scanned = [page for page in document.pages if page.source == 'ocr']
        if not scanned:
            return document, baseline, 0
        missing = self.missing_fields(baseline)
        if baseline.key and not missing:
            return document, baseline, 0
        if not baseline.key and (scanned[0].number > 2 or any(score <= -10 for score in baseline.scores.values())):
            return document, baseline, 0
        signer_only = missing and all('.podpisujacy.' in path for path in missing)
        number = (scanned[-1] if signer_only else scanned[0]).number
        methods = ('deskew', 'single_block') if baseline.key else ('rotate_180', 'deskew')
        attempts = 0
        for method in methods:
            attempts += 1
            try:
                corrected = self.reader.retry(source, number, method)
            except DocumentError:
                continue
            if not usable(corrected.text):
                continue
            candidate_document = replace(document, pages=tuple(
                corrected if page.number == number else page for page in document.pages
            ))
            candidate = self.assess(candidate_document)
            if self.improved(baseline, candidate):
                return candidate_document, candidate, attempts
        return document, baseline, attempts

    def analyze(self, document: Document, *, trace: bool = False, started: float | None = None,
                assessment: RuleAssessment | None = None, ocr_retries: int = 0) -> Result:
        started = perf_counter() if started is None else started
        assessment = assessment or self.assess(document)
        key, scores, data = assessment.key, assessment.scores, assessment.data
        warnings = list(document.warnings)
        text = document.text
        engine = 'rules'
        if key is None and self.model and usable(text):
            try:
                key = self.model.classify(self.classes, source_context(document, 6000, include_tail=False))
                engine = self.model.model
                if key:
                    data = self.rule_data(key, text)
            except ModelError as exc:
                warnings.append(str(exc))
        if key:
            spec = self.classes[key]
            # A complete labelled bank form needs no inference.
            transfer_data = data.get('przelew_bankowy', {})
            complete_transfer = spec.extractor == 'transfer' and all(
                transfer_data.get(field) is not None for field in ('data_operacji', 'kwota', 'na_rachunek', 'tytul', 'z_rachunku')
            )
            if self.model and not complete_transfer:
                try:
                    proposed = self.model.extract(spec, source_context(document, 19000))
                    candidate = conform(proposed, data, spec.schema, spec.validator, text)
                    if spec.extractor == 'appeal':
                        action = candidate['OdwolanieKIO']
                        action['czynnosc_opis'] = REASONS.get(action['czynnosc_powod_id'])
                    spec.validator.validate(candidate)
                    data = candidate
                    engine = self.model.model
                except (ModelError, ValidationError) as exc:
                    warnings.append(str(exc) if isinstance(exc, ModelError) else 'Odpowiedź modelu nie spełnia schematu.')
            if not spec.validator.is_valid(data):
                raise DocumentError(f'Nie udało się zbudować poprawnego wyniku dla klasy {key}.')
        return Result(key, self.classes[key].label if key else 'Poza obsługiwanymi klasami',
                      data, engine, scores,
                      tuple({'number': p.number, 'source': p.source, 'characters': len(p.text),
                             'ocr_method': p.ocr_method} for p in document.pages),
                      document.total_pages, evidence_for(data, document) if trace else {},
                      tuple(warnings), perf_counter() - started, ocr_retries)
