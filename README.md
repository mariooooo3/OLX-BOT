# OLX Auto-Responder Bot

Bot Python care rulează 24/7, citește mesajele noi de pe OLX și răspunde
automat cu un LLM (Groq) pe baza unui catalog de produse local, plus un
dashboard web de administrare.

## Pornire rapidă (calculator nou, prima dată)

**Necesare înainte de a începe:**

| Unealtă | De unde | Observație |
|---|---|---|
| [Python 3.11+](https://www.python.org/downloads/) | python.org | Windows: bifează **"Add python.exe to PATH"** la instalare |
| [Node.js LTS](https://nodejs.org/) | nodejs.org | pentru interfața web (dashboard) |
| [Git](https://git-scm.com/downloads) | git-scm.com | ca să clonezi acest repo |

Nu ai nevoie de cont OLX sau cheie API înainte de instalare — le configurezi
în pasul 3.

```bash
git clone https://github.com/mariooooo3/OLX-BOT.git
cd OLX-BOT
```

**1. Instalează tot automat** (mediu Python, Chromium pentru Playwright,
interfața web):

- Windows: dublu-click pe `setup.bat` (sau `.\setup.bat` din terminal)
- Mac / Linux: `bash setup.sh`

Durează câteva minute (descarcă pachete + un Chromium). La final, scriptul
te întreabă de cheia Groq — vezi pasul 2.

**2. Cheia Groq (LLM-ul care scrie răspunsurile)**

Gratuită, se face în ~30 de secunde: intră pe
[console.groq.com/keys](https://console.groq.com/keys), creează un cont,
generează o cheie (începe cu `gsk_...`) și lipește-o când te întreabă
scriptul de instalare. Dacă ai sărit peste pas, o poți completa oricând
manual în fișierul `.env`, la linia `GROQ_API_KEY=`.

**3. Pornește aplicația**

- Windows: dublu-click pe `start.bat`
- Mac / Linux: `bash start.sh`

Se deschide automat dashboard-ul în browser la `http://localhost:8080`.

**4. Conectează-ți contul OLX**

În dashboard apasă **„Conectează cont OLX"**. Se deschide o fereastră reală
de Chrome — te loghezi cu **email-ul și parola ta de OLX** și rezolvi
sliderul CAPTCHA dacă apare. Fereastra se închide singură când login-ul e
confirmat. (Detalii la [Autentificare OLX](#autentificare-olx-o-singură-dată)
mai jos — de ce nu se poate automatiza complet.)

**5. Adaugă produsele tale**

Din dashboard, secțiunea „Produse" — botul răspunde pe baza catalogului de
acolo (titlu, preț, cuvinte cheie, FAQ).

**6. Apasă „Pornește botul"** din dashboard. Gata — răspunde automat la
mesajele noi.

> Fiecare calculator/prieten care clonează acest repo își conectează
> **propriul cont OLX** și **propria cheie Groq** — nu se partajează nimic
> din contul original. Datele (produse, conversații, sesiunea de login) rămân
> locale, pe calculatorul respectiv, și nu ajung în git (vezi `.gitignore`).

## Arhitectură

```
main.py (loop la 30-60 sec)
  └── browser_client.py → citește conversațiile noi (Playwright)
        └── message_handler.py → pentru fiecare mesaj nou:
              ├── product_matcher.py     → găsește produsul relevant (titlul anunțului OLX; fallback keywords)
              ├── prompt_builder.py      → construiește promptul
              ├── groq_adapter.py        → apelează LLM
              ├── response_formatter.py  → validează răspunsul (fallback la nevoie)
              └── browser_client.py      → trimite răspunsul (delay 3-8 sec)
                    └── json_adapter.py  → loghează conversația
```

`core/` depinde doar de interfețele abstracte din `adapters/*/base.py`.
La MVP2 se schimbă doar cele două linii din `config.py`
(`GroqAdapter` → `OllamaAdapter`, `JSONAdapter` → `DBAdapter`).

## Instalare manuală (dacă nu vrei să folosești setup.bat/setup.sh)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
playwright install chromium    # doar pentru rularea reală, nu pentru test.py
```

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux
```

Completează în `.env`:

| Variabilă | Descriere |
|---|---|
| `GROQ_API_KEY` | cheie de la https://console.groq.com/keys (singura obligatorie) |
| `POLL_INTERVAL_SECONDS` | intervalul de polling (default 45) |
| `LOG_LEVEL` | `INFO` sau `DEBUG` |
| `OLX_EMAIL` / `OLX_PASSWORD` | **nefolosite** — login-ul e manual, prin browser (vezi mai jos) |

## Test fără browser și fără cont OLX

```bash
python test.py
```

Rulează 3 mesaje simulate prin fluxul complet și printează răspunsurile.
- Cu `GROQ_API_KEY` setat → folosește Groq real.
- Fără cheie → folosește un LLM mock (funcționează complet offline).

Conversațiile se loghează în `data/conversations.json`. Șterge fișierul
dacă vrei să rulezi testul de la zero (conversațiile procesate se sar).

## Dashboard web (ui/)

Interfață de administrare (React + TanStack Start): dashboard cu status și
statistici, conversații, CRUD produse, setări.

```bash
# terminal 1 — API-ul botului (port 8000)
python server.py

# terminal 2 — UI-ul (port 8080)
cd ui
npm install
npm run dev
```

Apoi deschide http://localhost:8080. (Scriptul `start.bat` / `start.sh` face
exact asta automat.)

- Tot stratul de date al UI-ului e în `ui/src/lib/api.ts` → bate în
  `server.py` (FastAPI). URL-ul API se poate schimba prin `VITE_API_URL`.
- Butonul „Pornește botul" din dashboard rulează bucla de polling OLX
  într-un thread al serverului.
- Dacă nu ești conectat, dashboard-ul afișează butonul **„Conectează cont
  OLX"** care deschide fereastra de login (vezi mai jos) — nu e nevoie de
  terminal. După conectare, cardul arată „Cont OLX conectat" și apare
  butonul de pornire.
- Comutator **light / dark** în bara laterală (și în bara de sus pe mobil).
  Tema se reține în `localStorage`, fără flash la reîncărcare.
- Setările din UI se salvează în `data/settings.json` și se aplică la
  următorul start al botului (modelul) / următorul ciclu (intervalul).

## Autentificare OLX (o singură dată)

OLX protejează login-ul cu un **CAPTCHA anti-bot** (slider „Glisați spre
dreapta"). Login-ul automat headless nu este posibil (și nu încercăm să
ocolim protecția). De aceea folosim login manual o singură dată, apoi
sesiune persistentă. Două moduri, ambele identice ca efect:

- **Din dashboard:** apasă „Conectează cont OLX". Serverul lansează
  `login.py` și se deschide fereastra de browser. (Recomandat.)
- **Din terminal:** `python login.py`

- Se deschide o fereastră Chrome reală. Te loghezi tu (email + parolă +
  rezolvi sliderul CAPTCHA).
- Login-ul e confirmat prin API-ul OLX (`users/me` cu tokenul din cookie),
  fără navigare — vezi `adapters/olx/session_check.py`; fallback pe pagina
  `/myaccount/` dacă API-ul se schimbă vreodată.
- La confirmare se scrie markerul `olx_session.json` **în profilul
  contului** (cu numele și emailul contului OLX, afișate în dashboard),
  apoi fereastra se închide singură.
- Fiecare cont OLX are profilul lui persistent în `data/browser_profiles/`
  (registru în `data/accounts.json`); botul refolosește headless profilul
  contului activ. Conturile se schimbă din meniul „OLX Bot" (stânga sus)
  sau din cardul „Stare bot".
- Dacă sesiunea expiră, reconectează contul din dashboard (sau
  `python login.py --profile <profilul contului>`).

## Rulare reală

```bash
python main.py          # sau butonul „Pornește botul" din dashboard
```

- Refolosește sesiunea contului activ din `data/accounts.json` (același
  cont selectat în dashboard).
- Dacă nu ești logat, se oprește cu un mesaj clar care cere conectarea.
- Loguri în consolă și în `logs/bot.log` (rotire la 10 MB).

## Note

- Delay random 3–8 secunde înainte de fiecare trimitere (simulare comportament uman).
- Botul selectează explicit inbox-ul **Vânzări** și se oprește în siguranță
  dacă OLX nu îl poate confirma; nu răspunde conversațiilor de cumpărare.
- La fiecare poll verifică toate conversațiile necitite și primele 10
  conversații recente. Astfel recuperează și mesaje marcate accidental drept
  citite, fără să deschidă întreg istoricul.
- Un răspuns este `sent` numai după confirmarea trimiterii în browser;
  încercările `failed` sunt eligibile pentru retry la poll-ul următor.
- Selectorii OLX sunt centralizați în `SELECTORS` din
  `adapters/olx/browser_client.py` — dacă OLX își schimbă interfața,
  actualizează doar acolo.
- Răspunsurile invalide (goale, >1000 caractere, fraze de tip „Ca AI...")
  sunt înlocuite cu un mesaj fallback politicos.

## MVP2 — scalabilitate (implementat, opt-in din `.env`)

Tot MVP2 e scris și testat. Nu schimbă comportamentul implicit — se
activează prin variabile de mediu, **zero cod modificat** în `core/`.

### Ce s-a adăugat

| Componentă | Fișier | Activare |
|---|---|---|
| Stocare pe DB (SQLAlchemy) | `adapters/storage/db_adapter.py` | `STORAGE_BACKEND=db` |
| LLM local Ollama | `adapters/llm/ollama_adapter.py` | `LLM_BACKEND=ollama` |
| Coadă de joburi (`jobs`) | `adapters/storage/models.py` | `USE_QUEUE=true` |
| Worker separat | `worker.py` | `python worker.py` |
| Migrare JSON → DB | `migrate_json_to_db.py` | o singură dată |

Selecția adaptoarelor e centralizată în `config.py` (`build_llm` /
`build_storage`), condusă exclusiv de `.env`.

### Storage: SQLite acum, PostgreSQL prin schimbarea unui URL

```bash
STORAGE_BACKEND=db
DATABASE_URL=sqlite:///data/olxbot.db        # zero instalări, fișier local
```

Trecerea la PostgreSQL = schimbi doar URL-ul (și `pip install "psycopg[binary]"`):

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/olxbot
```

Codul rămâne neschimbat — SQLAlchemy vorbește identic cu ambele. Datele
existente se mută cu `python migrate_json_to_db.py`.

### Coadă + workeri (scalare)

Cu `STORAGE_BACKEND=db` și `USE_QUEUE=true`, fluxul se împarte:

```
server.py (producător + expeditor, are browserul)
  ├── citește mesaje noi OLX → enqueue job (tabel `jobs`)
  └── trimite răspunsurile 'done' generate de workeri

worker.py (unul sau mai mulți, fără browser)
  └── claim job → matcher → prompt → LLM → validare → 'done'
```

Scalezi rulând mai mulți workeri simultan (`claim` atomic cu
`FOR UPDATE SKIP LOCKED` pe Postgres). Ciclul de viață al unui job:
`pending → processing → done → sending → sent` (sau `failed`).

### LLM local (Ollama)

```bash
LLM_BACKEND=ollama
OLLAMA_MODEL=llama3.1:8b        # după `ollama pull llama3.1:8b`
```

`OllamaAdapter` vorbește direct cu API-ul HTTP (`/api/chat`) — nu instalează
niciun SDK până nu îl activezi.

### Test MVP2 (offline, fără browser/OLX/Groq)

```bash
python test_mvp2.py
```

Dovedește round-trip DB (inclusiv coloane JSON) și fluxul complet al cozii
(enqueue → worker → sender) cu un LLM mock, într-o bază SQLite temporară.
