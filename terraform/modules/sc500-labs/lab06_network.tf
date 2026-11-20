# Lab 6: Implement security for Azure network services.
# The web NSG has one rule that is too open. You find it with Network Watcher and fix it.

resource "azurerm_application_security_group" "web" {
  count               = local.lab.network ? 1 : 0
  name                = "asg-web"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags
}

resource "azurerm_application_security_group" "app" {
  count               = local.lab.network ? 1 : 0
  name                = "asg-app"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags
}

resource "azurerm_network_security_group" "web" {
  count               = local.lab.network ? 1 : 0
  name                = "nsg-web"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags

  security_rule {
    name                       = "Allow-HTTPS-In"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-SSH-In-TOO-OPEN"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "app" {
  count               = local.lab.network ? 1 : 0
  name                = "nsg-app"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags
}

resource "azurerm_subnet_network_security_group_association" "web" {
  count                     = local.lab.network ? 1 : 0
  subnet_id                 = azurerm_subnet.web.id
  network_security_group_id = azurerm_network_security_group.web[0].id
}

resource "azurerm_subnet_network_security_group_association" "app" {
  count                     = local.lab.network ? 1 : 0
  subnet_id                 = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.app[0].id
}

# A storage account reached over a private endpoint.
resource "azurerm_storage_account" "private" {
  count                           = local.lab.network ? 1 : 0
  name                            = "stsc500pe${local.sfx}"
  location                        = local.loc
  resource_group_name             = local.rg
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = true # lab task: turn this off and test name resolution
  tags                            = local.tags
}

resource "azurerm_private_dns_zone" "blob" {
  count               = local.lab.network ? 1 : 0
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = local.rg
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob" {
  count                 = local.lab.network ? 1 : 0
  name                  = "link-vnet-sc500-lab"
  resource_group_name   = local.rg
  private_dns_zone_name = azurerm_private_dns_zone.blob[0].name
  virtual_network_id    = azurerm_virtual_network.lab.id
  tags                  = local.tags
}

resource "azurerm_private_endpoint" "blob" {
  count               = local.lab.network ? 1 : 0
  name                = "pe-stsc500pe-blob"
  location            = local.loc
  resource_group_name = local.rg
  subnet_id           = azurerm_subnet.pe.id
  tags                = local.tags

  private_service_connection {
    name                           = "psc-blob"
    private_connection_resource_id = azurerm_storage_account.private[0].id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob[0].id]
  }
}

# ---- Optional: Azure Firewall Basic (set deploy_firewall = true) ----

resource "azurerm_subnet" "firewall" {
  count                = local.firewall ? 1 : 0
  name                 = "AzureFirewallSubnet"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.20.0/26"]
}

resource "azurerm_subnet" "firewall_mgmt" {
  count                = local.firewall ? 1 : 0
  name                 = "AzureFirewallManagementSubnet"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.21.0/26"]
}

resource "azurerm_public_ip" "firewall" {
  count               = local.firewall ? 1 : 0
  name                = "pip-afw-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.tags
}

resource "azurerm_public_ip" "firewall_mgmt" {
  count               = local.firewall ? 1 : 0
  name                = "pip-afw-mgmt-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.tags
}

resource "azurerm_firewall_policy" "lab" {
  count               = local.firewall ? 1 : 0
  name                = "afwp-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  sku                 = "Basic"
  tags                = local.tags
}

resource "azurerm_firewall" "lab" {
  count               = local.firewall ? 1 : 0
  name                = "afw-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  sku_name            = "AZFW_VNet"
  sku_tier            = "Basic"
  firewall_policy_id  = azurerm_firewall_policy.lab[0].id
  tags                = local.tags

  ip_configuration {
    name                 = "ipconfig"
    subnet_id            = azurerm_subnet.firewall[0].id
    public_ip_address_id = azurerm_public_ip.firewall[0].id
  }

  management_ip_configuration {
    name                 = "mgmt"
    subnet_id            = azurerm_subnet.firewall_mgmt[0].id
    public_ip_address_id = azurerm_public_ip.firewall_mgmt[0].id
  }
}
