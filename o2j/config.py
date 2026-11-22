"""Load document classes, extraction prompts and output contracts."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / 'config'


@dataclass(frozen=True)
class Signal:
    pattern: re.Pattern
    weight: int


@dataclass(frozen=True)
class DocumentClass:
    id: str
    label: str
    description: str
    validator: Draft202012Validator
    instructions: str
    signals: tuple[Signal, ...]
    minimum_score: int
    extractor: str | None
    fields: dict[str, re.Pattern]
    review_fields: tuple[str, ...] = ()

    @property
    def schema(self) -> dict:
        return self.validator.schema


def load_classes(directory: Path = DEFAULT_CONFIG) -> dict[str, DocumentClass]:
    classes = {}
    for path in sorted(directory.glob('*.toml')):
        cfg = tomllib.loads(path.read_text(encoding='utf-8'))
        key = cfg['id']
        if key in classes or not re.fullmatch(r'[a-z][a-z0-9_]*', key):
            raise ValueError(f'Nieprawidłowy lub powtórzony identyfikator klasy w {path.name}')
        schema = json.loads((directory / cfg['schema']).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        if schema.get('type') != 'object':
            raise ValueError(f'Schemat {key} musi definiować obiekt JSON')
        classes[key] = DocumentClass(
            key, cfg['label'], cfg['description'],
            Draft202012Validator(schema, format_checker=FormatChecker()),
            (directory / cfg['prompt']).read_text(encoding='utf-8').strip(),
            tuple(Signal(re.compile(s['pattern'], re.I | re.M), s['weight']) for s in cfg.get('signals', [])),
            cfg.get('minimum_score', 1), cfg.get('extractor'),
            {name: re.compile(pattern, re.I | re.M) for name, pattern in cfg.get('fields', {}).items()},
            tuple(cfg.get('review_fields', [])),
        )
        for field, pattern in classes[key].fields.items():
            if pattern.groups != 1 or any(not part for part in field.split('.')):
                raise ValueError(f'Pole {field} w klasie {key} wymaga dokładnie jednej grupy przechwytującej.')
            target = schema
            for part in field.split('.'):
                if part not in target.get('properties', {}):
                    raise ValueError(f'Pole {field} nie istnieje w schemacie klasy {key}.')
                target = target['properties'][part]
    if not classes:
        raise ValueError(f'Brak konfiguracji klas w {directory}')
    return classes
