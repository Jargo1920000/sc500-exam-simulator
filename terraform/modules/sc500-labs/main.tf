# Shared pieces that every lab can use. They cost nothing while idle.

data "azurerm_resource_group" "lab" {
  name = var.resource_group_name
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  sfx = random_string.suffix.result
  rg  = data.azurerm_resource_group.lab.name
  loc = var.location
  # Start from the resource group tags: a policy copies them onto every resource, so setting them here stops drift.
  tags = merge(data.azurerm_resource_group.lab.tags, var.tags, { Purpose = "SC-500 Lab" })

  # One on/off switch per lab.
  lab = { for l in [
    "identity", "keyvault", "governance", "storage", "database", "network",
    "ai", "vm", "apps", "posture", "sentinel", "copilot"
  ] : l => contains(var.enabled_labs, l) }

  firewall = local.lab.network && var.deploy_firewall
}

resource "azurerm_log_analytics_workspace" "lab" {
  name                = "log-sc500-lab-${local.sfx}"
  location            = local.loc
  resource_group_name = local.rg
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_virtual_network" "lab" {
  name                = "vnet-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  address_space       = ["10.50.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "web" {
  name                 = "snet-web"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.1.0/24"]
}

resource "azurerm_subnet" "app" {
  name                 = "snet-app"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.2.0/24"]
}

resource "azurerm_subnet" "data" {
  name                 = "snet-data"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.3.0/24"]
}

resource "azurerm_subnet" "pe" {
  name                 = "snet-private-endpoints"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.4.0/24"]
}

resource "azurerm_subnet" "vm" {
  name                 = "snet-vm"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.50.5.0/24"]
}
