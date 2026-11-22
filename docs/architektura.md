# Architektura Odwołania2JSON

1. **PDF i OCR.** PDFium odczytuje warstwę tekstową. Tesseract z modelami pol i eng odczytuje obraz stron, których tekst jest zbyt krótki lub uszkodzony. Domyślnie aplikacja czyta do 12 stron od początku i dwie końcowe. Limit OCR to 5 stron na dokument i można go zmienić parametrem --ocr-pages. Skanowanie stron jest ograniczone czasowo. Wynik wskazuje wykorzystane strony.
2. **Klasyfikacja.** Wagi sygnałów z plików config/*.toml są sumowane dla pierwszych dwóch stron. Minimalny wynik i rozstrzygnięcie remisu pomagają odrzucać dokumenty bez wystarczających sygnałów. W trybie hybrydowym model rozstrzyga niejednoznaczne przypadki na podstawie opisów klas.
3. **Ekstrakcja.** Lokalne reguły rozpoznają role, etykiety, daty, identyfikatory oraz pierwszy zaskarżony zarzut. Opcjonalny model dostaje instrukcję właściwej klasy, schemat oraz ograniczony fragment treści PDF. W przypadku niedostępności modelu działa wynik reguł.
4. **Walidacja.** JSON Schema sprawdza kształt wyniku, daty i rodzaje identyfikatorów. Brak wartości jest reprezentowany przez null lub pustą listę zgodnie z konfiguracją. Numery kont są ciągami 26 cyfr. PESEL jako ciąg cyfr zachowuje zera wiodące i odpowiada publicznym referencjom. Schemat akceptuje również liczbę 11-cyfrową pokazaną w przykładzie UZP.
5. **Ślad.** Opcjonalna diagnostyka pokazuje klasę, punktację, źródło tekstu per strona, dopasowane cytaty, ostrzeżenia i czas. Fragmenty są dopasowaniami wartości do tekstu źródłowego. Pola wnioskowane lub silnie zniekształcone przez OCR mogą nie mieć dopasowanego fragmentu.
6. **Interfejs.** CLI odzwierciedla drzewo input w output, obsługuje wykonanie równoległe i zapis atomowy każdego wyniku. Lokalny interfejs używa tej samej usługi ekstrakcji, przechowuje przesłany PDF w pamięci na czas przetwarzania i umożliwia pobranie JSON z przeglądarki.

## Dodanie nowej klasy

1. Dodaj plik TOML do config z id, label, description, ścieżkami schema i prompt oraz progiem minimum_score. Dodaj jeden lub kilka sygnałów z wyrażeniem regularnym i wagą. Waga ujemna może obniżać wynik dla dokumentu, który tylko zawiera podobne słowa.
2. Zdefiniuj JSON Schema w config/schemas i instrukcję ekstrakcji w config/prompts. Opisz rolę każdego pola, format i warunki braku wartości. Deklaracja typu głównego to object.
3. Jeśli pola mają czytelne etykiety, dodaj opcjonalną sekcję fields do konfiguracji. Każde wyrażenie ma jedną grupę przechwytującą. Klucz z kropkami określa ścieżkę przez obiekty JSON, np. kontrola.numer. Typ string pozostaje tekstem, integer i number są konwertowane na liczby, a format date jest zapisywany w ISO. Złożone tablice i semantyczne relacje można obsłużyć skonfigurowanym modelem.
4. Dodaj przykładowe dokumenty do katalogu testowego i uruchom CLI z --config. Aplikacja odkrywa pliki TOML przy starcie i udostępnia klasy automatycznie w GUI.

~~~toml
id = "protokol"
label = "Protokół kontroli"
description = "Dokument zawierający podsumowanie przeprowadzonej kontroli"
schema = "schemas/protokol.json"
prompt = "prompts/protokol.md"
minimum_score = 8

[[signals]]
pattern = '^PROTOKÓŁ KONTROLI$'
weight = 8

[fields]
"kontrola.numer" = '^Numer protokołu:\s*(.+)$'
~~~

Dodając pole do istniejącej klasy, zaktualizuj jej schemat i prompt. Gdy etykieta jest stabilna, przypisz pole również w sekcji fields. Test test_new_class_and_field_need_configuration_only sprawdza całą ścieżkę dla nowej klasy skonfigurowanej bez zmian w silniku.

## Komponenty zewnętrzne

Python na licencji PSF, PDFium i pypdfium2 na licencjach rodziny BSD i Apache, Pillow na HPND, jsonschema na MIT oraz Tesseract i dane językowe na Apache 2.0. Techniczny opis modeli i dostawców jest w README. Dokumenty oraz referencje UZP pobierane są oddzielnie na potrzeby weryfikacji. [Repozytorium UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026) · [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) · [Pillow](https://github.com/python-pillow/Pillow) · [jsonschema](https://github.com/python-jsonschema/jsonschema) · [Tesseract](https://github.com/tesseract-ocr/tesseract)
