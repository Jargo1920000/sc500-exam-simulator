# Lab 4: Implement security for storage accounts.
# Starts weak on purpose: shared key on, public network on, anonymous blob access allowed.

resource "azurerm_storage_account" "lab" {
  count                           = local.lab.storage ? 1 : 0
  name                            = "stsc500lab${local.sfx}"
  location                        = local.loc
  resource_group_name             = local.rg
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = true
  allow_nested_items_to_be_public = true
  public_network_access_enabled   = true
  tags                            = local.tags
}

resource "azurerm_storage_container" "labdata" {
  count                 = local.lab.storage ? 1 : 0
  name                  = "labdata"
  storage_account_id    = azurerm_storage_account.lab[0].id
  container_access_type = "private"
}
