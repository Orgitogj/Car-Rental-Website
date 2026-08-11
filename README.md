# Vantage Rentals

> A multi-tenant car rental management platform built with Django, HTML, CSS and JavaScript, providing separate experiences for a platform administrator, rental companies and customers.

## Project Overview

Vantage Rentals is a web application that connects independent car rental companies with customers in a single marketplace. Each rental company runs its own fleet, pricing and reservations from a private console, while the public site lets visitors search across every company's vehicles, check availability for a date range, price a rental with optional add-ons and submit a booking request. A platform administrator sits above all of it, creating and managing companies, monitoring platform-wide activity and exporting reports.

The core problem the project solves is tenant isolation with a shared storefront: many companies publish to one catalogue, but no company may read or modify another's bookings, vehicles or customers. That boundary is implemented once — in a request-scoped company context, a set of controller decorators and re-checks inside the service layer — rather than being re-implemented in every controller. The application follows a Model–View–Controller separation, with the domain rules held in a dedicated service and selector layer so the controllers stay thin. The system also demonstrates a full server-side booking pipeline (validation, availability locking, price calculation, audit logging and email notification), Excel report generation, a four-language interface, and a hand-built CSS/JavaScript front end with no framework, bundler or CDN.

Main capabilities actually implemented:

- Public vehicle catalogue with multi-criteria search, faceted filtering, sorting and pagination
- Date-range availability checking shared by search, the vehicle page and booking creation
- Guest booking flow with server-computed quotes, optional paid add-ons and a booking reference
- Booking lookup by reference and name, with no account required
- Company console: dashboard metrics, bookings, fleet, customers, pricing add-ons, maintenance, reports, company profile
- Platform console: companies, users, fleet and booking overviews, contact messages, audit log, reports, command-palette search
- Read-only drill-in that lets the platform administrator open any company's real console without being able to change anything
- Excel (`.xlsx`) exports for both consoles, scoped and filtered
- Audit trail recording sensitive actions, including blocked ones
- Albanian, English, Italian and German interface with a language switcher
- Light and dark theme, remembered per browser

## Key Technologies

- **Python** — application language
- **Django 6.0** — web framework, ORM, forms, auth, sessions, i18n, admin
- **PostgreSQL** — database, via `psycopg2-binary`
- **Pillow** — validation of uploaded images
- **openpyxl** — generation of `.xlsx` report workbooks
- **python-dotenv** — loading configuration from a local `.env`
- **HTML5** with the Django template language — server-rendered pages
- **CSS3** — custom design system built on CSS custom properties (no CSS framework)
- **JavaScript (ES modules)** — progressive enhancement, loaded natively by the browser with no bundler or CDN

## Architecture

The project is organised as a **Model–View–Controller (MVC)** application, and the directory layout says so: the request handlers live in `rental/controllers/`.

| MVC role | Responsibility | In this project |
| --- | --- | --- |
| **Model** | Domain state and business rules | `rental/models/`, `rental/services/`, `rental/selectors/` |
| **View** | Presentation | `templates/`, `static/`, `rental/templatetags/ui.py` |
| **Controller** | Request handling and dispatch | `rental/controllers/`, `rental/accounts/controllers.py`, `rental/urls.py`, `carrental/urls.py`, `rental/middleware.py` |

### Model

- **Entities** (`rental/models/`) — the domain, split across modules by concern (companies, vehicles, bookings, customers, support, audit), with custom `QuerySet` managers holding the reusable query vocabulary (`bookable()`, `for_company()`, `available_between()`, …).
- **Services** (`rental/services/`) — the behavioural half of the model: business operations such as creating a booking, confirming it, saving a vehicle or suspending a company. They own their transactions, write the audit trail, and re-check authorisation themselves, so a controller that forgets a decorator still cannot mutate another tenant's data.
- **Selectors** (`rental/selectors/`) — the read half: dashboard metrics and the public search/facet builder, kept separate from the write operations.
- **Reports** (`rental/reports/`) — a workbook builder plus a catalogue of report definitions shared by both consoles.

Keeping business rules in services and selectors rather than in the controllers is what makes the MVC separation real here: the controllers hold no domain logic, and the same operation behaves identically whether it is reached from an HTML form, a JSON endpoint or a test.

