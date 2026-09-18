# OIL razvoj

Objedinjeni kontekst razvoja, sastavljen 18. rujna 2026. iz 11 lokalnih
korisničkih razgovora povezanih s `/var/www/oil`, postojećih razvojnih bilježaka
i ciljane provjere koda. Ovo je sažetak za nastavak rada, a ne doslovni prijepis
ili spajanje razgovora u Codex sučelju. Izvorni razgovori ostaju sačuvani.

## Polazište za nastavak

OIL znači **Open Instrument Lab**: Django aplikacija za upravljanje
laboratorijskim instrumentima, mjerenjima i dugotrajnim zadacima. Autor je
Elvis Baketa; projekt koristi AGPL-3.0-or-later.

Lokalno provjereno pri sastavljanju dokumenta:

- Aktivna grana: `testing`.
- HEAD: `e27099f` — `Improve responsive DMM panel display`.
- Najnovija dostupna lokalna oznaka: `v0.0.9`.
- Postoje brojne necommitane promjene panela, drivera, zadataka i migracija.
  Starija tvrdnja iz razgovora da je radno stablo čisto više ne vrijedi.
- Stanje udaljenog repozitorija i objavljenih izdanja nije ponovno provjereno.
- `DEVELOPMENT_HANDOFF.md` sadržava povijesni presjek i dopunjen je sažetkom
  novijih necommit-anih promjena; `CHANGELOG.md` ih vodi pod `Unreleased`.

Posljednja razvojna izmjena iz razgovora odnosi se na temperaturna očitanja:
DS1820/DS18S20 zaokružuje se na **0,5 °C**, a DS18B20 na **0,1 °C**.
Zaokruživanje postoji u driveru; tablica, graf i CSV koriste jednu decimalu.
Izbor rezolucije DS18B20 od 9 do 12 bita ostaje dostupan.

## Dogovori koje treba zadržati

- Razgovor s korisnikom voditi na hrvatskom. Kod, komentari u kodu i tekst
  aplikacijskog sučelja trebaju biti na engleskom.
- Driver opisuje mogućnosti stvarnog instrumenta; ne pretpostavljati podršku
  za naredbe, raspone ili funkcije prema drugom modelu.
- Pri otvaranju fizičkog DMM panela očitati stanje instrumenta i prilagoditi
  sučelje. Ne mijenjati funkciju ili mjerno područje samo radi otvaranja panela.
- Broj znamenki mora biti dosljedan u vrijednosti, statistici, tablici, grafu,
  oznakama osi, tooltipu i CSV-u. Format prikaza nije isto što i razlučivost senzora.
- Korisnik bira primarnu ili sekundarnu os grafikona; temperaturu ne prebacivati
  samovoljno na sekundarnu os.
- Razlikovati identifikaciju `*IDN?`, automatizirane testove i fizičko testiranje.
  Ne navoditi izmišljenu adresu uređaja kao potvrđeni port.
- Dugotrajni zadaci trebaju raditi u pozadini i nakon zatvaranja preglednika;
  restart aplikacije zahtijeva oporavak iz spremljenog stanja.
- Razvoj se vodi na `testing`; izdavanje, slanje na GitHub i spajanje u `main`
  zasebni su koraci. Ovaj dokument nije nova objava.

## Razvojna povijest

| Razdoblje/verzija | Objedinjeni rezultat razgovora |
| --- | --- |
| 0.0.1 | Naziv OIL, licenca i autorstvo, prijava/odjava, profili i teme, lokalni Bootstrap, MkDocs, početni deployment i changelog. |
| 0.0.2–0.0.3 | Dashboard, inventar, Agilent i Keysight driveri, uređivanje i identifikacija, ConnectionManager, spremljena mjerenja, Online/Reachable statusi. |
| 0.0.4 | Single, Continuous i Loop mjerenja, rezultati uživo, jedna veza za seriju očitanja, dorade Agilent serijske komunikacije i vremena čekanja. |
| 0.0.5 | MeasurementRun, DriverRegistry, capability sustav i Mock driver; konfiguracija tajni, DEBUG-a i hostova kroz okruženje. |
| 0.0.6–0.0.7 | Podjela Django aplikacija, zajednički transporti, JSON API, CSV izvoz, prenosiv installer servisa i zajedničko učitavanje `.env`. |
| 0.0.8 | Trajni Tasks workspace, Mock PSU, konfiguracija više instrumenata, fixed/sweep/cycle programi i korisničke postavke navigacije. |
| Razgovori oko 0.0.9 i nakon nje | Fizički RND PSU, trigger takt, readback, paralelna očitanja, trajanje akvizicije, grafovi, oporavak zadataka, DMM paneli, BTDL temperaturni i BMx280 okolišni driveri, izbor senzora i optimizacija većih skupova podataka. |

