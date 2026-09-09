# Mai multe conturi OLX, fiecare cu IP propriu (Docker)

## Problema pe care o rezolvă

Cu mai multe conturi OLX pornite din același dashboard, toate ies pe
internet cu **același IP** (al calculatorului tău). Sistemele anti-fraudă
ale OLX pot corela ușor conturi diferite care vin mereu de pe același IP și
le pot limita.

Soluția are trei bucăți, fiecare acoperind un tip diferit de semnal pe care
sistemele anti-fraudă îl pot folosi ca să coreleze conturile:

1. **Proxy per cont** (buton „Proxy" din panoul de conturi) — fiecare cont
   iese prin adresa lui de IP. Trebuie configurat de tine (nu are cum să fie
   automat — ai nevoie de un proxy/VPN real per cont).
2. **Amprentă de browser diferită per cont** — automat, fără nicio
   configurare. Fiecare profil de browser (deci fiecare cont) primește o
   combinație proprie de user-agent, rezoluție de ecran și placă video
   „raportată" — mereu aceeași pentru același cont (determinist, nu se
   schimbă la fiecare pornire), diferită între conturi. Se aplică automat
   oriunde rulează browserul contului: dashboard, container, fereastra de
   login manual. Nu ai nimic de făcut pentru asta.
3. **Container separat per cont** (acest document) — izolare și la nivel de
   proces, nu doar de rețea: un cont blocat/căzut nu afectează celelalte, îl
   poți reporni independent, poți limita resursele lui.

Punctele 1 și 2 funcționează și fără Docker (chiar și cu toate conturile ca
thread-uri în dashboard, ca până acum). Container-ul (punctul 3) e un pas în
plus, pentru izolare de proces — nu e obligatoriu ca să beneficiezi de IP
sau amprentă diferite.

## Ce se schimbă și ce rămâne la fel

- **Dashboard-ul (`start.bat`, `http://localhost:8080`) rămâne pe Windows,
  neschimbat.** Nu conține trafic către OLX — doar bucla de bot îl are.
- **Conturile pe care NU le muți în Docker continuă exact ca înainte** —
  thread în dashboard, comutator din UI.
- **Un cont mutat în Docker rulează într-un container separat**
  (`bot_worker.py`). Pornirea, oprirea și restart-ul se fac direct din
  dashboard (buton „Pornește în Docker" / „Oprește Docker" / „Repornește"
  în panoul de conturi) — la fel de simplu ca pentru un cont local. Merge și
  din linia de comandă (`docker compose ...`), dacă preferi.
- **Datele rămân în `data/`, pe disc**, montate ca volum în container —
  produsele, conversațiile și profilul de browser al contului sunt aceleași
  fișiere pe care le vede și dashboard-ul. Nu există nicio bază de date nouă
  de configurat.

## Pași

### 1. Pregătește Docker