### View

- **Templates** (`templates/`) — three base shells (public, dashboard, auth) plus reusable components; registered through the project-level `DIRS`, not per-app.
- **Template tags** (`rental/templatetags/ui.py`) — presentation helpers for currency, icons, pagination windows and status tones, so formatting decisions live in the view layer.
- **Static assets** (`static/`) — CSS organised as base / components / layouts / pages; JavaScript as core / components / pages ES modules.

### Controller

- **Routing** — `carrental/urls.py` wraps every route in `i18n_patterns`, so all paths are language-prefixed (`/en/cars/`, `/sq/cars/`). `rental/urls.py` groups patterns into public, company (`/portal/`), console (`/console/`) and JSON API sections.
- **Controllers** (`rental/controllers/`) — one module per audience: `public`, `company`, `superadmin`, `reports`, `booking_api`, `media`, `errors`. Each one parses the request, delegates to a selector or service, and picks a template or JSON response. Authentication controllers live alongside their app in `rental/accounts/controllers.py`.
- **Middleware and guards** (`rental/middleware.py`, `rental/access.py`) — `CompanyContextMiddleware` attaches a lazily-resolved `CompanyContext` to every request, carrying the company in scope and whether the caller may *manage* it or only *read* it. Decorators (`company_member_required`, `company_manage_required`, `superadmin_required`) apply that context at the controller boundary.

### Supporting pieces

- **Forms** (`rental/forms.py`, `rental/accounts/forms.py`) — Django `Form`/`ModelForm` classes sitting between controller and model, handling validation and binding, with a shared styling mixin that applies the design-system CSS classes and ARIA attributes.
- **Media** — vehicle photos and company logos are stored as binary columns in PostgreSQL and streamed by a cached, ETagged controller, not written to disk. `MEDIA_URL` / `MEDIA_ROOT` are configured but no model writes to them.

There are two Django apps: `rental` (the domain) and `rental.accounts` (authentication and the user profile). The `rental` app label is deliberately kept as one app; the MVC separation is enforced at module level rather than by splitting the database tables across apps.

## Project Structure

```
carrental/                  Django project configuration
  settings/
    base.py                 shared settings, environment loading
    development.py          local defaults, console email, optional SQL logging
    production.py           secure defaults, fails fast on missing config
  urls.py                   root URLConf (i18n_patterns, error handlers)
  asgi.py  wsgi.py          server entry points

rental/                     main application
  models/                   MODEL — companies, vehicles, bookings, customers, support, audit
  services/                 MODEL — write operations: bookings, fleet, companies, customers, audit
  selectors/                MODEL — read queries: metrics (dashboards), search (catalogue)
  controllers/              CONTROLLER — public, company, superadmin, reports,
                            booking_api, media, errors
  reports/                  workbook builder + report catalogue
  accounts/                 auth app: Profile model, controllers.py (login/register/
                            logout), forms
  management/commands/      trans_extract, trans_compile
  locale/                   sq, en, it, de message catalogues
  templatetags/ui.py        icons, money, pagination, tone and formatting helpers
  migrations/               8 migrations
  tests/                    booking rules, tenancy, controllers, reports, i18n
  access.py                 CompanyContext, permission guards and decorators
  middleware.py             attaches the company context to each request
  context_processors.py     navigation/context values shared by every template
  forms.py                  car, extra, company, contact and lookup forms
  i18n_tools.py             pure-Python .po parser / .mo writer
  signals.py                booking confirmation email
  admin.py                  Django admin registrations
  urls.py  utils.py

templates/                  VIEW — server-rendered presentation
  base/                     public, dashboard and auth shells + shared <head>
  components/               car card, KPI, field, pagination, icons, flash, language menu
  public/                   home, cars, car detail, checkout, success, lookup, about, contact
  company/                  dashboard, bookings, fleet, car form, customers, pricing,
                            maintenance, reports, settings
  superadmin/               dashboard, companies, users, fleet, bookings, messages,
                            activity, reports
  auth/                     login, portal login, signup
  errors/                   400, 403, 404, 500

static/                     VIEW — client-side assets
  css/                      base (reset, tokens, typography, utilities), components,
                            layouts, pages
  js/                       core (app, api, toast), components (chart, filters, table,
                            sidebar, overlays, palette), pages (car-detail)

manage.py                   Django management entry point
requirements.txt            Python dependencies
```