Posljednji redak opisuje razvojno razdoblje, ne tvrdi da su sve navedene
funkcionalnosti sadržane baš u oznaci `v0.0.9`.

## Instrumenti i driveri

U `drivers/__init__.py` trenutačno je registrirano deset drivera:

| Ključ | Namjena |
| --- | --- |
| `agilent_34401a` | Agilent 34401A, Serial/FTDI; povijesno važna konfiguracija 8N2. |
| `keysight_34461a` | Keysight 34461A, Linux USBTMC. |
| `rnd_ka3005p` | RND Lab 320-KA3005P, fizičko laboratorijsko napajanje. |
| `btdl_ntc` | Baketa BTDL-NTC; dorada prema firmwareu 1.2.0. |
| `btdl_ds18b20` | Baketa BTDL-DS18B20; zasebne funkcije za DS1820/DS18S20 i DS18B20. |
| `btdl_bmx280` | Baketa BTDL-BMx280; otkrivanje BMP280/BME280 senzora na kanalima 1 i 2 te temperatura, vlaga i tlak. |
| `rpi_cpu_temperature` | Temperatura procesora Raspberry Pija. |
| `mock-dmm` | Simulirani multimetar. |
| `mock_dc_power_supply` | Simulirano DC napajanje. |
| `mock_rnd_320_3005p` | Simulirano RND napajanje. |

Administrator uređuje inventar i testira konfiguraciju prije spremanja novog
instrumenta. Obični korisnik ima pregled informacija i korištenje instrumenata
u dopuštenim mjernim postupcima. Adresa pripada instrumentu, ne općem opisu drivera.

BTDL-NTC je u razgovoru usklađen s protokolom 19200 baud, 8N1, LF,
identifikacijom, mjerenjem, resetom i SCPI redom pogrešaka. Nevaljani rezultat
`9.9E37` obrađuje se kao pogreška, a ne temperatura. Prikaz je jedna decimala.

BTDL-DS18B20 podržava izbor funkcije `temperature_ds1820` ili
`temperature_ds18b20`, skeniranje, broj senzora, ROM adrese i rezoluciju
DS18B20 od 9 do 12 bita. Najnovije pravilo zaokruživanja zamjenjuje raniji
dogovor o prikazu najviše dvije decimale. Raspberry Pi temperatura koristi dvije.

BTDL-BMx280 pri otvaranju konfiguracije zadatka očitava tipove senzora na
adresama `0x76` i `0x77`. BMP280 nudi temperaturu i tlak, a BME280 dodatno
vlagu. Korisnik bira koje će vrijednosti zapisivati; unutarnji driver šalje
jedan `READ?` po triggeru i iz zajedničkog odgovora izdvaja odabrane vrijednosti.

## Zadaci, grafovi i izvoz

Prema razgovorima implementirani su Single, Continuous i Loop zadaci,
spremljene konfiguracije, pozadinsko izvršavanje, Stop, označavanje zaustavljenog
zadatka kao Completed, brisanje neaktivnih vlastitih zadataka i ponovno pokretanje
neuspjelih zadataka.

Trigger ima podesiv vremenski takt; dodani su početna odgoda, proteklo vrijeme,
Acquisition time i paralelno očitavanje neovisnih instrumenata. Ako akvizicija
traje dulje od traženog intervala, sam odabir intervala ne jamči tu brzinu.

