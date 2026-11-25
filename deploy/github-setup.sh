#!/usr/bin/env bash
# One-time setup so GitHub Actions can deploy the exam app with no stored password.
#
# It creates (or reuses):
#   - an Entra app registration and service principal: github-sc500-exam-simulator-deploy
#   - a federated credential that trusts only this repo's main branch
#   - a Website Contributor role assignment on the one web app, nothing wider
# Then it prints the values to add in GitHub, or sets them for you if the gh CLI is signed in.
#
# Run from the project folder:   bash deploy/github-setup.sh
# Override any value:            REPO=owner/name RG=my-rg APP=my-app bash deploy/github-setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

SUBSCRIPTION="${SUBSCRIPTION:-$(az account show --query id -o tsv)}"
# owner/repo from your git remote. It must match GitHub's casing exactly. Override with REPO=owner/name.
REPO="${REPO:-$(git remote get-url origin 2>/dev/null | sed -E 's#(\.git)?$##; s#^.*github\.com[:/]##')}"
BRANCH="${BRANCH:-main}"
RG="${RG:-$(cat deploy/.rg 2>/dev/null || echo rg-sc500-exam-app)}"
APP="${APP:-$(cat deploy/.appname 2>/dev/null || true)}"
NAME="github-sc500-exam-simulator-deploy"

[ -n "$APP" ] || { echo "No web app name. Run with APP=<your-app-name> bash deploy/github-setup.sh"; exit 1; }
[ -n "$REPO" ] || { echo "No GitHub repo found. Run with REPO=<owner>/<repo> bash deploy/github-setup.sh"; exit 1; }

az account set --subscription "$SUBSCRIPTION"
TENANT=$(az account show --query tenantId -o tsv)
SCOPE=$(az webapp show -g "$RG" -n "$APP" --query id -o tsv) \
  || { echo "Web app $APP not found in $RG. Set RG= and APP= to match."; exit 1; }

echo "Repo:    $REPO ($BRANCH)"
echo "Web app: $APP in $RG"

APP_ID=$(az ad app list --display-name "$NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$NAME" --sign-in-audience AzureADMyOrg --query appId -o tsv)
  echo "Created app registration $NAME"
else
  echo "Reusing app registration $NAME"
fi

SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv 2>/dev/null || true)
if [ -z "$SP_ID" ]; then
  SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
  echo "Created service principal"
fi

SUBJECT="repo:${REPO}:ref:refs/heads/${BRANCH}"
if az ad app federated-credential list --id "$APP_ID" --query "[?subject=='$SUBJECT'].name" -o tsv | grep -q .; then
  echo "Federated credential for $SUBJECT already exists"
else
  az ad app federated-credential create --id "$APP_ID" -o none --parameters "{
    \"name\": \"github-${BRANCH}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"${SUBJECT}\",
    \"description\": \"GitHub Actions deploy from ${REPO} ${BRANCH}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"
  echo "Added federated credential for $SUBJECT"
fi

# The role can fail for a minute while a new service principal spreads. Retry a few times.
for i in 1 2 3 4 5; do
  if az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
       --role "Website Contributor" --scope "$SCOPE" -o none 2>/dev/null; then
    echo "Granted Website Contributor on $APP only"; break
  fi
  [ "$i" = 5 ] && { echo "Could not assign the role. You need Owner or User Access Administrator on $RG."; exit 1; }
  sleep 15
done

cat <<MSG

Add these in GitHub: $REPO > Settings > Secrets and variables > Actions

  Secrets (Secrets tab > New repository secret)
    AZURE_CLIENT_ID        $APP_ID
    AZURE_TENANT_ID        $TENANT
    AZURE_SUBSCRIPTION_ID  $SUBSCRIPTION

  Variables (Variables tab > New repository variable)
    AZURE_WEBAPP_NAME      $APP
    AZURE_RESOURCE_GROUP   $RG
MSG

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  read -r -p "The gh CLI is signed in. Set these in GitHub for you now? (y/n) " OK
  if [ "$OK" = "y" ]; then
    gh secret set AZURE_CLIENT_ID -R "$REPO" -b "$APP_ID"
    gh secret set AZURE_TENANT_ID -R "$REPO" -b "$TENANT"
    gh secret set AZURE_SUBSCRIPTION_ID -R "$REPO" -b "$SUBSCRIPTION"
    gh variable set AZURE_WEBAPP_NAME -R "$REPO" -b "$APP"
    gh variable set AZURE_RESOURCE_GROUP -R "$REPO" -b "$RG"
    echo "Done. Run the workflow from the Actions tab, or push a change to main."
  fi
fi
