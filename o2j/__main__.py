"""Command-line interface for the contest batch, benchmark and local workbench."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from time import perf_counter

from .config import DEFAULT_CONFIG, ROOT, load_classes
from .model import ModelClient
from .pdf import DocumentError, PdfReader
from .pipeline import Pipeline


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Wymagana liczba całkowita większa od zera.')
    return number


def pdfs(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() == '.pdf':
        return [path]
    if not path.is_dir():
        raise ValueError(f'Nie znaleziono pliku PDF lub katalogu {path}.')
    return sorted(file for file in path.rglob('*') if file.is_file() and file.suffix.lower() == '.pdf')


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=path.parent,
                            prefix='.o2j-', delete=False) as handle:
        temp = Path(handle.name)
        try:
            handle.write(content)
        except BaseException:
            handle.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def extract(args, pipeline: Pipeline) -> int:
    inputs = args.input.resolve()
    outputs = args.output.resolve()
    if args.trace_dir is not None:
        traces = args.trace_dir.resolve()
        if traces.is_relative_to(outputs) or outputs.is_relative_to(traces):
            raise ValueError('Katalog śladu i katalog wynikowy muszą mieć rozłączne ścieżki.')
    if inputs == outputs:
        raise ValueError('Wskaż osobny katalog dla wyników.')
    sources = pdfs(inputs)
    root = inputs if inputs.is_dir() else inputs.parent
    if not sources:
        raise ValueError(f'Brak plików PDF w {inputs}.')
    destinations = [source.relative_to(root).with_suffix('.json') for source in sources]
    paths = {str(path).casefold() for path in destinations}
    if len(paths) != len(destinations):
        raise ValueError('Co najmniej dwa pliki PDF mają tę samą ścieżkę wynikową.')

    def convert(job):
        source, relative = job
        try:
            result = pipeline.process(source, trace=args.trace_dir is not None)
            write_atomic(outputs / relative, result.json())
            if args.trace_dir:
                metadata = result.as_dict()
                del metadata['data']
                write_atomic(args.trace_dir / relative, json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
            return relative, result, None
        except (DocumentError, OSError) as exc:
            return relative, None, str(exc)

    started = perf_counter()
    failures = 0
    with ThreadPoolExecutor(max_workers=min(args.jobs, len(sources))) as pool:
        for relative, result, error in pool.map(convert, zip(sources, destinations, strict=True)):
            if error:
                failures += 1
                print(f'BŁĄD {relative}: {error}', file=sys.stderr)
            else:
                print(f'{relative} | {result.label} | {result.seconds:.2f} s', file=sys.stderr)
                for warning in result.warnings:
                    print(f'  {warning}', file=sys.stderr)
    print(f'Zapisano {len(sources) - failures}/{len(sources)} wyników w {perf_counter() - started:.1f} s.',
          file=sys.stderr)
    return int(bool(failures))


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='katalog konfiguracji klas')
    common.add_argument('--engine', choices=('auto', 'rules', 'hybrid'), default='auto',
                        help='auto wybiera model tylko przy skonfigurowanym API')
    common.add_argument('--ocr-pages', type=positive, default=5, help='limit stron OCR na dokument')
    common.add_argument('--no-ocr-retry', action='store_true', help='wyłącz dodatkowy OCR trudnych skanów')
    cli = argparse.ArgumentParser(prog='python -m o2j', description='Odwołania2JSON | PDF do JSON')
    sub = cli.add_subparsers(dest='command')
    batch = sub.add_parser('extract', parents=[common], help='przetwórz plik PDF lub katalog')
    batch.add_argument('--input', '-i', type=Path, default=ROOT / 'input')
    batch.add_argument('--output', '-o', type=Path, default=ROOT / 'output')
    batch.add_argument('--trace-dir', type=Path)
    batch.add_argument('--jobs', type=positive, default=min(4, os.cpu_count() or 1))
    bench = sub.add_parser('benchmark', parents=[common], help='oceń na oznaczonym zbiorze PDF i JSON')
    bench.add_argument('dataset', type=Path, help='katalog PDF z referencjami JSON')
    bench.add_argument('--report', type=Path, help='zapisz zagregowany raport JSON')
    bench.add_argument('--jobs', type=positive, default=min(4, os.cpu_count() or 1))
    web = sub.add_parser('serve', parents=[common], help='otwórz lokalny interfejs przeglądarkowy')
    web.add_argument('--host', default='127.0.0.1', choices=('127.0.0.1', '0.0.0.0'),
                     help='użyj 0.0.0.0 wewnątrz kontenera')
    web.add_argument('--port', type=positive, default=8765)
    return cli


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in {'extract', 'benchmark', 'serve', '--help', '-h'}:
        arguments.insert(0, 'extract')
    cli = parser()
    args = cli.parse_args(arguments)
    try:
        pipeline = Pipeline(load_classes(args.config), PdfReader.from_env(args.ocr_pages),
                            ModelClient.from_env(args.engine), retry_ocr=not args.no_ocr_retry)
        if args.command == 'extract':
            return extract(args, pipeline)
        if args.command == 'benchmark':
            from .benchmark import benchmark
            report = benchmark(args.dataset, pipeline, args.jobs)
            content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
            if args.report:
                write_atomic(args.report, content)
            sys.stdout.write(content)
            return int(bool(report['processing_errors']))
        from .web import serve
        serve(pipeline, args.host, args.port)
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f'BŁĄD: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(errors='backslashreplace')
    sys.exit(main())