Configuration lives in a `.env` file you create in the project root; it is git-ignored and not part of the repository. See [Environment Variables](#environment-variables).

## User Roles

Roles are derived from the Django `User` record, not from a separate role column: a superuser is the platform administrator, a user with a related `Company` (one-to-one `owner`) is a company account, and any other user is a customer.

### SuperAdmin

Signs in through the business portal (`/portal/login/`) and works in the platform console at `/console/`. A super admin can:

- View a platform dashboard: revenue, bookings, fleet size, utilisation, active rentals, top companies, recent activity and recent bookings, each with a 30-day trend
- Create a rental company together with its owner account, and seed its default add-ons
- Edit company details, change a company's status (active / pending / suspended), and delete a company along with its owner account
- Open any company's own console in **read-only** mode, and exit back to the platform console
- Browse every vehicle and every booking on the platform, filtered by company, status, text and date range
- List non-superuser accounts and activate or deactivate them
- Read contact-form messages and record a reply against them
- Search the full audit log, filtered by action, company or text
- Export seven report workbooks: companies, bookings, revenue, fleet, customers, users, activity log
- Use a command palette that searches companies, vehicles, bookings and customers
- Reach the Django admin site

A super admin does **not** get write access to a company by drilling into it. The read-only context is enforced by the `company_manage_required` decorator on every mutating view and again by `ensure_can_manage()` inside the service functions; templates merely hide the controls. The company being viewed is held in the session, never in a URL.

### Companies

A company account is created by the super admin, not by self-registration. The owner signs in at `/portal/login/` and manages their company at `/portal/`. A company owner can:

- View a dashboard: revenue today / period / lifetime, bookings, pending count, active rentals, fleet totals, utilisation, a 30-day revenue chart, a fleet breakdown by category, upcoming pickups and returns, and an attention list (pending requests, overdue returns, never-booked vehicles)
- List and search their bookings by reference, customer, email or vehicle, filter by status and date range, and confirm or cancel them individually or in bulk
- Add, edit, delete and list/unlist vehicles, upload multiple photos, delete a photo and choose the cover photo
- Browse their customer list with booking counts and lifetime value, and open a customer to see their booking history
- Create and remove paid add-ons (extras) with a per-day price, active flag and sort order
- Schedule maintenance records against a vehicle and mark them completed
- Export five report workbooks: bookings, revenue, fleet, customers, maintenance
- Edit the company profile — name, description, email, phone, city, address, website and logo

A company only ever sees its own data: every query is filtered by the company on the request context, and the services refuse any object belonging to another company.

### Users

Customers use the public site. They can:

- Browse the vehicle catalogue and open a vehicle's detail page with its photo gallery, specifications, add-ons and similar vehicles
- Search and filter across all companies (see below)
- Get a live price quote and availability answer for a date range
- Submit a booking request with their name, email and phone, receiving a `CR-XXXXXXXX` reference and a confirmation email
- Look up an existing booking with its reference and the name on it
- Send a message through the contact form
- Register an account and sign in or out
- Switch the interface language and toggle dark mode

Booking does not require an account, and the project does **not** include a customer account dashboard: a registered customer's bookings are not linked to their login, and bookings are retrieved through the reference-and-name lookup. Registration provides an authenticated identity and account menu; the booking flow itself is the same for signed-in and anonymous visitors.

## Core Features

### Authentication

- Customer registration (`/accounts/register/`) with full name, email, phone, and password confirmation. The email becomes the username; passwords go through Django's validators (minimum 8 characters, not common, not entirely numeric, not similar to the user's attributes).
- Two sign-in surfaces backed by one view: the customer login (`/accounts/login/`) and the business portal login (`/portal/login/`), which rejects accounts that are neither a super admin nor a company owner.
- Either identifier signs you in: `UsernameOrEmailBackend` (`rental/accounts/backends.py`) matches the typed value against username *or* email, case-insensitively. Accounts made on the site use the address for both, but a `createsuperuser` account may hold a separate handle. Where one identifier names two accounts — an address held as one user's username and another's email — each candidate is checked against the password, so both stay reachable.
- Logout for both surfaces; deactivated accounts are refused with a clear message.
- After signing in, users are redirected by role — platform console, company console, or the public home page — and a `?next=` destination is honoured only after a same-host safety check.
- Password fields are marked sensitive for error reports, and login views are never cached.
- Sessions are HTTP-only, `SameSite=Lax`, and last 14 days.