PSU zadaci imaju odvojene zadane i očitane vrijednosti, opcionalni readback,
pripremu prvog setpointa prije uključivanja izlaza i završno čišćenje.
Konačni sweep ne treba se ponovno pokretati samo zato što je zadatak Continuous.
Za RND se prikaz napona usklađuje s korakom 0,01 V.

Grafovi imaju vremenske raspone, tooltip i do pet neovisnih Y-osi. Svaka
odabrana vrijednost može se dodijeliti osi `Primary`, `Secondary`, `Axis 3`,
`Axis 4` ili `Axis 5`. U razgovoru je zatraženo
uklanjanje ograničenja broja točaka, ali aktualni `tasks/views.py` i dalje
reducira skup na najviše približno 1000 odabranih indeksa. To je otvoreno
neslaganje zahtjeva i implementacije koje treba riješiti zasebno.

Novije optimizacije potvrđene u kodu:

- `AutomationTask.sample_count` izbjegava ponovno prebrojavanje svih uzoraka
  pri otvaranju popisa; pripadaju migracija `tasks.0012` i signali.
- CSV koristi `.iterator(chunk_size=2000)` umjesto učitavanja cijelog zadatka.
- Temperaturna preciznost usklađena je kroz prikaz i CSV.
- Serijski transport za brze kontrolere provjerava odgovor svakih 5 ms; to je
  samo čekanje odgovora i ne pokreće dodatne trigere.

Povijesna mjerenja iz razgovora: upit popisa zadataka ubrzan je s približno
1,96 s na 0,025 s; CSV za ADR1399 Test 35 imao je oko 343 tisuće uzoraka.
To nisu nova mjerenja izvršena tijekom sastavljanja ovog sažetka.

## DMM paneli

Razgovori bilježe očitanje funkcije, raspona i integracijskih postavki pri
otvaranju, prikaz vrijednosti i statistike, graf, ručno i automatsko okidanje,
te prikaz podataka zadatka koji već koristi instrument.

Prvi panel preuzima kontrolu; dodatni prozori koriste read-only prikaz.
Vlasništvo i posljednje stanje čuvaju se u bazi. Kontrolni panel komunicira
s instrumentom; dodatni panel ne bi smio neovisno slati iste naredbe.

Posljednji sažetak rada na Agilentu navodi:

- Zasebne gumbe `4½`, `5½`, `6½`, `Fast` i `Slow`.
- SCPI konzolu s rednim brojevima naredbi, oznaku Remote i gumb `CLS`.
- Usklađivanje jedinica, vodećih nula i broja znamenki; dodatnu znamenku u `6½ Slow`.
- Timeout očitanja do 10 sekundi i odgodu od 3 sekunde nakon sporog očitanja.
- Početno čekanje 1 sekunde pri otvaranju, odnosno 5 sekundi pri refreshu,
  radi dovršetka starog očitanja i oslobađanja veze.

To su posljednji opisani popravci, ne potvrda da je fizičko testiranje svih
kombinacija završeno. Ranije jednostavno poistovjećivanje broja znamenki
i NPLC-a bilo je više puta korigirano; stare tablice ne koristiti kao specifikaciju.

## Otvorena pitanja za nastavak

1. **Oporavak nakon restarta:** posljednja prijava za ADR1399 Test 33 opisuje
   uspješno pronalaženje zadatka, zatim pad na USBTMC pisanju prema Keysightu.
   Predloženo čekanje i ponavljanje povezivanja nije potvrđeno kao dovršeno.
   Postojeći `recover_active_tasks()` pokreće Pending/Running zadatke; samo
   postojanje te metode ne znači da je uređaj spreman nakon restarta.
2. **Agilent 6½ Slow:** potvrditi ponašanje kod otvaranja, ponovljenog refresha,
   promjene funkcije i izlaska iz panela na fizičkom instrumentu.
3. **Graf velikih zadataka:** razriješiti zahtjev za svim točkama i postojeću
   redukciju na približno 1000 indeksa.
