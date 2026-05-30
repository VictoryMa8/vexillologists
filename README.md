# Vexillologists.com

Vexillologists.com is a project made by yours truly. It is a fun, interactive, and replayable flag quizzing game and educational tool for geography and world-politics lovers alike.

**🌍 Live at [vexillologists.com](https://vexillologists.com)**

---

## What can you do?

- **Quiz yourself**: a random flag appears, you type the country. Get it right and your streak grows; get it wrong and the game ends! 
- **Build your collection**: every flag you correctly identify during a game gets permanently added to your profile!
- **Mastery page**: see all ~250 flags of the world laid out alphabetically. Flags you've collected are fully visible; the rest are locked until you earn them.
- **Leaderboard**: compete for the highest streak against other players!
- **Country explorer**: browse every country and territory on the home page, with capitals, populations, regions, official languages, and a fun fact for each.
- **Dark / light theme**: your eyes, your choice.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13 · Django 5.2 |
| Database | PostgreSQL |
| Frontend | Django Templates · Tailwind CSS · DaisyUI · HTMX |
| Auth | django-allauth (email + Google OAuth2) |
| Static files | Whitenoise |
| Email | Resend (SMTP relay) |

No JavaScript framework. The live search and autocomplete are powered by HTMX, a small library that makes server-rendered partials feel instant without client-side state management.

---

## Engineering Highlights

**Session-based game state**: quiz state (current flag, streak, collected flags) lives in the server-side Django session. This prevents a trivial cheat where a player could edit the streak value in DevTools.

**Secure POST/GET pattern**: after every guess, the server redirects to a GET instead of rendering directly from the POST. This means refreshing after a wrong guess can't accidentally re-submit the form.

**In-memory caching**: the full country list is cached in RAM on first request and reused across all views for 1 hour, cutting database queries greatly. A Django signal (`post_save`/`post_delete` on the `Country` model) automatically clears the cache whenever an admin edits a country, so stale data is never served.

**No repeated flags**: already-collected flags are excluded from the random pool for the rest of that game, so your streak always shows you something new.

**Rate-limited login**: failed login attempts are tracked per IP in the cache; 5 failures in 60 seconds triggers a temporary lockout.

---

*Built with ❤️ and curiousity for the 🌏 from Minnesota.*