### Role-based Access Control

- `CompanyContextMiddleware` resolves a `CompanyContext` for every request: the company in scope plus a mode of `manage` or `read_only`.
- `company_member_required` allows read access to a company's console; `company_manage_required` additionally requires manage mode; `superadmin_required` gates the platform console.
- The service layer re-checks with `ensure_can_manage()` and `ensure_same_company()` before mutating anything.
- A blocked write by a read-only viewer is written to the audit log as `access.denied`.

### Vehicle Management

- Vehicles carry brand, model, category (economy, family, SUV, luxury, sports), description, price per day, year, seats, doors, bags, horsepower, engine size, fuel (petrol, diesel, hybrid, electric) and gearbox (manual, automatic).
- Multiple photos per vehicle, uploaded through a multi-file field. Uploads are checked for size (5 MB default), MIME type (JPEG, PNG, WebP, AVIF) and are opened by Pillow to verify they are real images before being stored.
- The first uploaded photo becomes the cover; the cover can be changed, and deleting the cover promotes another photo automatically.
- Images are stored as binary columns and served from `/media/car-image/<id>/` with an ETag, `Last-Modified`, a long `Cache-Control` and `304` handling.
- A vehicle can be listed or unlisted; unlisted vehicles disappear from the public site but keep their history.
- Database constraints enforce a non-negative price and a positive seat count.

### Search & Filtering

The public catalogue (`/cars/`) parses its filters from the query string, ignoring anything malformed:

- Free-text query across model, brand and company name
- Pick-up and return date range — vehicles with an overlapping pending or confirmed booking are excluded
- Minimum and maximum price per day
- Minimum and maximum year
- Minimum seats and minimum horsepower
- Brand, fuel, gearbox and category (multi-select)
- Company
- Sorting: recommended, price ascending/descending, newest, oldest, most seats
- 12 results per page, with the filter state preserved across pages

Filter options are generated from the live fleet (available brands, real price range, companies with listed vehicles). The form is a plain GET submit and works without JavaScript; when JavaScript is available, changes fetch only the results fragment and update the URL so the page stays shareable and the back button keeps working.

### Reservations / Rentals

1. A visitor picks dates on a vehicle page. The browser asks `POST /api/quote/` for a price and an availability answer; the same numbers are recomputed server-side at every later step.
2. Dates are validated: both present, pick-up not in the past, return after pick-up, and at least `MIN_RENTAL_DAYS` nights (3 by default).
3. Pricing is entirely server-side. The browser sends identifiers and dates only; the day rate and add-on prices are read from the database. Add-ons are re-filtered to the vehicle's own company and to active rows.
4. On checkout, the booking is created inside a transaction that locks the vehicle row (`select_for_update`) and re-checks availability, so two simultaneous customers cannot both succeed. The customer record is created or updated, add-on lines are snapshotted onto the booking, and the vehicle's popularity counter is incremented.
5. Availability uses a half-open interval, so a rental ending on the 14th does not block one starting on the 14th. Search and booking share one definition.
6. The booking is stored as `pending` with a unique `CR-XXXXXXXX` reference and a price snapshot (rate, days, base, extras, total), and a "booking received" email is queued after the transaction commits.
7. The company confirms or cancels it. Confirmation sends a second email through a `post_save` signal, and both transitions are audit-logged with a timestamp.
8. The customer can retrieve the booking at any time from `/booking/lookup/` using the reference and the name on it.

Two JSON endpoints back this flow: `POST /api/quote/` and `POST /api/bookings/create/`, both CSRF-protected like every other POST.

### Company Dashboard

