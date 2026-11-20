# Lab 2: Secure secrets and keys by using Azure Key Vault.
# Starts open: public network access on, firewall allows all. You lock it down.

resource "azurerm_key_vault" "lab" {
  count                         = local.lab.keyvault ? 1 : 0
  name                          = "kv-sc500-${local.sfx}"
  location                      = local.loc
  resource_group_name           = local.rg
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  soft_delete_retention_days    = 7
  purge_protection_enabled      = false # keep false, or destroy cannot purge the vault
  public_network_access_enabled = true
  tags                          = local.tags

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }
}

resource "azurerm_monitor_diagnostic_setting" "keyvault" {
  count                      = local.lab.keyvault ? 1 : 0
  name                       = "diag-to-law"
  target_resource_id         = azurerm_key_vault.lab[0].id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.lab.id

  enabled_log {
    category_group = "audit"
  }
}
