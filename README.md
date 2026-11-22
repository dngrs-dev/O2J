# Odwołania2JSON

Aplikacja dla wyzwania UZP na HackNation 2026. Rozpoznaje odwołania do KIO, pełnomocnictwa i potwierdzenia przelewu na podstawie treści PDF. Obsługuje dokumenty cyfrowe i skany, działa na CPU i zapisuje po jednym pliku JSON dla każdego PDF. Dokument spoza obsługiwanych klas daje plik o długości 0 bajtów. [Specyfikacja i dane UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026)

## Uruchomienie

Wymagania to **Python 3.13 lub nowszy** oraz **Tesseract 5 z pakietami pol i eng** do OCR. Praca z warstwą tekstową PDF oraz przetwarzanie skanów w trybie lokalnym działają na CPU bez klucza API.

**Windows · PowerShell**

~~~powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.bat
.\start.bat serve
~~~

Zainstaluj Tesseract wraz z językiem polskim. Program wykrywa standardowy katalog instalacji Windows lub szuka polecenia w PATH. Przy instalacji niestandardowej ustaw O2J_TESSERACT na ścieżkę do tesseract.exe. Tesseract --list-langs powinien wyświetlić pol i eng. [Instalacja Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html)

**Linux · Debian/Ubuntu**

~~~sh
sudo apt-get install tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m o2j
python -m o2j serve
~~~

**Docker Compose**

~~~sh
docker compose up --build gui
docker compose run --build --rm batch
~~~

Compose montuje katalogi input, output i config z repozytorium. Na Linuksie katalog output musi być zapisywalny dla użytkownika kontenera. Jeśli Twój UID lub GID różni się od 1000, wpisz odpowiednie wartości O2J_UID i O2J_GID w lokalnym pliku .env.

## Przetwarzanie i podgląd

Umieść pliki w input. Polecenie python -m o2j przetwarza je rekurencyjnie. Na przykład input/sprawa-01/pismo.pdf zapisze wynik w output/sprawa-01/pismo.json. Puste pliki oznaczają dokumenty spoza zakresu. Błędy odczytu są raportowane na stderr, a partia kończy się kodem 1, jeśli któregokolwiek pliku nie udało się przetworzyć.

~~~sh
python -m o2j extract --input input --output output --engine rules
python -m o2j extract --input dokument.pdf --output output --trace-dir trace
python -m o2j extract --help
~~~

Po uruchomieniu polecenia python -m o2j serve otwórz przeglądarkę pod adresem http://127.0.0.1:8765. Wybierz PDF lub przeciągnij go do aplikacji i wybierz **Analizuj**. Interfejs wyświetla PDF obok JSON, umożliwia przejście do stron zawierających odnalezione pola oraz kopię i pobranie wyniku.

## Tryb hybrydowy i wybór modelu

Domyślny tryb auto używa lokalnych reguł. Gdy skonfigurujesz klucz, model może uzupełnić ekstrakcję i rozstrzygnąć klasyfikację przy niewystarczających sygnałach. Kompletne formularze bankowe są rozwiązywane lokalnie. W razie błędu modelu aplikacja zwraca lokalny wynik i opisuje błąd w diagnostyce.

| Profil | Endpoint i model | Parametry |
| --- | --- | --- |
| Scaleway, Paryż | https://api.scaleway.ai/v1 · mistral/mistral-small-3.2-24b-instruct-2506:fp8 | 24B, Apache 2.0 |
| Mistral EU, po potwierdzeniu dostępności w koncie | https://api.eu.mistral.ai/v1 · ministral-8b-2512 | 8B, Apache 2.0 |
| Własny serwer, np. Ollama | http://127.0.0.1:11434/v1 · identyfikator zainstalowanego modelu | Zależnie od modelu |

Profile mają otwarte wagi i istnieje możliwość instalacji lokalnej. W przypadku zewnętrznego dostawcy użyj endpointu przetwarzającego dane w UE/EOG. Tryb hybrydowy przekazuje do skonfigurowanego endpointu fragmenty tekstu, które mogą zawierać dane z dokumentu. [Lokalizacja Scaleway](https://www.scaleway.com/en/docs/generative-apis/faq/) · [Polityka Scaleway](https://www.scaleway.com/en/docs/generative-apis/reference-content/data-privacy/) · [Model 24B](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506) · [Mistral EU](https://docs.mistral.ai/inference/regional-inference) · [Model 8B](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512)

Ustaw O2J_API_KEY w środowisku uruchomieniowym. O2J_API_BASE i O2J_MODEL pozwalają zmienić profil. W Compose możesz skopiować .env.example do .env i uzupełnić wartości. W trybie natywnym użyj zmiennych środowiskowych powłoki. Do oceny trybu hybrydowego przekaż klucz organizatorowi uzgodnionym kanałem prywatnym. Kod repozytorium nie wymaga przechowywania kluczy.

Pierwszy eksperyment z mniejszym modelem powinien używać tych samych schematów, promptów i publicznego benchmarku. Zacznij od temperatury 0 i porównaj F1 per klasa, F1 skanów i czas wykonania. Zmienna O2J_TEMPERATURE steruje losowością, O2J_API_TIMEOUT ustala limit pojedynczego żądania, a O2J_MODEL wybiera wersję wag. Dane skanów są najlepszym miejscem do sprawdzenia, czy model uzasadnia dodatkowy czas i koszt.

## Ocena

~~~sh
git clone https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026.git ../hacknation-2026
python -m o2j benchmark ../hacknation-2026/dane --engine rules --jobs 6 --report .work/benchmark.json
python -m unittest discover -s tests -v
~~~

Benchmark pokazuje mikro-F1 dla niepustych wartości według dokładnej ścieżki i wartości JSON, klasyfikację, liczbę pełnych dopasowań i czas. Pary dokumentów oraz referencji dobierane są w benchmarku, w tym udokumentowana rozbieżność nazw w publicznym zbiorze przelewów. Ocena na niejawnym zbiorze i dokładny sposób liczenia F1 przez organizatora pozostają odrębną walidacją.

[Wyniki benchmarku](docs/wyniki.md) · [Architektura i dodawanie klas](docs/architektura.md)
