# Wyniki benchmarku wersji v0.1.0-baseline

Porównanie z późniejszą wersją znajduje się w [walidacji ponownego OCR](ocr-validation.md).

Pomiar lokalny na publicznym korpusie UZP z commita eadffbce531eeac876d0f7e62c1cc6e857b05796. Korpus zawiera 226 PDF, w tym 30 plików w katalogu skany i 16 dokumentów spoza zakresu. Pomiar wykonano na Windows z Pythonem 3.13.17, Tesseractem 5.5.3 i sześcioma pracownikami CLI, w trybie rules na CPU. [Korpus UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796/dane)

| Metryka | Wartość z tessdata_fast |
| --- | ---: |
| Mikro-F1 pól | 0,98865 |
| Precyzja | 0,99141 |
| Czułość | 0,98590 |
| Mikro-F1 skanów | 0,91240 |
| Mikro-F1 pozostałych PDF | 1,00000 |
| Trafność klasyfikacji | 226 / 226 |
| Pełne dopasowanie JSON | 209 / 226 |
| Błędy przetwarzania | 0 |
| Czas całej partii | 40,61 s |

W benchmarku pole trafia do licznika TP, gdy niepusta wartość z wyniku odpowiada dokładnie ścieżce i wartości w JSON referencyjnym. Nadmiarowa wartość jest FP, a nieodtworzona wartość jest FN. Niezgodna wartość w tym samym polu daje FP i FN. Mikro-F1 agreguje te liczniki z całej partii. UZP stosuje odrębną ocenę na zbiorze niejawnym.

Porównanie polskich danych językowych Tesseract pokazało mikro-F1 0,98736 ogółem i 0,90248 na skanach dla tessdata_best. Profil tessdata_fast jest zalecany dla tej konfiguracji, ponieważ dał wyższy F1 przy krótszym czasie. Pozostałe różnice na skanach dotyczą przede wszystkim odczytów OCR, np. zniekształconych nazw lub tytułów przelewów. Wyjściowy numer rachunku jest normalizowany do 26 cyfr także w dwóch skanach, których publiczna referencja zachowała prefiks PL. [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) · [tessdata_best](https://github.com/tesseract-ocr/tessdata_best)

Sprawdzono 12 testów automatycznych, odczyt przykładowego drzewa konkursowego, pusty wynik dla dokumentu spoza zakresu oraz działanie podglądu, stronicowania i pobierania JSON w Edge. Pomiar jakości dotyczy lokalnych reguł i OCR. Weryfikacja trybu hybrydowego na rzeczywistym koncie dostawcy wymaga klucza API.
