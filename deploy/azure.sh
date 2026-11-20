#!/usr/bin/env bash
# Host the SC-500 exam simulator on Azure App Service.
#
#   ./deploy/azure.sh create    make the web app. No code and no API key yet.
#   (then turn on sign-in in the Azure portal. See the steps this command prints.)
#   ./deploy/azure.sh deploy    upload the code and your API key. Run again after any change.
#   ./deploy/azure.sh logs      watch the app logs.
#   ./deploy/azure.sh delete    remove the web app and its plan.
set -euo pipefail

SUBSCRIPTION="${SUBSCRIPTION:-$(az account show --query id -o tsv)}"   # defaults to your current az login subscription
RG="${RG:-rg-sc500-exam-app}"     # resource group for the web app. Created if missing
LOCATION="${LOCATION:-uksouth}"   # if you hit an App Service quota error, try LOCATION=ukwest
PLAN="asp-sc500-exam-app"
SKU="${SKU:-B1}"                       # B1 costs about 10 pounds a month. Try SKU=F1 for the free tier.
TAGS=(Purpose="SC-500 Exam App")       # not the lab tag, so the lab destroy check ignores it

cd "$(dirname "$0")/.."
NAME_FILE="deploy/.appname"

app_name() {
  [ -f "$NAME_FILE" ] || { echo "Run './deploy/azure.sh create' first."; exit 1; }
  cat "$NAME_FILE"
}

case "${1:-}" in
create)
  az account set --subscription "$SUBSCRIPTION"
  if [ -f "$NAME_FILE" ]; then APP=$(cat "$NAME_FILE"); else APP="app-sc500-exam-$(openssl rand -hex 3)"; fi
  ME=$(az ad signed-in-user show --query userPrincipalName -o tsv)
  az group create -n "$RG" -l "$LOCATION" --tags "${TAGS[@]}" -o none
  echo "Creating $APP in $RG ($LOCATION). Only $ME will be allowed in."

  az appservice plan create -g "$RG" -n "$PLAN" -l "$LOCATION" --is-linux --sku "$SKU" --tags "${TAGS[@]}" -o none
  az webapp create -g "$RG" -p "$PLAN" -n "$APP" --runtime "PYTHON:3.12" --https-only true --tags "${TAGS[@]}" -o none
  echo "$APP" > "$NAME_FILE"   # save the name only once the app exists
  az webapp config set -g "$RG" -n "$APP" -o none \
    --startup-file "python -m uvicorn app:app --host 0.0.0.0 --port 8000" \
    --ftps-state Disabled --min-tls-version 1.2
  az webapp config appsettings set -g "$RG" -n "$APP" -o none --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true ENABLE_ORYX_BUILD=true \
    SC500_HOSTED=1 SC500_REQUIRE_AUTH=1 SC500_DATA_DIR=/home/data \
    SC500_ALLOWED_USERS="$ME"

  HOST=$(az webapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv)
  cat <<MSG

Web app created: https://$HOST

NOW TURN ON SIGN-IN, before you deploy the code:
  1. Azure portal > $APP > Settings > Authentication > Add identity provider.
  2. Identity provider: Microsoft.  Tenant type: Workforce configuration (current tenant).
  3. App registration type: Create new app registration.
  4. Supported account types: Current tenant - Single tenant.
  5. Restrict access: Require authentication.
  6. Unauthenticated requests: HTTP 302 Found redirect.
  7. Select Add.

Then run:  ./deploy/azure.sh deploy
MSG
  ;;

deploy)
  APP=$(app_name)
  az account set --subscription "$SUBSCRIPTION"
  if [ "$(az webapp auth show -g "$RG" -n "$APP" --query "platform.enabled || properties.platform.enabled || enabled" -o tsv 2>/dev/null)" != "true" ]; then
    echo "Sign-in is not turned on for $APP yet. Do the portal steps from 'create' first."
    echo "To deploy anyway, run:  FORCE=1 ./deploy/azure.sh deploy"
    [ "${FORCE:-}" = "1" ] || exit 1
  fi

  KEY=$(grep -E '^ANTHROPIC_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
  [ -n "$KEY" ] || { echo "No ANTHROPIC_API_KEY found in .env"; exit 1; }
  SETTINGS=(ANTHROPIC_API_KEY="$KEY")
  MODEL=$(grep -E '^ANTHROPIC_MODEL=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ' || true)
  [ -z "$MODEL" ] || SETTINGS+=(ANTHROPIC_MODEL="$MODEL")
  az webapp config appsettings set -g "$RG" -n "$APP" -o none --settings "${SETTINGS[@]}"

  ZIP="$(mktemp -d)/sc500-app.zip"
  zip -qr "$ZIP" app.py agent.py guide.py guide_snapshot.json labs.json requirements.txt static \
    $( [ -f bank.json ] && echo bank.json )
  echo "Uploading the code. The build takes a few minutes."
  az webapp deploy -g "$RG" -n "$APP" --src-path "$ZIP" --type zip -o none
  rm -f "$ZIP"
  echo "Done: https://$(az webapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv)"
  ;;

logs)
  APP=$(app_name)
  az webapp log config -g "$RG" -n "$APP" --docker-container-logging filesystem -o none
  az webapp log tail -g "$RG" -n "$APP"
  ;;

delete)
  APP=$(app_name)
  read -r -p "Delete $APP and the plan $PLAN? Type yes: " OK
  [ "$OK" = "yes" ] || exit 0
  az webapp delete -g "$RG" -n "$APP"
  az appservice plan delete -g "$RG" -n "$PLAN" --yes
  rm -f "$NAME_FILE"
  echo "Deleted. Also delete the app registration: Entra admin center > App registrations > $APP."
  ;;

*)
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  ;;
esac
