# SC-500 Exam Simulator and Labs

A study tool for Microsoft exam **SC-500: Implementing End-to-End Security Controls for Cloud and AI Workloads**.

It has two parts:

- **Practice exams.** The app reads the official SC-500 study guide, then asks Claude to write Microsoft-style questions for each objective. You answer one question at a time and get a scored review at the end.
- **Hands-on labs.** 12 labs cover all 87 objectives in the study guide. Terraform deploys the starting resources to Azure, you fix what is wrong, then you destroy it all.

You can run it on your own computer, or host it on Azure App Service behind Microsoft Entra sign-in.

> This is an unofficial practice tool. It is not linked to Microsoft. An AI model writes the questions from the public study guide. They are not real exam questions, and the practice score is not Microsoft's scoring.

---

## Contents

1. [Features](#features)
2. [How it works](#how-it-works)
3. [Project layout](#project-layout)
4. [Run it on your computer](#run-it-on-your-computer)
5. [Settings](#settings)
6. [Using the exams](#using-the-exams)
7. [Tokens, cost and the question bank](#tokens-cost-and-the-question-bank)
8. [Using the labs](#using-the-labs)
9. [Host it on Azure](#host-it-on-azure)
10. [Deploy from GitHub Actions](#deploy-from-github-actions)
11. [Updating the app](#updating-the-app)
12. [Troubleshooting](#troubleshooting)
13. [Security notes](#security-notes)
14. [Credits](#credits)
15. [Licence](#licence)

---

## Features

**Exams**

| Mode | Questions | When you see answers |
| --- | --- | --- |
| Full Exam | 50 | After you submit |
| Quick Exam | 12 | After you submit |
| Case Study | 1 case, 6 linked questions | After you submit |
| Practice | 10 | After each question, with a Microsoft Learn link |

- Question types: single answer, multiple answer, Yes/No solution checks, and ordering.
- Skip, flag, go back and change answers. A status panel shows answered, unanswered, flagged and changed.
- The answer key stays on the server until you submit. The browser never sees it during an exam.
- The review shows a score out of 1000, pass or fail at 700, results per objective area, every answer with an explanation, and study links for what you missed.
- Retake with new questions, or with saved questions for free.

**Labs**

- One lab per skill group in the study guide. One task per objective.
- A Terraform module with a switch for each lab, so you deploy only what you need.
- Resources start with weak settings on purpose. The tasks walk you through fixing them.
- Tick off steps and tasks as you go. Progress saves in your browser.
- Each lab has a button for practice questions on just that skill group.
- A destroy page with a clean-up checklist and the commands to remove everything.

---

## How it works

```
                 +----------------------------+
                 |  Microsoft Learn           |
                 |  SC-500 study guide        |
                 +-------------+--------------+
                               | 1. read skills and weights
                               v
 Browser  <---->  FastAPI app (app.py)
                    |   2. pick objectives by weight (agent.py)
                    |   3. ask Claude to write questions
                    v
                 Claude API  ---> questions, answer key, explanations
                    |
                    v
           sessions/ (exams)    bank.json (saved questions)
```

1. **Scope check.** Before each exam, `guide.py` loads the live study guide and reads the four objective areas, their weights and every objective. If the page can't be reached, the app asks before it uses the saved copy in `guide_snapshot.json`, and labels that exam as unverified.
2. **Plan.** `agent.py` splits the questions across the four areas by their published weights. It picks one objective and one question type for each slot. The code decides what to test, so every question maps to the guide.
3. **Write.** Claude writes each question, its answer key and its explanation. The app checks each one (option count, answer count) and shuffles the options.
4. **Store.** The exam is saved in `sessions/`, and the new questions are saved to `bank.json` for reuse.

---

## Project layout

| Path | What it is |
| --- | --- |
| `app.py` | Web server, exam state, scoring, question bank, lab endpoints, sign-in check |
| `agent.py` | Question planning and the Claude API calls |
| `guide.py` | Loads and reads the Microsoft Learn study guide |
| `guide_snapshot.json` | Saved copy of the study guide, used only for unverified sets |
| `labs.json` | The 12 labs: scenarios, tasks, steps, checks and clean-up |
| `static/index.html` | Exam page |
| `static/labs.html` | Labs page |
| `requirements.txt` | Python packages |
| `.env.example` | Template for your settings. Copy it to `.env` |
| `terraform/` | Root Terraform config: backend, provider, variables |
| `terraform/modules/sc500-labs/` | The labs module. One file per lab |
| `deploy/azure.sh` | Creates, deploys and deletes the hosted app on Azure |
| `deploy/github-setup.sh` | One-time setup for GitHub Actions deploys |
| `.github/workflows/deploy.yml` | Deploys to Azure on each push to `main` |

Files that stay on your computer and never go in Git: `.env`, `.venv/`, `sessions/`, `deploy/.appname`, and Terraform state.

---

## Run it on your computer

You need Python 3.10 or newer and an Anthropic API key.

**1. Get an API key**

Sign in at [platform.claude.com](https://platform.claude.com), open **Settings > API keys**, and create a key. Copy it straight away, because the Console shows it only once. API use is billed from your Console credit, separate from any Claude subscription, so add a small amount of credit.

**2. Set up the project (macOS)**

```bash
git clone https://github.com/Jargo1920000/sc500-exam-simulator.git
cd sc500-exam-simulator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
open -e .env        # paste your API key, then save
```

On macOS, use the virtual environment. Running `pip install` outside it gives an "externally-managed-environment" error.

**3. Start it**

```bash
source .venv/bin/activate     # each new Terminal window
python app.py
```

Open http://127.0.0.1:8500. The app listens on your own computer only.

**Try it with no API key:** set `SC500_MOCK=1` in `.env`. You get placeholder questions and no AI calls.

---

## Settings

Put these in `.env` on your computer. On Azure they are app settings.

| Setting | Default | What it does |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | none | Your API key. Needed unless mock mode is on |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model that writes questions. `claude-opus-5-5` writes more careful questions at a higher cost |
| `SC500_PORT` | `8500` | Local port |
| `SC500_MOCK` | off | `1` for placeholder questions |
| `SC500_HOSTED` | off | `1` when running on Azure |
| `SC500_REQUIRE_AUTH` | off | `1` to refuse requests that App Service sign-in has not passed |
| `SC500_ALLOWED_USERS` | none | Comma-separated sign-in names allowed in, such as `you@domain.com` |
| `SC500_DATA_DIR` | project folder | Where `sessions/` and `bank.json` live. `/home/data` on Azure |

---

## Using the exams

1. Pick a mode. Each card has two buttons:
   - **Write new questions (uses tokens)** asks Claude for fresh questions.
   - **Use saved questions (free)** builds the exam from your question bank.
2. Answer each question and select **Save and next**. Multiple-answer questions tell you how many to pick.
3. Use **Flag**, **Skip** and the number grid to move around.
4. Select **Submit exam** when done. Unanswered questions count as wrong.

**Scoring.** Correct answers divided by total, scaled to 1000. Pass mark 700. Multiple-answer and ordering questions need every part right. There is no partial credit. Microsoft uses its own scaled scoring, so treat this as a guide.

**Practice Mode** checks each answer as you go and shows the correct answer, the reason and a Microsoft Learn link. Because you see answers, its score is not a readiness check. Use Quick or Full for that.

---

## Tokens, cost and the question bank

- Only **Write new questions** uses tokens. Answering, checking, reviewing and the whole Labs page cost nothing.
- A Quick or Practice exam makes about 3 API calls. A Full exam makes about 10. A case study makes 1.
- The header shows the model in use. The terminal prints the model and token count for each call:
  ```
  [tokens] model claude-sonnet-5-5 | call 1: in 1,234 / out 5,678 | total: ...
  ```
- Every new question is saved to `bank.json`. **Use saved questions** picks from it, keeps the study guide weighting, and shuffles the options so you can't learn positions. Saved questions whose objective has left the guide are dropped.
- The free button stays grey until you have enough saved: 50 for Full, 12 for Quick, 10 for Practice, 1 case study for Case Study.
- Check your account spend in the Claude Console usage pages.

---

## Using the labs

Open http://127.0.0.1:8500/labs, or select **Labs** in the header. The page has four steps.

### 1. Set up

You need Terraform 1.6 or newer and the Azure CLI.

```bash
terraform -version
az version
az login
az account set --subscription <your-subscription-id>
```

- **Lab resource group.** Terraform deploys into an existing resource group and never deletes it. Create it once:
  ```bash
  az group create -n rg-sc500-lab -l uksouth
  ```
  To use another name, set `resource_group_name` in `terraform.tfvars`.
- **Remote state.** Terraform keeps state in Azure Storage. Make a storage account once if you have none, and give yourself **Storage Blob Data Contributor** on it:
  ```bash
  az group create -n rg-sc500-tfstate -l uksouth
  az storage account create -g rg-sc500-tfstate -n <unique-name> -l uksouth \
    --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false
  az storage container create --account-name <unique-name> -n tfstate --auth-mode login
  ```
- **Your settings.** Two files hold your values. Both are git-ignored:
  ```bash
  cd terraform
  cp backend.hcl.example backend.hcl                 # set storage_account_name
  cp terraform.tfvars.example terraform.tfvars       # set subscription_id
  ```
- **Role.** You need Owner, or Contributor plus User Access Administrator. The governance lab creates a policy definition and a custom role.
- **Init:**
  ```bash
  terraform init -backend-config=backend.hcl
  ```

### 2. Choose and deploy

Tick the labs you want and select **Save to terraform.tfvars**. That writes one line, such as `enabled_labs = ["keyvault", "storage"]`. Nothing deploys until you run:

```bash
terraform plan -out lab.tfplan
terraform apply lab.tfplan
terraform output lab_resources
```

Every resource goes to the resource group `rg-sc500-lab` in UK South with the tag `Purpose = SC-500 Lab`. Terraform reads the resource group and never deletes it.

| # | Lab | Deploys | Rough cost |
| --- | --- | --- | --- |
| 1 | Entra ID access | Managed identity | Free |
| 2 | Key Vault | Vault with an open firewall, audit logs | Pennies |
| 3 | Governance | Policies, custom role, Recovery Services vault | Free |
| 4 | Storage | Storage account with weak settings | Pennies |
| 5 | Databases | Azure SQL, Entra-only sign-in, Basic database | About £4 a month |
| 6 | Networking | NSGs with a bad rule, ASGs, private endpoint. Optional Azure Firewall | About £6 a month. Firewall extra, by the hour |
| 7 | AI | Foundry (AI Services) resource, no model deployed | Free until you deploy a model |
| 8 | Servers and VMs | Small Linux VM, no public IP, daily shutdown | About £7 a month if left on |
| 9 | App platform | App Service, container registry, API Management, WAF policy | About £14 a month |
| 10 | Posture | Nothing. Portal only | Paid Defender plans while on |
| 11 | Sentinel | Sentinel on the shared workspace | Per GB ingested |
| 12 | Security Copilot | Nothing. Capacity made by hand | Bills hourly. Delete the same day |

Costs are rough. Check the Azure pricing calculator.

**Lab 9 and App Service quota.** If your subscription has no B1 quota in UK South, change `sku_name` in `terraform/modules/sc500-labs/lab09_apps.tf` from `"B1"` to `"F1"`. Every Lab 9 task still works on F1.

**Azure Firewall** is off by default. Tick **Deploy Azure Firewall** only while you do that task, then untick it and apply again.

**Remove one lab:** untick it, save, then plan and apply. Terraform removes only that lab.

### 3. Do the labs

Each task is one study guide objective. Task tags:

- **Azure:** uses your lab resources.
- **Tenant:** Entra or Microsoft 365 work. Some need licences, such as Entra ID P2, Purview or Agent 365.
- **Walkthrough:** read and walk the portal wizard. Deploys nothing, because the real thing costs too much to leave running.

### 4. Destroy

1. Work through the clean-up checklist on the page. Locks, Azure Bastion and anything made by hand can block destroy.
2. Destroy:
   ```bash
   cd terraform
   terraform plan -destroy
   terraform destroy
   ```
3. Check nothing is left:
   ```bash
   az resource list -g rg-sc500-lab --query "[?tags.Purpose=='SC-500 Lab'].{name:name, type:type}" -o table
   ```
4. Turn off any Defender for Cloud plans you enabled, and delete any Security Copilot capacity.

**Never** turn on Key Vault purge protection or lock Recovery Services vault immutability in a lab. Neither can be undone.

---

## Host it on Azure

The hosted app runs on Azure App Service (Linux, Python 3.12) behind Microsoft Entra sign-in.

Check your App Service quota before you start. Some subscriptions have a limit of 0 in some regions, even when the Quotas page shows more. If you get a quota error, try another region, such as `ukwest`.

### Option A: the deploy script

```bash
az login
bash deploy/azure.sh create
```

- The script uses the subscription you're signed in to. Set `SUBSCRIPTION=<id>` to pick another.
- `LOCATION` defaults to `uksouth`. Set `LOCATION=ukwest` if you hit a quota error.
- `SKU` defaults to `B1` (about £10 a month). `F1` is free but sleeps when idle.
- `RG` defaults to `rg-sc500-exam-app`. The script creates it if it doesn't exist.

The script creates the plan and web app, sets HTTPS only, TLS 1.2, FTP off, the startup command and the app settings. It also puts your Azure sign-in name in `SC500_ALLOWED_USERS`.

Then turn on sign-in (see below) and deploy:

```bash
bash deploy/azure.sh deploy
```

### Option B: the Azure portal

1. **App Services > Create > Web App.** Code, Python 3.12, Linux, your region and plan. Tag `Purpose = SC-500 Exam App`. Application Insights off.
2. **Configuration:**
   - Startup command: `python -m uvicorn app:app --host 0.0.0.0 --port 8000`
   - HTTPS Only on, FTP disabled, minimum TLS 1.2
3. **Environment variables > App settings:**

   | Name | Value |
   | --- | --- |
   | `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
   | `ENABLE_ORYX_BUILD` | `true` |
   | `SC500_HOSTED` | `1` |
   | `SC500_REQUIRE_AUTH` | `1` |
   | `SC500_DATA_DIR` | `/home/data` |
   | `SC500_ALLOWED_USERS` | your sign-in name |

4. Save the app name for the script, then deploy:
   ```bash
   echo "<your-app-name>" > deploy/.appname
   RG=<your-resource-group> bash deploy/azure.sh deploy
   ```

### Turn on sign-in

In the portal, open the web app, then **Settings > Authentication > Add identity provider**:

- Identity provider: **Microsoft**
- Tenant type: **Workforce configuration (current tenant)**
- App registration type: **Create new app registration**
- Supported account types: **Current tenant, single tenant**
- Restrict access: **Require authentication**
- Unauthenticated requests: **HTTP 302 Found redirect**

`deploy` refuses to upload your API key until sign-in is on.

### Other script commands

```bash
bash deploy/azure.sh logs      # stream the app logs
bash deploy/azure.sh delete    # remove the web app and its plan
```

After `delete`, also remove the app registration in the Entra admin center.

### How the hosted copy differs

- Saved exams and the question bank live in `/home/data`, which survives restarts and deploys. The first deploy copies your local `bank.json` as a starting point.
- It can't edit `terraform.tfvars` on your computer. The Labs page shows the lines to paste instead. You still run Terraform locally.
- Lab progress saves per browser.

---

## Deploy from GitHub Actions

`.github/workflows/deploy.yml` deploys the app on each push to `main` that changes app files. You can also run it by hand from the **Actions** tab.

It signs in to Azure with OpenID Connect. GitHub gives the job a short-lived token, and Entra trusts that token only for this repo's `main` branch. No password or client secret is stored in GitHub.

### One-time setup

1. Make sure the web app exists and `deploy/.appname` holds its name.
2. Run:
   ```bash
   bash deploy/github-setup.sh
   ```
   It creates or reuses:
   - the app registration `github-sc500-exam-simulator-deploy` and its service principal
   - a federated credential for `repo:<owner>/<repo>:ref:refs/heads/main`, read from your git remote
   - a **Website Contributor** role on the web app only
3. Add the values it prints in GitHub, under **Settings > Secrets and variables > Actions**:

   | Type | Name |
   | --- | --- |
   | Secret | `AZURE_CLIENT_ID` |
   | Secret | `AZURE_TENANT_ID` |
   | Secret | `AZURE_SUBSCRIPTION_ID` |
   | Variable | `AZURE_WEBAPP_NAME` |
   | Variable | `AZURE_RESOURCE_GROUP` |

   If the GitHub CLI (`gh`) is signed in, the script offers to set them for you.
4. Open **Actions > Deploy to Azure App Service > Run workflow** to test.

Until `AZURE_WEBAPP_NAME` is set, the workflow is skipped, not failed.

The workflow ships code only. Your Anthropic API key and other app settings stay in Azure.

---

## Updating the app

1. Test locally first:
   ```bash
   source .venv/bin/activate
   python app.py
   ```
2. Ship it, either way:
   - **With GitHub Actions:** commit and push to `main`.
   - **By hand:** `RG=<your-resource-group> bash deploy/azure.sh deploy`
3. Allow two to three minutes for the build, then refresh.

A deploy keeps saved exams, the question bank, app settings and sign-in. A hand deploy also resends your API key from `.env`.

If you add a new file the app needs, add it to the zip list in both `deploy/azure.sh` and `.github/workflows/deploy.yml`.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `pip: command not found` | Use `python3 -m pip`, or work inside the virtual environment |
| `externally-managed-environment` on macOS | Create and activate `.venv` first |
| `tool_choice ... not supported for this model` | Update `agent.py`. The current version asks for the tool call in the prompt |
| Quota error: `Current Limit (B1 App Service instances): 0` | Try another region (`LOCATION=ukwest`), try `SKU=F1`, or raise a support request for App Service quota |
| `ResourceNotFound` for the web app | `deploy/.appname` or `RG` doesn't match. Fix the name in `.appname` and pass `RG=` |
| "Sign-in is not turned on" from `deploy` | Add the Microsoft identity provider in the portal first |
| 503 Service Unavailable | Run `deploy/azure.sh logs` and look for the lines below |
| Log: `No module named uvicorn` | The build didn't run. Set `SCM_DO_BUILD_DURING_DEPLOYMENT=true` and `ENABLE_ORYX_BUILD=true`, then deploy again |
| Log: `didn't respond to HTTP pings on port 8000` | Set the startup command shown above |
| "That account is not on the allowed list" | Set `SC500_ALLOWED_USERS` to the name the message shows |
| 500 error, log: `static/index.html does not exist` | The file is missing locally. Restore it and deploy again |
| Actions: "No matching federated identity record" | The repo, owner or branch in the federated credential doesn't match GitHub exactly. Casing matters |
| Actions: `AuthorizationFailed` | The role assignment is missing or still spreading. Wait a few minutes or rerun `github-setup.sh` |
| `terraform destroy` fails | Remove locks, Azure Bastion and anything made by hand, then try again |

---

## Security notes

- **Never commit `.env`.** It holds your API key. `.gitignore` excludes it. Check `git status` before your first commit.
- **Keep your values out of Git.** Your subscription ID and storage names go in `terraform.tfvars` and `backend.hcl`, which are git-ignored. Don't hard-code them in tracked files.
- **The hosted app has two locks.** App Service sign-in blocks anyone not signed in to your tenant. The app then lets in only the names in `SC500_ALLOWED_USERS`.
- **CI has no stored secret.** GitHub Actions uses OIDC, trusted for one repo and one branch, with a role on one web app.
- **Lab resources are weak on purpose.** Deploy them only to a lab subscription, and destroy them when you finish.

---

## Credits

- **John Jackson** ([@Jargo1920000](https://github.com/Jargo1920000)): idea, design, testing, Azure deployment
- **Claude** (Anthropic): pair programmer for the app, labs, Terraform and deploy scripts

---

## Licence

MIT. See [LICENSE](LICENSE).
