# StudyHub

StudyHub to desktopowy prototyp aplikacji edukacyjnej napisany w PyQt6. Projekt jest pół-prototypem – skupia się na spójnym interfejsie i integracji głównych modułów, bez pełnego wdrożenia produkcyjnego. Aktualnie korzysta z Supabase (SQL + Storage) dla logowania, kalendarza i załączników.

## Przegląd funkcjonalności

- **Poczta** – wspólny interfejs dla Gmail, Microsoft 365/Outlook oraz IMAP/SMTP. Logika providerów: `core/mail.py`, UI: `ui/mail_view.py`. (Persystencja w Supabase + załączniki mailowe są planowane w kolejnym kroku.)
- **Kalendarz** – import ICS (także z URL), kolorystyka, szybki import bez duplikatów, zapis/soft-delete w Supabase, cleanup starych zdarzeń (`core/calendar.py`, `data/calendar_persistence.py`, `ui/calendar_view.py`).
- **Logowanie** – ekran logowania (username + hasło, hash w Supabase) i zapis tokenu lokalnie (`data/user_credentials.json`); overlay w `ui/login_overlay.py`.
- **Notatki i panel startowy** – lekkie widoki prototypowe (w `core/notes.py` znajduje się instrukcja podpięcia Supabase dla notatek).
- **Ustawienia** – persystencja preferencji w `data/settings.json` zarządzana przez `core/settings.py`.

## Stos technologiczny

- PyQt6 – UI.
- google-auth / google-api-python-client – Gmail API.
- MSAL – logowanie Microsoft 365.
- imap-tools + smtplib – IMAP/SMTP.
- icalendar – import ICS.
- supabase – persystencja SQL/Storage.
- bcrypt – hashowanie haseł.

## Struktura projektu (wybrane)

```
core/
  mail.py          # providerzy poczty
  calendar.py      # logika kalendarza + import ICS
  settings.py      # preferencje użytkownika
  notes.py         # instrukcja integracji Supabase dla notatek
ui/
  mail_view.py     # widok poczty
  calendar_view.py # widok kalendarza
  login_overlay.py # ekran logowania
  main_window.py   # główne okno
data/              # ustawienia, pliki, migracje Supabase
.env/              # lokalne sekrety (ignorowane w git)
```

## Uruchomienie developerskie

```bash
pip install -r requirements.txt
python main.py
```

Aplikacja zapisuje lokalne dane w `.env/` (np. tokeny poczty) oraz `data/user_credentials.json` (token Supabase). Katalog `.env/` jest ignorowany przez Git.

## Konfiguracja Supabase (skrót)

1) `.env/local.env`:
```
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...   # lub legacy anon dla dev
```
2) Uruchom migracje w Supabase SQL Editor: `data/supabase_migration.sql` (użytkownicy, kalendarz, kolumny deleted_at itp.).
3) Buckety Storage: `attachments` (notatki/załączniki), `mail_attachments` (załączniki mailowe – planowane).
4) Logowanie: pierwszy ekran rejestruje/loguje użytkownika (username + hasło), zapisuje dane lokalnie; sesja jest odświeżana do tygodnia.
5) Kalendarz: zapis/odczyt w Supabase, import ICS/URL bez duplikatów (czyszczenie źródła, upsert wsadowy), soft-delete + automatyczny cleanup (ukrywanie zdarzeń z przeszłości, twarde usunięcie po 7 dniach).
6) Notatki: patrz komentarz w `core/notes.py` – następny krok integracji.

## Droga rozwoju

- Poczta: zapis metadanych i załączników w Supabase (Storage + tabela mail_attachments), mark read/soft-delete, cleanup.
- Kalendarz: ewentualna dwukierunkowa synchronizacja i udziały.
- Notatki: podpięcie do Supabase (tekst + załączniki).
- Testy providerów i konfiguratora poczty.
- Refaktoryzacja UI i pakiet instalacyjny.
