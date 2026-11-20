# Lab 5: Implement security for databases.
# Entra-only sign-in, so there is no SQL password anywhere. You are the admin.

resource "azurerm_mssql_server" "lab" {
  count                         = local.lab.database ? 1 : 0
  name                          = "sql-sc500-lab-${local.sfx}"
  location                      = local.loc
  resource_group_name           = local.rg
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true
  tags                          = local.tags

  azuread_administrator {
    login_username              = "sc500-lab-admin"
    object_id                   = data.azurerm_client_config.current.object_id
    tenant_id                   = data.azurerm_client_config.current.tenant_id
    azuread_authentication_only = true
  }
}

resource "azurerm_mssql_database" "lab" {
  count                = local.lab.database ? 1 : 0
  name                 = "sqldb-sc500-lab"
  server_id            = azurerm_mssql_server.lab[0].id
  sku_name             = "Basic"
  max_size_gb          = 2
  storage_account_type = "Local"
  tags                 = local.tags
}
