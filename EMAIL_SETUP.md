# Email Confirmations Setup

Booking confirmations are sent via your own Gmail account using SMTP.
Google requires a special **"App Password"** for this — not your normal
Gmail login password — because your regular password won't work for
apps like this (Google blocks it for security).

## 1. Turn on 2-Step Verification (required first)

App Passwords only work if 2-Step Verification is already on for your account.

1. Go to https://myaccount.google.com/security
2. Under "How you sign in to Google," turn on **2-Step Verification** if it isn't already
3. Follow the prompts (usually verifying with your phone)

## 2. Generate an App Password

1. Go to https://myaccount.google.com/apppasswords
   (If this link asks you to sign in again, do so)
2. Under "App name," type something like `Glow Studio`
3. Click **Create**
4. Google will show a **16-character password** like `abcd efgh ijkl mnop`
5. Copy it (remove the spaces) — you'll only see it once

## 3. Add it to your `.env` file

```
MAIL_USERNAME=youraddress@gmail.com
MAIL_PASSWORD=abcdefghijklmnop
MAIL_DEFAULT_SENDER=youraddress@gmail.com
```

- `MAIL_USERNAME` — the Gmail address you generated the App Password for
- `MAIL_PASSWORD` — the 16-character App Password (no spaces)
- `MAIL_DEFAULT_SENDER` — usually the same as MAIL_USERNAME

## 4. Restart the app

```powershell
python app.py
```

## 5. Test it

Book a service as a customer. Check the inbox of the email address you
used to register — you should get a confirmation email within a few
seconds. Also check your **Spam folder** the first time; Gmail sometimes
flags automated emails from a new sender.

## Troubleshooting

- **"Username and Password not accepted"** — you likely used your real
  Gmail password instead of the App Password, or 2-Step Verification
  isn't turned on yet.
- **No error, but no email arrives** — check Spam folder, and double
  check the customer's email address was typed correctly at signup.
- **App Passwords option missing from Google** — this usually means
  2-Step Verification isn't enabled yet; go back to step 1.
