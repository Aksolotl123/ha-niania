# Niania — Philips Avent Baby Monitor w Home Assistant

Integracja HACS dla niań Philips Avent obsługiwanych przez aplikację **Philips Avent Baby Monitor+**
(kamery Tuya IPC: SCD923, SCD973, SCD951, SCD953/26, SCD643/26, SCD971; SCD921 — wideo bywa niestabilne).

To fork integracji [thekoma/aventproxy](https://github.com/thekoma/aventproxy) (licencja MIT) z jedną
istotną zmianą: **klucze Tuya aplikacji nie są zaszyte w kodzie** — podaje się je raz w konfiguracji.
Do tego polskie tłumaczenie kreatora konfiguracji.

## Co daje

- kamera na żywo (1080p H.264, przez mostek WebRTC→RTSP),
- temperatura w pokoju,
- lampka nocna (włącz/wyłącz, jasność, timer),
- kołysanki (play/pauza/następna/poprzednia, utwór, głośność, timer),
- detekcja ruchu i dźwięku (przełączniki + `binary_sensor` do automatyzacji),
- tryb prywatności, opcjonalnie dźwięk dwukierunkowy.
- **SenseIQ (nowość w tym forku):** oddech na minutę, obecność dziecka w łóżeczku, ruch na żywo,
  faza snu (sen lekki / sen głęboki / ruch / poza łóżeczkiem — jak w aplikacji Philips), czas faktycznego snu i „w łóżeczku od”. Kamera wysyła te dane
  lokalnie przez LAN (DPS 3 i 4), więc działają tylko przy połączeniu LAN z nianią. Opis formatu: `senseiq.py`.

„Motion Detected” to alarm ruchu z kamery (z opóźnieniem po stronie kamery i podtrzymaniem 30 s) —
nadaje się do powiadomień. „Moving” to ruch na żywo z SenseIQ, odświeżany co kilka sekund.

## Instalacja

Potrzebne są **dwa elementy** — integracja (to repo) i dodatek z mostkiem wideo.

1. **Integracja (HACS):** HACS → ⋮ → *Custom repositories* → `https://github.com/Aksolotl123/ha-niania`,
   kategoria *Integration* → pobierz „Niania (Philips Avent Baby Monitor)” → zrestartuj Home Assistant.
2. **Dodatek z mostkiem wideo:** Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → *Repozytoria* →
   `https://github.com/thekoma/aventproxy` → zainstaluj **Philips Avent WebRTC Bridge (Addon)** (kanał stable)
   i uruchom go. Wersja dodatku powinna odpowiadać wersji integracji (`manifest.json` → `version`).
   Bez dodatku działają czujniki i przełączniki, ale nie obraz.
3. **Konfiguracja:** Ustawienia → Urządzenia i usługi → *Dodaj integrację* → „Philips Avent Baby Monitor”:
   1. **Klucze aplikacji** (tylko przy pierwszym koncie) — patrz niżej,
   2. **e-mail, hasło i kraj** konta z aplikacji Baby Monitor+,
   3. **kod weryfikacyjny** z maila.

Hasło nie jest zapisywane — przy wygaśnięciu sesji integracja poprosi o ponowne logowanie.

## Klucze aplikacji

Aplikacja Philips Avent Baby Monitor+ rozmawia z chmurą Tuya, a każde żądanie musi być podpisane kluczami
tej aplikacji (tymi samymi dla wszystkich użytkowników danej wersji APK). Integracja potrzebuje trzech wartości:

| Pole | Wygląd |
|---|---|
| Klucz aplikacji (clientId) | 20 liter i cyfr |
| Klucz podpisu (signing key) | długi ciąg zaczynający się od `com.philips.ph.babymonitorplus_` |
| Klucz kanału (chKey) | 8 znaków szesnastkowych |

To repo jest publiczne, więc tych wartości tu nie ma. Można je odczytać z pliku `const.py` w repozytorium
upstream ([thekoma/aventproxy](https://github.com/thekoma/aventproxy), stałe `TUYA_APP_KEY`, `TUYA_SIGNING_KEY`,
`TUYA_CH_KEY`) albo samodzielnie odzyskać z APK aplikacji. Są przechowywane w lokalnym wpisie konfiguracji
Home Assistant i ukrywane w diagnostyce.

Jeśli Philips zmieni klucze w nowej wersji aplikacji, logowanie zacznie zwracać błąd podpisu — wtedy usuń
integrację i dodaj ją ponownie z nowymi kluczami.

## Testy

```sh
pip install pytest pycryptodome aiohttp tinytuya
pytest
```

Test wektora podpisu (`test_known_vector`) uruchamia się tylko z prawdziwymi kluczami w zmiennych
`AVENT_APP_KEY`, `AVENT_SIGNING_KEY`, `AVENT_CH_KEY`; bez nich jest pomijany.

## Podziękowania

Cała praca nad protokołem (logowanie Tuya, MQTT, mostek WebRTC) pochodzi z
[thekoma/aventproxy](https://github.com/thekoma/aventproxy). Szczegóły techniczne: `WHITEPAPER.md` w tamtym repo.
