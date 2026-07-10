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

## Probleme frecvente

- **"Python nu e instalat sau nu e in PATH"** — reinstalează Python și
  bifează opțiunea de adăugare în PATH (Windows), sau folosește `python3`
  (de obicei deja prezent pe Mac/Linux).
- **Portul 8000 sau 8080 e ocupat** — scripturile de pornire închid
  automat instanțele vechi; dacă tot nu merge, repornește calculatorul.
- **Sesiunea OLX a expirat** — reconectează contul din dashboard (butonul
  „Conectează cont OLX" apare din nou).
