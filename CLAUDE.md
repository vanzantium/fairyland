# CLAUDE.md — Fairyland

AI assistant guide for the **Fairyland** repository. Read this before writing any code.

---

## Project Overview

**Fairyland** is a Flask-based plant identification and nature education web application. Its purpose is to help people explore and learn about plants in a safe, privacy-respecting way.

Core philosophy:
- **Safety first** — never guide users toward foraging, medicinal use, or consumption
- **Privacy first** — no tracking, no accounts, no analytics; ephemeral sessions by default
- **Honest** — the app does not claim to identify plants; it links to trusted external tools

---

## SAFETY — Prime Directive

> Read `SAFETY.md` before writing any feature. These rules are non-negotiable.

| Rule | Detail |
|------|--------|
| **Look, don't taste** | No foraging, medicinal, dosage, or "is it edible?" guidance — ever |
| **No GPS magic** | No precise coordinates; encourage habitat archetypes ("any oak", "streamside meadow") |
| **Kid mode** | Routes to [Seek](https://www.inaturalist.org/pages/seek_app) / [iNaturalist](https://www.inaturalist.org/) links only; the app never claims to identify a plant |
| **Burn Mode** | Ephemeral sessions by default — no user tracking, no accounts, no analytics |

**For AI assistants — never:**
- Add edibility, toxicity, medicinal, or dosage information
- Add location tracking, user accounts, or any analytics
- Write code that makes plant identification claims
- Persist user session data beyond ephemeral scope

---

## Repository Structure

```
fairyland/
  app.py                     # Flask application entry point (planned)
  requirements.txt           # Python dependencies (Flask 3.0.3)
  SAFETY.md                  # Prime directive — read before coding
  CLAUDE.md                  # This file
  repo-structure             # Canonical planned directory layout
  data/
    plants/
      <slug>.plant.json      # Plant metadata (name, description, habitat, etc.)
      <slug>.media.json      # Media references for a plant (images, illustrations)
```

`app.py` and `data/` are planned but not yet committed — use `repo-structure` as the authoritative layout reference.

---

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
flask run
# or
python app.py
```

No environment variables or external services are required at this stage.

---

## Key Conventions

### Data Files
- Plant data is stored as JSON, one plant per pair of files:
  - `<slug>.plant.json` — metadata (common name, scientific name, description, habitat archetype)
  - `<slug>.media.json` — media references (images, illustrations, credits)
- Slugs are lowercase, hyphen-separated (e.g., `bracken-fern`, `wood-sorrel`)

### Python Style
- Standard Flask patterns; keep dependencies minimal
- No ORM or database — data is flat JSON files
- Sessions must be ephemeral (do not write session data to persistent storage)

### External Links Over In-App Claims
- For plant identification, always link to [Seek](https://www.inaturalist.org/pages/seek_app) or [iNaturalist](https://www.inaturalist.org/)
- Never present the app as authoritative on species identification

---

## Git Workflow

| Aspect | Convention |
|--------|-----------|
| Branch naming | `claude/<description>-<short-id>` |
| Commit style | Present tense, action verb: `Add ...`, `Update ...`, `Fix ...` |
| Signing | GPG/SSH signed commits are enforced |

---

## Testing

No tests exist yet. When adding tests:
- Place them in a `tests/` directory at the repo root
- Use `pytest` (add to `requirements.txt` when introduced)
- Run with `pytest tests/`

---

## CI/CD

No CI/CD pipeline configured yet. When adding one, prefer GitHub Actions (`.github/workflows/`).
