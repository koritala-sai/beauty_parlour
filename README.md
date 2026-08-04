# Glow Studio — Flask Beauty Parlour App

## What's included

- `app.py` — app factory, run this to start the server
- `config.py` — reads DB credentials from `.env`
- `extensions.py` — shared `db` and `login_manager` instances
- `models.py` — `User`, `Service`, `Staff`, `Booking` tables
- `routes/` — one blueprint per area: `main` (home/services), `auth` (login/register), `booking` (customer booking flow), `admin` (dashboard)
- `templates/` — Jinja2 HTML pages
- `static/css/style.css` — styling

## 1. Set up MySQL

Create the database (using MySQL Workbench, phpMyAdmin, or the command line):

```sql
CREATE DATABASE beauty_parlour;
```

## 2. Set up the Python environment

```bash
cd beauty_parlour
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your real MySQL username/password and a random `SECRET_KEY`.

## 4. Create the tables

Running the app once will auto-create tables (see the bottom of `app.py`):

```bash
python app.py
```

Visit **http://127.0.0.1:5000** — you should see the home page (no services yet).

## 5. Create your admin account

Since there's no signup checkbox for "admin" (on purpose — anyone could tick it),
promote yourself to admin manually after registering:

1. Register a normal account at `/register`
2. In MySQL, run:
   ```sql
   UPDATE users SET is_admin = 1 WHERE email = 'youremail@example.com';
   ```
3. Log out and log back in — you'll now see an "Admin" link in the navbar

## 6. Add your first services

Go to `/admin/services` and add a few services (e.g. Haircut, Facial, Manicure).
They'll immediately show up on the home page and `/services`.

## What's next (not built yet)

- Payment gateway integration (Razorpay) — hook it into `routes/booking.py`
  where the comment marks where payment should be triggered
- Email/SMS booking confirmations
- PWA manifest + service worker so it's installable on phones
- Staff management UI (the `Staff` model exists, but there's no admin page
  to add/edit staff yet — for now you'd add rows directly in MySQL)
- Reviews, loyalty points, promo codes (mentioned in the original plan,
  intentionally left out of this MVP to keep the first build manageable)

## Notes

- Auth is intentionally simple: one `users` table with an `is_admin` flag,
  rather than separate customer/admin systems. Fine for a solo project.
- All dates/times are stored as MySQL `DATE`/`TIME` columns via SQLAlchemy —
  no timezone handling included, assumes single-timezone use (one parlour,
  one location).
