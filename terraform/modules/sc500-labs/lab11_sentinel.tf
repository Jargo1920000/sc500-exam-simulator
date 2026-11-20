# Lab 11: Implement activity and event collection in Microsoft Sentinel.
# Turns Microsoft Sentinel on for the shared Log Analytics workspace.

resource "azurerm_sentinel_log_analytics_workspace_onboarding" "lab" {
  count        = local.lab.sentinel ? 1 : 0
  workspace_id = azurerm_log_analytics_workspace.lab.id
}

# Labs 10 (posture) and 12 (copilot) are portal-only. They deploy nothing.
