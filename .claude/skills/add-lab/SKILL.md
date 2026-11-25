---
name: add-lab
description: Add a new hands-on lab to the SC-500 labs. Use when the user asks to add, create or scaffold a lab. Covers the labs.json entry, the Terraform file with its on/off switch and Purpose tag, the lab_resources output, the README row and the repo checks.
---

# Add a lab

A lab touches six places. Miss one and the lab either fails to deploy, fails Terraform validation, or never shows on the Labs page. Do every step in order.

Before you start, read one existing lab end to end as a model: `terraform/modules/sc500-labs/lab02_keyvault.tf` and the `keyvault` entry in `labs.json`.

## 1. Pick the id and number

- **id:** lowercase letters only, such as `backup`. No digits, dashes or underscores. `app.py` reads the selection back with the regex `"([a-z]+)"`, so any other character breaks the Labs page.
- **n:** the next free number. Today labs run 1 to 12. Numbers 10 (`posture`) and 12 (`copilot`) are portal only and have no `.tf` file.

## 2. Add the labs.json entry

Append an object to `labs` in `labs.json`. It needs every one of these keys:

```json
{
  "id": "backup",
  "n": 13,
  "area": "<area name, exactly as in the study guide>",
  "section": "<skill group name, exactly as in the study guide>",
  "terraform": true,
  "scenario": "Two or three sentences. Say what starts out weak and what the learner must fix.",
  "deploys": ["Recovery Services vault rsv-sc500-<suffix> (soft delete off)"],
  "cost": "Free | Pennies | About £N a month",
  "cleanup": ["Anything terraform destroy cannot remove on its own."],
  "tasks": [
    {
      "objective": "<one study guide objective, exactly as written>",
      "kind": "azure",
      "steps": ["Short, active sentences. One action each."],
      "note": null,
      "check": "How the learner proves the task is done."
    }
  ]
}
```

- **Exact names:** `area`, `section` and each task `objective` must match the study guide text exactly. The **Practice questions on this lab** button filters exam questions by `section`, so a typo gives an empty exam.
- **One task per objective:** add one task for each objective in that section.
- **`kind`:** `azure` (uses the deployed resources), `tenant` (Entra or Microsoft 365, may need a licence) or `study` (walk the wizard, deploy nothing). The page defines no other kinds.
- **Portal-only labs:** set `"terraform": false` and skip steps 3 to 5.

## 3. Write the Terraform file

Create `terraform/modules/sc500-labs/labNN_<id>.tf`, with `NN` as the two-digit lab number. Follow these rules:

- **Header:** start with a comment that gives the lab number, the section name, and what starts out weak on purpose.
- **Switch:** give every resource `count = local.lab.<id> ? 1 : 0`, and refer to it elsewhere as `azurerm_x.y[0]`.
- **Tags:** set `tags = local.tags` on every resource that takes tags. `local.tags` already adds `Purpose = SC-500 Lab`. Never write the tag by hand.
- **Placement:** use `local.rg`, `local.loc`, and `local.sfx` for unique names, such as `"rsv-sc500-${local.sfx}"`. Never hard-code a resource group, region, subscription ID or tenant ID. Get the tenant ID from `data.azurerm_client_config.current.tenant_id`.
- **Shared resources:** reuse what `main.tf` already creates (the Log Analytics workspace `azurerm_log_analytics_workspace.lab` and the virtual network `azurerm_virtual_network.lab`) instead of creating new ones.
- **Clean destroy:** keep anything that would block `terraform destroy` turned off, such as purge protection or delete locks. Leave a short comment saying why.
- **Built-in IDs:** reference built-in policy definitions as `/providers/Microsoft.Authorization/policyDefinitions/<guid>`. `scripts/check_secrets.sh` allows that form only. Any other GUID fails the check.

## 4. Register the switch

Add the id to both lists. They must match each other and `labs.json`.

- `terraform/modules/sc500-labs/main.tf`: the `lab = { for l in [ ... ] ... }` list in `locals`.
- `terraform/modules/sc500-labs/variables.tf`: the `contains([ ... ], l)` list in the `enabled_labs` validation, and the names in its `error_message`.

## 5. Add the output

In `terraform/modules/sc500-labs/outputs.tf`, add one line to `lab_resources`. Keep the column alignment.

```hcl
backup     = local.lab.backup ? { recovery_vault = azurerm_recovery_services_vault.backup[0].name } : null
```

List only the names the learner needs to find in the portal. The root `terraform/outputs.tf` passes the whole map through, so it needs no change.

## 6. Update the README

In `README.md`, under **Using the labs**, add a row to the lab table:

```markdown
| 13 | Backup | Recovery Services vault with soft delete off | Free |
```

- **Counts:** fix every count that changes. The line under the title says "12 labs cover all 87 objectives", and the project layout table says "The 12 labs".
- **Style:** plain English, active voice, no em dashes.

## 7. Run the checks

Run all of these and fix any failure before you report back:

```bash
# labs.json is valid, ids are unique and lowercase, and names match the study guide snapshot
python3 -c "
import json, re
labs = json.load(open('labs.json'))['labs']
guide = json.load(open('guide_snapshot.json'))['areas']
secs = {(a['name'], s['name']): set(s['objectives']) for a in guide for s in a['sections']}
ids = [l['id'] for l in labs]
assert len(ids) == len(set(ids)), 'duplicate id'
assert len({l['n'] for l in labs}) == len(labs), 'duplicate n'
for l in labs:
    assert re.fullmatch('[a-z]+', l['id']), 'bad id ' + l['id']
    key = (l['area'], l['section'])
    assert key in secs, 'area/section not in guide: %s' % (key,)
    for t in l['tasks']:
        assert t['kind'] in ('azure', 'tenant', 'study'), 'bad kind in ' + l['id']
        assert t['objective'] in secs[key], 'objective not in guide: ' + t['objective']
print('labs.json OK:', len(labs), 'labs')
"

# Terraform formats and validates (no Azure sign-in needed)
cd terraform && terraform fmt -recursive -check && terraform init -backend=false -input=false >/dev/null && terraform validate; cd ..

# Repo checks
python3 scripts/check_deploy_lists.py
bash scripts/check_secrets.sh

# The Labs page loads the new lab
SC500_MOCK=1 python3 app.py   # open http://127.0.0.1:8500/labs and confirm the lab shows
```

- **Guide check failures:** if the study guide snapshot is older than the live guide, the check may fail on a real new name. Check the live page at https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-500 before you change a name to fit the snapshot.
- **Deploying:** do not run `terraform apply`. The user deploys from the Labs page.
