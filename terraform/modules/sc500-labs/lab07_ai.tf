# Lab 7: Implement security for AI.
# A Foundry (AI Services) resource with key sign-in and public access left on.
# No model is deployed, so it costs nothing until you deploy one in the lab.

resource "azurerm_cognitive_account" "foundry" {
  count                         = local.lab.ai ? 1 : 0
  name                          = "ais-sc500-lab-${local.sfx}"
  location                      = local.loc
  resource_group_name           = local.rg
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "ais-sc500-lab-${local.sfx}"
  local_auth_enabled            = true # lab task: turn key sign-in off
  public_network_access_enabled = true
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_monitor_diagnostic_setting" "foundry" {
  count                      = local.lab.ai ? 1 : 0
  name                       = "diag-to-law"
  target_resource_id         = azurerm_cognitive_account.foundry[0].id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.lab.id

  enabled_log {
    category_group = "audit"
  }
}
