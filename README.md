# Crypto Breakout Alert — Setup Guide (Free, 24/7)

Ye system 3 hisson mein hai:

1. **`scanner.py`** — Binance se real coin data leta hai, real technical
   indicators calculate karta hai, aur breakout milne par Gmail + phone app
   dono pe alert bhejta hai.
2. **GitHub Actions** — `scanner.py` ko har 15 minute, 24 ghante, hamesha
   free chalata hai. Koi server kiraye pe lene ki zaroorat nahi.
3. **`app/` folder** — ek installable phone app (PWA) jo push notification
   receive karti hai aur alert history dikhati hai.

Neeche har step follow karein — koi coding experience nahi chahiye.

---

## Part 1 — GitHub par project daalna

1. [github.com](https://github.com) par free account banayein.
2. New repository banayein (e.g. `crypto-breakout-alert`) — **Public** rakhein
   (Public repo pe GitHub Actions minutes unlimited/free hoti hain).
3. Is poore folder (`scanner.py`, `requirements.txt`, `.github/`, `app/`,
   `README.md`) ko us repo mein upload kar dein (GitHub website par
   "Add file → Upload files" se bhi ho sakta hai, drag-and-drop).

---

## Part 2 — Gmail se email alert (free)

1. Apne Gmail account mein **2-Step Verification** ON karein:
   `myaccount.google.com/security`
2. Us ke baad **App Passwords** section mein jayein:
   `myaccount.google.com/apppasswords`
3. Ek naam do (e.g. "Breakout Scanner") → 16-character password milega.
   Ye copy kar lein (spaces hata dein).
4. Apne GitHub repo mein: **Settings → Secrets and variables → Actions →
   New repository secret**. Ye 3 secrets add karein:
   - `GMAIL_ADDRESS` → aapka poora Gmail address
   - `GMAIL_APP_PASSWORD` → wo 16-character app password
   - `ALERT_TO_EMAIL` → jis email pe alert chahiye (same Gmail bhi ho sakta hai)

---

## Part 3 — Phone app (PWA) banwana aur push notification (free)

### 3a. Firebase project banayein
1. [console.firebase.google.com](https://console.firebase.google.com) par jayein
   → **Add project** → koi bhi naam do → free "Spark plan" hi kaafi hai.
2. Project ke andar: gear icon → **Project settings → General**.
3. "Your apps" mein **Web app (`</>`)** add karein, naam do, "Firebase Hosting"
   ka checkbox skip kar sakte hain.
4. Jo `firebaseConfig` object milega (apiKey, projectId, waghera), use copy
   karein.
5. Ye values `app/index.html` aur `app/firebase-messaging-sw.js` — dono files
   mein jahan `REPLACE_ME` likha hai wahan paste kar dein.
6. Same "Project settings" mein **Cloud Messaging** tab kholein → "Web
   configuration" ke neeche **Generate key pair** dabayein → milne wali
   "VAPID key" ko `app/index.html` mein `VAPID_KEY = "REPLACE_ME"` ki jagah
   paste karein.

### 3b. Service account key banayein (backend ke liye)
1. Firebase Console → Project Settings → **Service accounts** tab.
2. **Generate new private key** dabayein → ek `.json` file download hogi.
3. Us file ka **pura content** copy karein.
4. GitHub repo secrets mein 2 aur secrets add karein:
   - `FCM_PROJECT_ID` → aapka Firebase project ID (Project Settings mein milega)
   - `FCM_SERVICE_ACCOUNT_JSON` → us `.json` file ka pura content (paste as-is)

### 3c. App ko phone pe install karna
1. `app/` folder ko free static hosting par daalna hoga (taake ek link ban jaye):
   - **Sabse aasan: GitHub Pages** — repo Settings → Pages → Branch: `main`,
     Folder: `/app` (agar option na ho to `app` folder ko repo root pe alag
     branch/repo mein rakh dein) → Save. Kuch minutes mein ek link milega
     jese: `https://username.github.io/crypto-breakout-alert/`
2. Wo link apne phone (Chrome/Safari) mein khol lein.
3. Browser menu se **"Add to Home Screen"** dabayein — ab ye ek real app
   icon ki tarah phone pe install ho jayegi.
4. App khol kar **"Enable Notifications"** button dabayein — permission allow
   karein.
5. App neeche ek long **token** dikhayegi — us pura token copy karein.
6. GitHub repo secrets mein ek aur secret add karein:
   - `FCM_DEVICE_TOKEN` → wo copy kiya hua token
7. Bas — ab jab bhi `scanner.py` ko breakout milega, aapke phone pe turant
   push notification aayegi, chahe app band hi kyun na ho.

---

## Part 4 — 24/7 free run kaise hota hai

Isme koi server, VPS, ya paid hosting **bilkul nahi chahiye**:

- GitHub Actions ka scheduled workflow (`.github/workflows/scan.yml`) har
  **15 minute** pe khud-ba-khud chalta hai — 24 ghante, saal bhar, bilkul
  free (Public repos ke liye GitHub Actions minutes free hain, koi limit
  practically issue nahi karta is scale par).
- Aapko kabhi apna computer on rakhne ki zaroorat nahi — ye GitHub ke
  servers par chalta hai.
- Scan frequency badalne ke liye `.github/workflows/scan.yml` file mein
  `cron: "*/15 * * * *"` line change kar dein (e.g. `*/5 * * * *` = har 5 min,
  lekin bohot tez frequency Binance rate-limits se takra sakti hai).
- Chahen to **Actions** tab se manually bhi "Run workflow" button se turant
  chala sakte hain.

---

## Part 5 — Settings (thresholds) badalna

GitHub repo → **Settings → Secrets and variables → Actions → Variables**
tab mein ye add/change kar sakte hain (optional, defaults theek hain):

| Variable | Default | Matlab |
|---|---|---|
| `TIMEFRAME` | `1h` | Kis candle timeframe pe scan ho (15m, 1h, 4h) |
| `TOP_N_COINS` | `60` | Top kitne USDT pairs scan karne hain (volume ke hisaab se) |
| `RVOL_THRESHOLD` | `2.0` | Volume spike ka threshold |
| `RSI_THRESHOLD` | `60.0` | Minimum RSI |
| `ADX_THRESHOLD` | `25.0` | Minimum trend strength |
| `EXTENSION_THRESHOLD` | `0.10` | EMA20 se zyada extension par signal reject |

---

## Important disclaimer

Ye scanner sirf **real, calculable technical conditions** (trend + momentum +
volume + price-action + volatility) check karta hai — koi random ya fake
"institutional score" ya guaranteed "BUY" signal nahi deta. Har breakout
signal ek probability-based technical setup hai, financial advice nahi.
Crypto market bohot volatile hai — apna risk khud manage karein.
