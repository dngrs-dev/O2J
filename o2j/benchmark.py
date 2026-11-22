"""Evaluate the public UZP corpus with reproducible, exact leaf matching."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter

from .pdf import DocumentError
from .pipeline import Pipeline, scalar_fields

CLASS_KEYS = {'OdwolanieKIO': 'odwolanie', 'mocodawca': 'pelnomocnictwo', 'przelew_bankowy': 'przelew'}
NEGATIVE = 'poza_zakresem'


@dataclass
class Counts:
    correct: int = 0
    extra: int = 0
    missing: int = 0

    def update(self, expected: Counter, actual: Counter) -> None:
        self.correct += sum((expected & actual).values())
        self.extra += sum((actual - expected).values())
        self.missing += sum((expected - actual).values())

    def metrics(self) -> dict:
        precision = self.correct / (self.correct + self.extra) if self.correct + self.extra else 0
        recall = self.correct / (self.correct + self.missing) if self.correct + self.missing else 0
        return {'tp': self.correct, 'fp': self.extra, 'fn': self.missing, 'precision': round(precision, 5),
                'recall': round(recall, 5), 'f1': round(2 * precision * recall / (precision + recall), 5)
                if precision + recall else 0}


def reference(path: Path) -> dict:
    expected = path.with_suffix('.json')
    # The organizer names most transfer references przelew.json alongside potwierdzenie_przelewu.pdf.
    if not expected.exists() and path.stem.casefold() == 'potwierdzenie_przelewu':
        expected = path.with_name('przelew.json')
    if not expected.exists():
        return {}
    value = expected.read_text(encoding='utf-8-sig').strip()
    return json.loads(value) if value else {}


def pairs(value: dict) -> Counter:
    return Counter((path, field) for path, _, field in scalar_fields(value))


def benchmark(dataset: Path, pipeline: Pipeline, jobs: int) -> dict:
    sources = sorted(file for file in dataset.rglob('*') if file.is_file() and file.suffix.lower() == '.pdf')
    if not sources:
        raise ValueError(f'Brak plików PDF w {dataset}.')
    micro = Counts()
    per_class = defaultdict(Counts)
    per_group = defaultdict(Counts)
    confusion = defaultdict(Counter)
    errors = []
    warning_counts = Counter()
    num_ocr = 0
    retries = 0
    rescued = 0
    exact = 0
    started = perf_counter()

    def run(path):
        expected = reference(path)
        try:
            return path, expected, pipeline.process(path), None
        except (DocumentError, OSError) as exc:
            return path, expected, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(jobs, len(sources))) as pool:
        for path, expected, result, error in pool.map(run, sources):
            group = 'skany' if 'skany' in path.relative_to(dataset).parts else 'pozostałe'
            expected_class = next((kind for key, kind in CLASS_KEYS.items() if key in expected), NEGATIVE)
            if error:
                errors.append({'file': path.relative_to(dataset).as_posix(), 'error': error})
            if result:
                num_ocr += any(page['source'] == 'ocr' for page in result.pages)
                retries += result.ocr_retries
                rescued += any(page.get('ocr_method') for page in result.pages)
                warning_counts.update(result.warnings)
            actual = result.data if result and result.data is not None else {}
            actual_class = (result.class_id or NEGATIVE) if result else 'błąd'
            confusion[expected_class][actual_class] += 1
            expected_pairs, actual_pairs = pairs(expected), pairs(actual)
            exact += actual == expected and actual_class == expected_class
            for metric in (micro, per_class[expected_class], per_group[group]):
                metric.update(expected_pairs, actual_pairs)

    return {
        'documents': len(sources),
        'exact_documents': exact,
        'classification_accuracy': round(sum(row.get(key, 0) for key, row in confusion.items()) / len(sources), 5),
        'classification': dict(confusion),
        'fields_micro': micro.metrics(),
        'fields_by_class': {key: count.metrics() for key, count in sorted(per_class.items())},
        'fields_by_group': {key: count.metrics() for key, count in sorted(per_group.items())},
        'documents_with_ocr': num_ocr,
        'ocr_retry_calls': retries,
        'documents_using_ocr_retry': rescued,
        'seconds': round(perf_counter() - started, 2),
        'processing_errors': errors,
        'warnings': dict(warning_counts),
    }