`/portal/` shows revenue for today, the last 30 days (with the change against the previous 30) and lifetime; booking counts on the same basis; pending requests; rentals currently on the road; fleet totals and utilisation; customer count; a gap-filled daily revenue chart drawn as inline SVG; a fleet breakdown by category; the next 14 days of pickups and returns; and an attention list of pending bookings, overdue returns and vehicles that have never been booked.

### Admin Dashboard

`/console/` shows the same shape of metrics platform-wide: total, active, suspended and pending companies, new companies in the period, fleet size, bookings, pending bookings, active rentals, lifetime and period revenue, utilisation, registered users, customers and unread messages — plus the top five companies by confirmed revenue, the eight most recent audit entries and the six most recent bookings.

### Reporting & Exports

Both consoles share one report engine. Reports are filtered by date range, status and (on the platform side) company, and are streamed as styled `.xlsx` workbooks with typed columns, currency and date formats, totals rows and Excel tables. The revenue report adds a summary sheet, a daily sheet and a per-vehicle sheet. A company export can never widen its own scope — the company filter is cleared server-side. Every export is audit-logged.

### Audit Trail

Sensitive actions are recorded once, in the service layer: company created / updated / deleted / status changed / opened read-only, vehicle created / updated / deleted, booking created / confirmed / cancelled, user activated / deactivated, report exported, and blocked unauthorised actions. Each entry keeps the actor (and a name that survives the user being deleted), the company, the entity, the IP address, JSON metadata and a timestamp. The log is browsable and exportable from the platform console, and is read-only in the Django admin.

### Internationalisation

The interface ships in Albanian, English, Italian and German. Every URL is language-prefixed by `i18n_patterns`, and a language menu posts to Django's `set_language` view. GNU gettext is **not** required: `rental/i18n_tools.py` is a pure-Python `.po` parser and `.mo` writer, driven by two management commands. `trans_compile` refuses to write a catalogue whose translation names a placeholder its source does not have, since that mismatch would only surface as an exception at render time.

## Prerequisites

- **Python 3.12 or newer** — required by Django 6.0
- **pip** and the `venv` module
- **PostgreSQL** — a running server and a database for the project; the settings hard-code the `django.db.backends.postgresql` engine, so SQLite is not an option
- No Node.js, bundler or package manager: the CSS and JavaScript are served as authored
- No GNU gettext: the translation commands are pure Python

## Environment Variables

Configuration is read from the environment; `carrental/settings/base.py` loads a `.env` file from the project root during development. Nothing secret lives in source, and `.env` is git-ignored, so the repository ships no environment file of any kind — create your own from the sample below. It lists every variable the project reads, with the defaults applied when a variable is absent.

```env
# --- Django core ---
DJANGO_SECRET_KEY=replace-me-with-a-long-random-string
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_TIME_ZONE=Europe/Tirane

# --- Database ---
DB_NAME=SuperRental
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

# --- Email ---
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=Car Rental <no-reply@carrental.local>

# --- Business rules ---
MIN_RENTAL_DAYS=3
DEFAULT_CURRENCY_SYMBOL=€

# --- Production only ---
# DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com
# DJANGO_SECURE_SSL_REDIRECT=True
# REDIS_URL=redis://127.0.0.1:6379/1
```

`DJANGO_SECRET_KEY` is the only variable with no default — the application refuses to start without it. Everything else falls back to the values shown above. Leaving `EMAIL_HOST_PASSWORD` blank in development switches the email backend to the console, so booking emails are printed instead of sent.



## Setup Instructions

### 1. Clone the repository

```bash
git clone <repository-url>
cd Car-Rental-website
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the environment

Create a `.env` file in the project root. It is git-ignored and never ships with the repository, so write it from the sample block in [Environment Variables](#environment-variables) above, which lists every variable the project reads.

At minimum, set `DJANGO_SECRET_KEY` to a long random string — the application refuses to start without it — and fill in your PostgreSQL credentials:

```env
DJANGO_SECRET_KEY=replace-me-with-a-long-random-string
DJANGO_DEBUG=True
DB_NAME=SuperRental
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
```

Every other variable has a working default. Leaving `EMAIL_HOST_PASSWORD` unset keeps development email on the console backend.

### 5. Create the database

Create an empty PostgreSQL database matching `DB_NAME` (`SuperRental` by default), then apply the migrations:

```bash
python manage.py migrate
```

### 6. Create a platform administrator

```bash
python manage.py createsuperuser
```

The super admin is the account that creates rental companies; company owners are created from the platform console, not by signing up.

### 7. Compile the translations

Compiled `.mo` files are not committed, so a fresh clone needs this step before the non-English locales render:

```bash
python manage.py trans_compile
```

### 8. Run the development server

```bash
python manage.py runserver
```

The site is then available at `http://127.0.0.1:8000/` (which redirects to a language-prefixed URL such as `/en/`).

