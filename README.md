# OLX Auto-Responder Bot — Instalare

## Ce îți trebuie înainte de a începe

| Unealtă | De unde | Observație |
|---|---|---|
| [Python 3.11+](https://www.python.org/downloads/) | python.org | Windows: bifează **"Add python.exe to PATH"** la instalare |
| [Node.js LTS](https://nodejs.org/) | nodejs.org | pentru interfața web (dashboard) |
| [Git](https://git-scm.com/downloads) | git-scm.com | ca să clonezi acest repo |

Nu ai nevoie de cont OLX sau cheie API înainte — le configurezi în timpul instalării.

---

## Windows

Deschide `cmd` sau `PowerShell`:

```bat
git clone https://github.com/mariooooo3/OLX-BOT.git
cd OLX-BOT
setup.bat
```

`setup.bat` instalează automat tot ce trebuie (mediul Python, Chromium,
interfața web) și la final te întreabă de **cheia Groq**:

- gratuită, în ~30 de secunde: [console.groq.com/keys](https://console.groq.com/keys)
- lipește cheia (`gsk_...`) când te întreabă scriptul
- dacă sari peste pas, o poți completa oricând manual în fișierul `.env`, la linia `GROQ_API_KEY=`

După ce instalarea s-a terminat, pornește aplicația:

```bat
start.bat
```

(sau dublu-click pe `start.bat` din Explorer). Se deschide automat
dashboard-ul în browser la `http://localhost:8080`.

---

## Mac / Linux

Deschide `Terminal`:

```bash
git clone https://github.com/mariooooo3/OLX-BOT.git
cd OLX-BOT
bash setup.sh
```

`setup.sh` instalează automat tot ce trebuie (mediul Python, Chromium,
interfața web) și la final te întreabă de **cheia Groq**:

- gratuită, în ~30 de secunde: [console.groq.com/keys](https://console.groq.com/keys)
- lipește cheia (`gsk_...`) când te întreabă scriptul
- dacă sari peste pas, o poți completa oricând manual în fișierul `.env`, la linia `GROQ_API_KEY=`

După ce instalarea s-a terminat, pornește aplicația:

```bash
bash start.sh
```

Se deschide automat dashboard-ul în browser la `http://localhost:8080`.

---

## După pornire (identic pe orice sistem)

1. În dashboard apasă **„Conectează cont OLX"**. Se deschide o fereastră
   reală de Chrome — te loghezi cu **email-ul și parola ta de OLX** și
   rezolvi sliderul CAPTCHA dacă apare. Fereastra se închide singură când
   login-ul e confirmat.
2. Din dashboard, secțiunea **„Produse"** — adaugă catalogul tău (titlu,
   preț, cuvinte cheie, FAQ). Botul răspunde pe baza lui.
3. Apasă **„Pornește botul"**. Gata — răspunde automat la mesajele noi.

> Fiecare calculator/prieten care clonează acest repo își conectează
> **propriul cont OLX** și **propria cheie Groq** — nimic din contul
> original nu se partajează. Datele (produse, conversații, sesiunea de
> login) rămân locale pe calculatorul respectiv și nu ajung pe git.

## Mai multe conturi, fiecare cu IP propriu (proxy)

### De ce ai nevoie de asta

Dacă rulezi mai multe conturi OLX pe același calculator, toate ies pe
internet cu **același IP** — al mașinii tale. Sistemele anti-fraudă ale OLX
pot corela ușor conturi diferite care vin mereu de pe același IP și le pot
limita sau bloca. Soluția: fiecare cont iese pe **propriul IP**, printr-un
proxy dedicat lui.

### Ce se automatizează singur (nu ai nimic de făcut)

- **Amprenta de browser** — fiecare cont primește automat propriul
  user-agent, rezoluție de ecran și placă video „raportată", mereu aceeași
  pentru același cont, diferită față de celelalte conturi. Se aplică oriunde
  rulează botul (dashboard, fereastra de login).
- **Aplicarea proxy-ului** — odată ce ai lipit adresa în dashboard, botul
  **se repornește automat** și preia noul proxy imediat. Nu trebuie să
  opreşti/porneşti nimic manual.

### Ce trebuie să faci tu, pas cu pas

1. **Cumpără/obține un proxy** (SOCKS5 sau HTTP) pentru fiecare cont OLX pe
   care vrei să-l izolezi — de la un furnizor de proxy dedicat (nu un VPN
   obișnuit de tip NordVPN; ai nevoie de o adresă `host:port` + user/parolă,
   gândită pentru automatizare, nu pentru un singur utilizator uman).
2. În dashboard, din panoul de conturi, apasă **„Proxy"** pe contul dorit și
   completează adresa (`socks5://host:port` sau `http://host:port`) +
   utilizator/parolă, dacă proxy-ul le cere.
3. Apasă **Salvează**. Atât — dacă botul acelui cont rulează deja, se
   repornește singur și iese imediat prin noul proxy. Dacă nu rulează încă,
   proxy-ul se aplică automat la prima pornire.

> **Login-ul (cu CAPTCHA) se face mereu din dashboard.** Dacă vrei ca sesiunea
> de login și botul să iasă pe același IP (recomandat), setează proxy-ul
> contului **înainte** de a apăsa „Conectează cont OLX".

### Atenție — folosește mereu ACELAȘI proxy pentru un cont

Odată ce ai atribuit un proxy unui cont, **nu-l schimba** și nu-l lăsa să se
rotească între adrese diferite (unele servicii de proxy fac asta automat
"pentru anonimitate" — evită genul ăsta pentru boți). Sesiunea de login s-a
creat pe IP-ul respectiv; dacă botul începe brusc să vină de pe alt IP,
sistemele anti-fraudă OLX pot trata schimbarea ca pe un semnal suspect —
exact genul de corelare pe care proxy-ul încearcă să-l evite — și pot duce
la limitarea sau interzicerea contului. Regula simplă: **un cont OLX = un
proxy fix, tot timpul**.

## Probleme frecvente

- **"Python nu e instalat sau nu e in PATH"** — reinstalează Python și
  bifează opțiunea de adăugare în PATH (Windows), sau folosește `python3`
  (de obicei deja prezent pe Mac/Linux).
- **Portul 8000 sau 8080 e ocupat** — scripturile de pornire închid
  automat instanțele vechi; dacă tot nu merge, repornește calculatorul.
- **Sesiunea OLX a expirat** — reconectează contul din dashboard (butonul
  „Conectează cont OLX" apare din nou).