4. **Konsolidacija izdanja:** pregledati necommitane promjene i migracije,
   uskladiti changelog, provjeriti testove i tek zatim pripremati sljedeće izdanje.
5. **Povijesni prijenos baze s laptopa:** postoji plan remapiranja korisnika,
   instrumenata i zadataka, ali kratki razgovor o preuzimanju konteksta nije
   dokaz dovršenog prijenosa. Ne ponavljati uvoz bez provjere stanja.
6. **Ranije odgođene ideje:** automatska provjera dostupnosti instrumenata na
   Dashboardu i zaseban Power Supply Accuracy test nisu ovdje potvrđeni kao dovršeni.

## Mapa koda i provjere

| Područje | Glavne datoteke |
| --- | --- |
| Izvršavanje i oporavak | `tasks/runner.py`, `tasks/apps.py` |
| Status, graf, formatiranje, CSV | `tasks/views.py` |
| Modeli i brojač uzoraka | `tasks/models.py`, `tasks/signals.py`, `tasks/migrations/` |
| Obrazac i prikaz zadataka | `tasks/static/tasks/js/task_tabs.js`, `tasks/templates/tasks/task_list.html` |
| DMM panel | `dmm_panel/views.py`, `dmm_panel/models.py`, `dmm_panel/static/dmm_panel/panel.js` |
| Komunikacija i driveri | `services/connection_manager.py`, `drivers/` |
| Inventar i izbor drivera | `main/models.py`, `main/migrations/` |

Pri sljedećoj izmjeni odabrati provjere prema zahvaćenom području. Uobičajene
naredbe projekta su `manage.py check`, `manage.py makemigrations --check --dry-run`
i ciljani Django testovi kroz `.venv/bin/python`. JavaScript provjera zahtijeva
dostupan Node. Tijekom objedinjavanja nije pokretan aplikacijski servis,
migracija, mjerenje na instrumentima ni testni paket. Raniji brojevi prolaznih
testova iz razgovora ne predstavljaju potvrdu cijelog današnjeg radnog stabla.

## Izvori razgovora

Popis ispod omogućuje pronalaženje izvorne lokalne sesije. Redoslijed je prema
nastanku razgovora; pojedini razgovori nastavljani su mnogo kasnije. Automatske
interne sesije nisu uključene. Lozinke, tokeni i sadržaj privatnih konfiguracija
nisu preneseni u sažetak.

1. **Analiziraj run.sh datoteku**  
   Sesija: `019f9e26-d2cc-7173-8c09-f0fc31989964`

2. **Mozemo li ovdije i,plementirati AGPLv3?**  
   Sesija: `019f9e4e-58d6-7aa3-8cca-ae216375a5a1`

3. **MOzemo li sad u ovaj nas projekt OIL dodati changelog**  
   Sesija: `019f9eca-9e99-7582-a34f-f3fafe2f5ccb`

4. **Ajmo dalje sad smo na verziki 0.0.4. Reci mi imamo li kakve sigurnosne propuste i jesmo li ih objavili na github?**  
   Sesija: `019fa41e-636f-7da0-bafa-b81c82524dba`

5. **Dodaj razgovor iz developmenta**  
   Sesija: `019fb3d8-85ae-7021-a90c-33a26d71b7af`

6. **Uredi formu novog instrumenta**  
   Sesija: `019fb3fb-9022-76a1-9257-92e1e9e1d0ea`

7. **Pogledaj molim te sto se sad dogadja sa Taskom**  
   Sesija: `019fb432-7c09-7262-89f4-c95511a01e57`

8. **Pregled implementacija do 0.0.8**  
   Sesija: `019fb8ac-7fcf-74e3-8372-83169ee9179a`

9. **Ajmo dalje prema verziji 0.0.9?**  
   Sesija: `019fb8ae-518c-7731-9e76-d2bb8ad12665`

10. **Evo me na serveru znas li gdje smo stali?**  
   Sesija: `01a02e60-e858-7412-930e-eb1a0b125728`

11. **Koji su sve razgovori povezani sa ovim projektom**  
   Sesija: `01a0b4f1-42a7-72f0-aa62-d8344fb905aa`