`manage.py` defaults to `carrental.settings.development`. For production, set `DJANGO_SETTINGS_MODULE=carrental.settings.production`, which turns on HSTS, the SSL redirect, secure cookies and hashed static filenames, and requires `DJANGO_ALLOWED_HOSTS`.

### Running the tests

```bash
python manage.py test rental.tests
```

107 tests across five modules: booking rules and pricing, tenant isolation and read-only enforcement, every route and view, report exports, and the translation pipeline.

### Working on translations

```bash
python manage.py trans_extract    # rescan the source, refresh every .po
python manage.py trans_compile    # write the .mo files Django actually reads
```

`trans_extract` keeps existing translations and only adds or drops entries; it fills the English catalogue automatically, since message ids are authored in English. Edit the `msgstr` values in `rental/locale/<code>/LC_MESSAGES/django.po`, then compile. Both commands accept `--locale/-l` to limit the languages processed, and `trans_compile` accepts `--strict` to fail when a locale is incomplete.

## Application Experience

The application currently supports:

- A public marketplace: home page with a search widget, featured vehicles, participating companies and live platform statistics; a filterable catalogue; vehicle detail pages with a gallery, live quoting and availability
- A guest booking flow ending in a reference, a success page and an email
- A booking lookup page for retrieving a reservation without an account
- A contact form with a honeypot field, feeding the platform console's message inbox
- A company console covering dashboard, bookings, fleet, customers, pricing, maintenance, reports and settings
- A platform console covering dashboard, companies, users, fleet, bookings, messages, activity and reports, plus a keyboard-driven command palette
- A read-only drill-in from the platform console into any company's console
- Excel exports from both consoles
- Four interface languages and a light/dark theme, both switchable from the header
- Custom 400, 403, 404 and 500 pages
- Toast notifications, modals, confirm dialogs, bulk selection, animated counters and inline SVG charts — all hand-written, with no third-party JavaScript

## How to Review

A reviewer can verify:

- **Tenant isolation** — sign in as two different company owners and confirm that each console shows only its own bookings, vehicles and customers; then try a URL belonging to the other company and observe the 403. `rental/tests/test_tenancy.py` covers this.
- **Read-only enforcement** — as super admin, open a company with *View dashboard*, then attempt any write. The button is hidden, the view refuses, the service refuses, and an `access.denied` row appears in the activity log.
- **Server-side pricing** — tamper with the add-on ids or dates posted to `/api/quote/` or the checkout form and confirm the total is recomputed from the database, never trusted from the client.
- **Availability correctness** — book a vehicle for a range, then search for an overlapping range and confirm the vehicle disappears; search for a range starting on the return date and confirm it is still offered.
- **Concurrency** — `create_booking()` locks the vehicle row and re-checks availability inside the transaction; `rental/tests/test_booking_rules.py` exercises the rules around it.
- **Search behaviour** — apply filters with JavaScript disabled; the plain GET form still works, and the URL remains shareable with JavaScript on.
- **Audit trail** — perform a create, an update, a delete and an export, then confirm each appears in `/console/activity/` with actor, company, entity and IP.
- **Reports** — export the same report from a company console and from the platform console and confirm the company version cannot widen its scope beyond its own data.
- **Internationalisation** — switch language in the header and confirm the URL prefix and page content change; run `python manage.py trans_compile --strict` to check catalogue completeness and placeholder safety.
- **Configuration hygiene** — confirm no secret is committed: `SECRET_KEY`, database credentials and SMTP details all come from the git-ignored `.env`.
- **The test suite** — `python manage.py test rental.tests` (107 tests).

## GitHub

Repository: *no remote is configured on this checkout — add the repository URL here once it is published.*
