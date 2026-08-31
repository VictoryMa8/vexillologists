# Vexillologists.com

Vexillologists.com is an interactive flag quiz and geography learning tool. The live site is [vexillologists.com](https://vexillologists.com).

## User guide

You can play without an account. Creating an account also saves your flag mastery, personal statistics, and leaderboard results.

- **Game modes:** Practice, Daily Challenge, Speed Round, Perfect Ten, Multiple Choice, adaptive Mastery Review, World Tour, and regional or themed collections.
- **Country explorer:** search and filter countries, territories, and other entries, then open an entry for its geography and flag details.
- **Mastery:** correctly identify a flag to collect it. Mastery Review prioritizes unmastered flags and flags you have missed.
- **Leaderboards:** each game mode has a separate ranking based on a player's best recorded score.
- **Preferences:** the light/dark theme and quiz-sound preference are saved in the browser.

## Developer guide

### Technology

| Layer | Technology |
|---|---|
| Application | Python 3.13, Django 5.2 |
| Database | PostgreSQL |
| Pages | Django templates, HTMX |
| Styling | Tailwind CSS 4, DaisyUI 5 |
| Authentication | Django auth, django-allauth, Google OAuth |
| Production | Gunicorn, WhiteNoise, Fly.io |
| Email | Resend SMTP |

PostgreSQL is required because `Country.aliases` uses Django's PostgreSQL `ArrayField`.

### Local setup

Prerequisites:

- Python 3.13
- PostgreSQL
- Node.js 18 or newer

Create the environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
cp .env.example .env
```

Create the PostgreSQL database named in `.env`, then initialize Django:

```bash
createdb vexillologists
python manage.py migrate
python manage.py createsuperuser
npm run css:build
python manage.py runserver
```

`createsuperuser` is optional, but it is the easiest way to add or edit countries through `/admin/`. A new database has no country records; populate it through the admin or from a trusted database export before testing quiz content.

For active CSS work, run this in a second terminal:

```bash
npm run css:watch
```

Signup email, Google login, and reCAPTCHA require the optional service credentials shown in `.env.example`. The rest of the application can run without them.

### Project map

```text
backend/
  settings.py          Django and service configuration
  test_settings.py     Test-only transport and cache overrides
  urls.py              Admin, allauth, and frontend URL roots
frontend/
  account_views.py     Signup, login, settings, and account deletion
  country_views.py     Explorer, country detail, search, and mastery pages
  countries.py         Country serialization, shared caching, and filtering
  gamemodes.py         Typed game-mode definitions and pool construction
  gameplay.py          Quiz requests, session state, results, and leaderboards
  forms.py             Validation and shared form-widget styling
  models.py            Users, countries, per-flag progress, and game results
  urls.py              Public URL-to-view mapping
  templates/           Server-rendered pages and reusable components
  static/assets/       Source CSS, generated CSS, scripts, media, and images
  tests/               Tests grouped by accounts, countries, gameplay, models, and pages
```

URLs point directly to the view module that owns the behavior. Static informational pages use Django's `TemplateView` and do not need empty view functions.

### Data model

- `Vexillologist` extends Django's user model with a World Tour high score, game count, and a many-to-many set of mastered countries.
- `Country` stores display data, categorization, flag URLs, facts, and accepted answer aliases.
- `FlagProgress` stores attempts, correct answers, misses, and the last-seen time for one user/country pair. Mastery Review uses this history.
- `GameResult` stores completed runs. Leaderboards aggregate each user's best result per game mode. A database constraint allows only one Daily Challenge result per user and date.

### Country explorer and cache

`countries.get_countries()` converts database records to template/session-friendly dictionaries. The serialized list is stored in Django's shared database cache for one hour. `Country` save/delete signals clear the key after the surrounding transaction commits, so another worker cannot refill the cache with pre-commit data.

The index view renders the full page. HTMX requests use `search_countries()` to replace only the country list. Both paths call the same `filter_countries()` function, so search and filter behavior stays consistent.

The cache key lives in `cache_keys.py`; change it there if the serialized country shape changes.

### Quiz lifecycle

1. A GET without an active game renders the mode picker.
2. Selecting a mode builds a stable country pool and stores its names plus counters in the Django session.
3. `_set_current_country()` chooses the next unseen flag and creates a per-question token. The token prevents duplicate or delayed HTMX responses from scoring the wrong round.
4. An answer POST updates `QuizProgress`, saves per-flag history immediately, and evaluates the selected mode's completion rules.
5. Finished authenticated runs create `GameResult` records. Daily results are protected by a database uniqueness constraint in case two browser tabs finish together.
6. HTMX answer requests return only `quiz_active.html`; ordinary form submissions use a redirect and store the result briefly in the session.

The server owns scores, timers, country pools, and answer checking. Browser JavaScript handles presentation concerns such as autocomplete selection, audio, focus, and the visible countdown.

Game behavior is described by the `GameMode` dataclass in `gamemodes.py`. To add a mode:

1. Add one `GameMode` entry to `GAME_MODES`.
2. Add a tone in `MODE_TONES` only if the default is unsuitable.
3. Add or adjust rules in `gameplay.py` if the existing `fixed`, `lives`, `timed`, or `sudden_death` rulesets do not cover it.
4. Add gameplay and leaderboard tests.

### Accounts

`account_views.py` owns signup, login throttling, profile changes, confirmation email, and deletion. Login attempts are counted in the shared cache by a hashed client address. Signup writes the user and allauth email record in one transaction; an email-service outage is logged but does not roll back the new account.

Username validation lives in `forms.py`. It blocks built-in impersonation terms plus optional comma-separated terms from `BLOCKED_USERNAME_WORDS`. `StyledFieldsMixin` applies the shared input classes, so templates do not need page-specific JavaScript for form styling.

### Frontend

- `input.css` is the source stylesheet; `output.css` is generated and committed for deployment.
- `components/form_fields.html` renders shared Django form fields and errors.
- `site.js` owns global theme, toast, and dialog behavior.
- `quiz.js` owns quiz autocomplete, focus, sound, hints, the countdown, and HTMX hooks.

Keep short, page-specific JavaScript in that page's `scripts` block so its HTML and behavior are easy to follow together. Extract a static script when the behavior is shared, substantial, or difficult to scan inline. Keep page-specific behavior out of `base.html`.

### Tests and checks

Tests use the `TEST_DB_*` PostgreSQL values from `.env`; Django creates a temporary database whose name begins with `test_`. These values default to the local setup shown in `.env.example`, and the configured user needs permission to create databases. Keeping test settings separate prevents a local test command from connecting to the production host by accident.

```bash
python manage.py check --settings=backend.test_settings
python manage.py makemigrations --check --dry-run
python manage.py test frontend --settings=backend.test_settings
```

Tests are grouped by feature in `frontend/tests/`. Factory helpers in `tests/factories.py` keep setup data consistent without hiding behavior relevant to a test.

### Comment and code style

- Let names and small functions explain what the code does.
- Comment constraints, compatibility behavior, race conditions, and non-obvious tradeoffs.
- Do not comment basic Python, Django template syntax, or an immediately visible `if` statement.
- Update or remove comments when behavior changes; an inaccurate comment is worse than no comment.
- Prefer a focused helper or reusable template component over copied code.

### Deployment

Fly.io builds the `Dockerfile`, runs migrations using the release command in `fly.toml`, and serves the application with Gunicorn. WhiteNoise collects and serves static files from `staticfiles/`. Production secrets and database credentials belong in Fly secrets, never in `.env` or source control.
