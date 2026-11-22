# Walidacja ponownego OCR

Porównanie wykonano w trybie lokalnym na CPU. Wersja bazowa pochodzi z commita b429bd1 oznaczonego tagiem v0.1.0-baseline. Wersja z ponownym OCR testuje alternatywną orientację, kontrast i segmentację na wybranej stronie. Akceptuje uzupełnienie rozpoznanego dokumentu, gdy nowy odczyt zachowuje wszystkie dotychczasowe wartości.

## Zbiory

- **Zbiór rozwojowy** obejmuje 16 oryginalnych skanów z czterech fikcyjnych spraw. Posłużył do testowania podejścia i poprawienia normalizacji adresu e-mail oraz daty przed skrótem „r.”.
- **Zbiór odłożony** obejmuje 24 skany z sześciu innych fikcyjnych spraw. Ma odrębne układy dokumentów i obejmuje skany obrócone, pochylone, o słabym kontraście, ze smugami lub z szumem. Każda sprawa zawiera trzy rozpoznawane typy pism i jeden dokument spoza zakresu.
- **Korpus UZP** obejmuje 226 publicznych plików. Służył również do dostrojenia wcześniejszej wersji. [Dane organizatora](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796/dane)

Referencje syntetyczne i stany wejściowe powstały przed zmianą ekstraktora. Metodę ponownego OCR dobrano na zbiorze rozwojowym. Sprawdzenie jednego odłożonego przelewu w przeglądarce wykazało błąd generatora, który usuwał przecinek dziesiętny z obrazu. Przywrócono przecinek w plikach PDF, zachowano zadane wartości referencyjne i ponownie porównano obie wersje na tych samych plikach. Parser zwraca null dla niepoprawnego grupowania cyfr, gdy zapis kwoty jest niejednoznaczny.

Zbiór odłożony mierzy zachowanie na nowych układach syntetycznych. Wynik na niejawnym zbiorze UZP pozostaje nieznany.

## Wyniki

| Zbiór i metryka | Wersja bazowa | Wersja z ponownym OCR |
| --- | ---: | ---: |
| Zbiór rozwojowy · mikro-F1 pól | 0,77083 | 0,98701 |
| Zbiór odłożony · mikro-F1 pól | 0,88959 | 0,98266 |
| Zbiór odłożony · prawidłowa klasa | 21 / 24 | 24 / 24 |
| Zbiór odłożony · pełne dopasowanie JSON | 17 / 24 | 20 / 24 |
| Zbiór odłożony · czas | 5,33 s | 8,11 s |
| Publiczny UZP · mikro-F1 pól | 0,98865 | 0,98951 |
| Publiczny UZP · mikro-F1 plików w katalogu skany | 0,91240 | 0,91954 |
| Publiczny UZP · prawidłowa klasa | 226 / 226 | 226 / 226 |
| Publiczny UZP · czas | 34,89 s | 59,33 s |

Wyłączenie samego ponownego OCR w bieżącym kodzie przywróciło wynik 0,88959 na zbiorze odłożonym. Z siedmiu prób dodatkowego OCR przyjęto trzy odczyty. Przywróciły prawidłową klasę po obrocie stron o 180°. Wszystkie sześć dokumentów spoza zakresu nadal dało pusty wynik. Publiczny korpus wymagał 13 dodatkowych prób i wykorzystał jeden ponowny odczyt. Oba zbiory przetworzono bez błędów.

Pomiar odbył się na Windows z Pythonem 3.13 i Tesseractem 5.5.3 z tessdata_fast. Użyto pięciu wątków dla zestawu odłożonego i sześciu dla danych UZP. Benchmark liczy zgodność dokładnej ścieżki i niepustej wartości JSON. [Metoda pomiaru](wyniki.md)

## Odtworzenie

~~~powershell
python -m validation.scan_cases .work/scan-validation --font C:/Windows/Fonts/arial.ttf
python -m o2j benchmark .work/scan-validation/holdout --engine rules --jobs 5 --report .work/holdout-candidate.json
python -m o2j benchmark .work/scan-validation/holdout --engine rules --jobs 5 --no-ocr-retry
~~~

Ostatnie polecenie wyłącza sam ponowny OCR w bieżącym kodzie. Wyniki pełnej wersji bazowej pochodzą z uruchomienia kodu z tagu v0.1.0-baseline na identycznych plikach wejściowych.
