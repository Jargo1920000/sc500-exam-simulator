# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

- **Docs style:** write all docs in plain English and the active voice. Never use em dashes.
- **No hard-coded IDs:** never hard-code subscription IDs, tenant IDs or resource names. Put them in the `.example` files (`.env.example`, `terraform/terraform.tfvars.example`, `terraform/backend.hcl.example`) and read them from there.
- **New app files:** add any new file the app needs to the zip lists in both `deploy/azure.sh` and `.github/workflows/deploy.yml`. In the workflow, also add it to the `paths` filter and the file-presence check.
- **Before every commit:** run the checks in `scripts/`.

## What this is

A study tool for Microsoft exam SC-500. A FastAPI app generates practice exams with Claude from the live Microsoft Learn study guide. A Terraform module deploys deliberately misconfigured Azure resources for 12 hands-on labs.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY
python app.py                 # http://127.0.0.1:8500 (SC500_PORT to change)
SC500_MOCK=1 python app.py    # placeholder questions, no API key, no token spend
```

Repo checks (also run on every pull request by `.github/workflows/checks.yml`):

```bash
python3 scripts/check_deploy_lists.py   # app modules and static/ files are in both deploy zip lists
bash scripts/check_secrets.sh           # no subscription/tenant GUIDs, storage keys or API keys
```

There is no test suite, linter or build step. Check app changes by running the app with `SC500_MOCK=1`.

Labs (run from `terraform/`): `terraform init -backend-config=backend.hcl`, then `terraform plan -out lab.tfplan && terraform apply lab.tfplan`.

Hosted deploy: `bash deploy/azure.sh create|deploy|logs|status|pause|resume|delete`. Pushes to `main` also deploy through `.github/workflows/deploy.yml`, which uses OIDC.

## Architecture

The exam pipeline runs across four Python modules:

1. **`guide.py`** scrapes the live SC-500 study guide into areas, weights and objectives. If the page can't be fetched, it falls back to `guide_snapshot.json`, and that exam is labelled unverified.
2. **`agent.py`** decides what to test. `build_plan` splits questions across areas by their published weights (`allocate`) and picks a question type for each slot (`format_mix`). Claude only writes the content. It is called with forced tool use (`TOOL` / `CASE_TOOL` schemas) in batches of 5. `_shape` validates each returned question and shuffles its options. Mock mode short-circuits here.
3. **`app.py`** holds exam state, scoring, the question bank, lab endpoints and an auth middleware.
   - Each exam is held in memory (`EXAMS`) and persisted to `sessions/`.
   - New questions are appended to `bank.json`, keeping only the `KEEP` fields. "Use saved questions" rebuilds an exam from the bank with the same weighting and reshuffled options.
   - The answer key never reaches the browser before submit. `_public()` strips it, so keep it that way when adding fields.
   - Scoring gives no partial credit. The score is scaled to 1000 and the pass mark is 700.
4. **`docs.py`** resolves each question's `doc_query` to an exact Microsoft Learn page. It tries the Learn search API, then the Learn MCP endpoint, then falls back to a search link. Results are cached in the data dir.

Frontend: two static pages, `static/index.html` (exam) and `static/labs.html` (labs). There is no build step.

Labs: `labs.json` holds all lab content (scenarios, tasks, steps, checks, clean-up), and the labs page renders it. `terraform/modules/sc500-labs/` has one `labNN_*.tf` per lab. Each lab is gated by `local.lab.<id>`, which comes from `var.enabled_labs`. The lab ids in `labs.json` must match that list in `modules/sc500-labs/main.tf`. Locally, `POST /api/labs/selection` rewrites the `enabled_labs` and `deploy_firewall` lines in `terraform/terraform.tfvars`. When hosted, it returns the lines for the user to paste instead.

## Hosted mode

- On Azure App Service, Entra sign-in is the real gate. `signed_in_only` in `app.py` is a second check. It reads the `x-ms-client-principal-name` header when `SC500_REQUIRE_AUTH=1` and enforces `SC500_ALLOWED_USERS`.
- `SC500_DATA_DIR=/home/data` keeps sessions and the bank across deploys.
- `deploy/azure.sh deploy` refuses to upload the API key until sign-in is enabled.

## Gotchas

- **Bank changes:** the bank drops saved questions whose objective is no longer in the guide. Keep that filtering in place if you change the bank format.
- **Git-ignored:** `.env`, `sessions/`, `doc_links.json` (the Learn link cache), `deploy/.appname`, `deploy/.paused`, `terraform/terraform.tfvars`, `terraform/backend.hcl` and Terraform state.
- **`bank.json` is not ignored.** If it exists, the deploy workflow ships it, and it seeds the hosted bank on the first deploy.
