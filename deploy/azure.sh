#!/usr/bin/env bash
# Host the SC-500 exam simulator on Azure App Service.
#
#   ./deploy/azure.sh create    make the web app. No code and no API key yet.
#   (then turn on sign-in in the Azure portal. See the steps this command prints.)
#   ./deploy/azure.sh deploy    upload the code and your API key. Run again after any change.
#   ./deploy/azure.sh logs      watch the app logs.
#   ./deploy/azure.sh status    show the plan tier, app state and Always On.
#   ./deploy/azure.sh pause     move the plan to the Free tier (F1) when you stop studying.
#   ./deploy/azure.sh resume    move it back to the tier it had before pause.
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

PAUSE_FILE="deploy/.paused"   # remembers the tier and Always On setting from before pause

# The plan the app runs on. Read from Azure, so plans made in the portal work too.
plan_name() {
  local id
  id=$(az webapp show -g "$RG" -n "$1" --query appServicePlanId -o tsv)
  echo "${id##*/}"
}

plan_sku() {
  az appservice plan show -g "$RG" -n "$1" --query sku.name -o tsv
}

# Custom domains on the app. The Free tier does not allow them.
custom_domains() {
  az webapp config hostname list -g "$RG" --webapp-name "$1" \
    --query "[?!ends_with(name, '.azurewebsites.net')].name" -o tsv
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
  zip -qr "$ZIP" app.py agent.py docs.py guide.py guide_snapshot.json labs.json requirements.txt static \
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

status)
  APP=$(app_name)
  az account set --subscription "$SUBSCRIPTION"
  P=$(plan_name "$APP")
  echo "App:       $APP ($(az webapp show -g "$RG" -n "$APP" --query state -o tsv))"
  echo "Plan:      $P ($(plan_sku "$P"))"
  echo "Always On: $(az webapp config show -g "$RG" -n "$APP" --query alwaysOn -o tsv)"
  [ -f "$PAUSE_FILE" ] && echo "Paused:    yes. Run './deploy/azure.sh resume' to go back to $(grep '^SKU=' "$PAUSE_FILE" | cut -d= -f2)."
  ;;

pause)
  APP=$(app_name)
  az account set --subscription "$SUBSCRIPTION"
  P=$(plan_name "$APP")
  CURRENT=$(plan_sku "$P")
  if [ "$CURRENT" = "F1" ]; then echo "$P is already on the Free tier (F1)."; exit 0; fi

  DOMAINS=$(custom_domains "$APP")
  if [ -n "$DOMAINS" ]; then
    echo "The Free tier does not allow custom domains, and this app has:"
    echo "$DOMAINS" | sed 's/^/  /'
    echo "Remove them first (portal > $APP > Custom domains), or leave the app on $CURRENT."
    exit 1
  fi

  ALWAYS_ON=$(az webapp config show -g "$RG" -n "$APP" --query alwaysOn -o tsv)
  printf 'SKU=%s\nALWAYS_ON=%s\n' "$CURRENT" "$ALWAYS_ON" > "$PAUSE_FILE"

  # The Free tier does not support Always On, so turn it off before the move.
  [ "$ALWAYS_ON" = "true" ] && az webapp config set -g "$RG" -n "$APP" --always-on false -o none
  echo "Moving $P from $CURRENT to F1."
  if ! az appservice plan update -g "$RG" -n "$P" --sku F1 -o none; then
    [ "$ALWAYS_ON" = "true" ] && az webapp config set -g "$RG" -n "$APP" --always-on true -o none
    rm -f "$PAUSE_FILE"
    echo "The move failed. The plan stays on $CURRENT. If the error mentions quota, the Free tier has none in this region."
    exit 1
  fi
  echo "Paused. Saved exams, the question bank, settings and sign-in are kept."
  echo "The app still works on F1, but sleeps when idle and has a daily CPU limit."
  echo "Run './deploy/azure.sh resume' to go back to $CURRENT."
  ;;

resume)
  APP=$(app_name)
  az account set --subscription "$SUBSCRIPTION"
  P=$(plan_name "$APP")
  TARGET=$( [ -f "$PAUSE_FILE" ] && grep '^SKU=' "$PAUSE_FILE" | cut -d= -f2 || echo "$SKU")
  ALWAYS_ON=$( [ -f "$PAUSE_FILE" ] && grep '^ALWAYS_ON=' "$PAUSE_FILE" | cut -d= -f2 || echo false)
  CURRENT=$(plan_sku "$P")
  if [ "$CURRENT" = "$TARGET" ]; then echo "$P is already on $TARGET."; rm -f "$PAUSE_FILE"; exit 0; fi

  echo "Moving $P from $CURRENT to $TARGET."
  if ! az appservice plan update -g "$RG" -n "$P" --sku "$TARGET" -o none; then
    echo "The move failed. The plan stays on $CURRENT. If the error mentions quota, request more $TARGET quota for this region."
    exit 1
  fi
  [ "$ALWAYS_ON" = "true" ] && az webapp config set -g "$RG" -n "$APP" --always-on true -o none
  rm -f "$PAUSE_FILE"
  echo "Resumed on $TARGET. Allow a minute for the app to start."
  ;;

delete)
  APP=$(app_name)
  az account set --subscription "$SUBSCRIPTION"
  P=$(plan_name "$APP")
  read -r -p "Delete $APP and the plan $P? Type yes: " OK
  [ "$OK" = "yes" ] || exit 0
  az webapp delete -g "$RG" -n "$APP"
  az appservice plan delete -g "$RG" -n "$P" --yes
  rm -f "$NAME_FILE" "$PAUSE_FILE"
  echo "Deleted. Also delete the app registration: Entra admin center > App registrations > $APP."
  ;;

*)
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  ;;
esac