Ai nevoie de [Docker Desktop](https://www.docker.com/products/docker-desktop/)
pornit. Verifică:

```bash
docker compose version
```

### 2. Conectează contul din dashboard, ca de obicei

Login-ul OLX (cu CAPTCHA) se face **întotdeauna** din dashboard, pe Windows —
nu din container (containerul rulează headless, fără fereastră). Deci:

1. Adaugă/conectează contul din dashboard, ca până acum.
2. Dacă vrei IP propriu, setează-i proxy-ul din panoul de conturi (buton
   „Proxy") **înainte** de login — sesiunea trebuie creată de pe același IP
   pe care va rula botul.
3. **Oprește botul acelui cont din dashboard** (comutatorul pe „oprit").
   Chromium nu acceptă două procese pe același profil — dacă rulează și în
   dashboard și în container, se blochează reciproc.

### 3. Pornește din dashboard

Din panoul de conturi (același loc unde ai configurat proxy-ul), fiecare
cont conectat are acum un buton **„Pornește în Docker"**. Un click:

1. oprește botul local al contului, dacă rula ca thread (Chromium nu
   acceptă două procese pe același profil);
2. generează/actualizează `docker-compose.yml` din `data/accounts.json`
   (fără să atingi tu vreun fișier);
3. construiește imaginea (poate dura câteva minute la prima rulare —
   progresul apare live în dashboard) și pornește containerul.

Când e pornit, butonul devine **„Oprește Docker"**, plus un buton de
**restart** (util după ce schimbi modelul LLM al contului din dashboard —
setările noi se aplică abia la următoarea pornire a containerului, nu din
mers). Eticheta „container Docker" apare lângă starea contului.

Dacă încerci să pornești din dashboard (ca thread local) un cont care
rulează deja într-un container, primești eroare 409 cu instrucțiunea
exactă — nu se lansează un al doilea proces peste același profil.

### 4. Alternativ, din linia de comandă

Dacă preferi terminalul (sau vrei să pornești mai multe conturi deodată
fără să dai click pe fiecare), poți face aceiași pași manual:

```bash
python generate_docker_compose.py   # genereaza docker-compose.yml, la fel ca butonul din UI
docker compose build
docker compose up -d                # toate conturile din fisier
docker compose up -d acc_429ab3     # doar un cont (numele serviciului = id-ul contului)
docker compose logs -f
docker compose stop acc_429ab3
docker compose down                 # opreste tot
```

Cele doua cai (dashboard si linia de comanda) folosesc exact acelasi
`docker-compose.yml` si acelasi mecanism de heartbeat — poti sa le
amesteci fara probleme (porneste un cont din UI, opreste-l din terminal
etc.).

> Daca vrei sa personalizezi un serviciu (resurse, VPN la nivel de
> container), nu edita `docker-compose.yml` direct — se pierde la
> regenerare (inclusiv la fiecare pornire din dashboard). Pune
> personalizarile intr-un `docker-compose.override.yml`; Docker Compose
> il aplica automat peste fisierul generat.

## De reținut

- **Fiecare cont trebuie reconectat manual din dashboard prima dată** —
  containerul nu poate face login (CAPTCHA), doar refolosește sesiunea deja
  creată.
- **Dacă schimbi setările contului din dashboard** (model LLM, interval de
  polling, informații vânzător), containerul le preia automat la următorul
  ciclu — citește din același `data/accounts/<id>/settings.json`.
- **Dacă schimbi proxy-ul unui cont** din dashboard, iar botul lui rulează
  deja (thread local sau container Docker), serverul îl repornește automat
  — proxy-ul nou se aplică imediat, nu trebuie repornit manual. Dacă
  preferi linia de comandă, `docker compose restart acc_1` face același
  lucru pentru varianta container.
- IP diferit (proxy) + amprentă de browser diferită (automat) reduc mult
  riscul de corelare, dar nu-l elimină 100%: rămân semnale pe care nu le
  controlăm din browser (ex. amprenta la nivel de rețea a proxy-ului
  însuși — TLS/TCP fingerprint — depinde de proxy-ul ales, nu de aplicație).
  Alege un IP de proxy geolocat coerent cu fusul orar românesc — un IP din
  altă țară e el însuși un semnal suspect, indiferent de amprenta browserului.
- Cu câteva conturi (2-5), șansa ca două să primească din întâmplare
  exact aceeași combinație de user-agent/rezoluție/placă video e mică
  (sub ~5%) — spațiul de combinații e generat separat pe fiecare
  componentă. Chiar și atunci, zgomotul de pe canvas tot diferă între ele.

## Optimizări la nivel de infrastructură Docker

`docker-compose.yml`-ul generat (automat sau manual, din `docker-compose.example.yml`)
folosește un tipar comun (`x-worker`, o ancoră YAML) pentru toate conturile:

- **O singură imagine, construită o dată** (`image: olx-bot-worker:latest`,
  aceeași pentru toate serviciile) — cu multe conturi, nu se mai repetă
  build-ul complet la fiecare cont; Docker refolosește cache-ul de layere.
- **Limite de resurse implicite** (`mem_limit`, `cpus`) — fiecare container
  rulează un Chromium headless complet; fără limită, un cont cu o pagină
  blocată poate epuiza RAM-ul mașinii și afecta celelalte conturi.
  Suprascrii implicitul din `.env`:
  ```
  OLX_BOT_MEM_LIMIT=1g
  OLX_BOT_CPUS=1.5
  ```
- **Healthcheck real** ([docker_healthcheck.py](../docker_healthcheck.py)) —
  verifică vârsta heartbeat-ului contului (nu doar dacă procesul e viu).
  `restart: unless-stopped` singur repornește un container doar când
  procesul chiar se termină (crapă); un browser Playwright *agățat* (pagină
  care nu mai răspunde niciodată) rămâne "pornit" la nesfârșit fără asta.
  O sesiune expirată (`running=false`, scrisă la timp de `bot_worker.py`)
  rămâne "healthy" — nu e o buclă blocată, doar așteaptă re-login din
  dashboard, deci nu declanșează restart.
- **Serviciu `autoheal`** — un singur container (`willfarrell/autoheal`,
  pornit automat o dată cu primul cont, via `depends_on`) care repornește
  automat orice container etichetat `autoheal=true` ajuns "unhealthy".
  **Atenție**: montează `/var/run/docker.sock`, ceea ce îi dă acces complet
  la Docker pe mașina respectivă (echivalent root la nivel de host) — e un
  tipar comun și o imagine minimală dedicată exact acestui scop, dar merită
  cunoscut înainte să pornești stack-ul. Dacă preferi să nu-l rulezi, șterge
  blocul `autoheal` și câmpul `depends_on` din `x-worker` într-un
  `docker-compose.override.yml` — restul funcționează identic, doar fără
  restart automat pe buclă blocată.

Regenerarea (`python generate_docker_compose.py --force` sau butonul din
dashboard) aplică automat toate cele de mai sus pentru orice cont nou.
