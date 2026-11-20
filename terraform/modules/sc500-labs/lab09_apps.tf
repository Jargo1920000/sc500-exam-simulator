# Lab 9: Implement security for application platform services.
# Each resource starts with weak settings for you to fix.

resource "azurerm_service_plan" "lab" {
  count               = local.lab.apps ? 1 : 0
  name                = "asp-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = local.tags
}

resource "azurerm_linux_web_app" "lab" {
  count               = local.lab.apps ? 1 : 0
  name                = "app-sc500-lab-${local.sfx}"
  location            = local.loc
  resource_group_name = local.rg
  service_plan_id     = azurerm_service_plan.lab[0].id
  https_only          = false # lab task: require HTTPS
  tags                = local.tags

  site_config {
    always_on           = false
    ftps_state          = "AllAllowed" # lab task: disable FTP
    minimum_tls_version = "1.2"

    application_stack {
      node_version = "20-lts"
    }
  }
}

resource "azurerm_container_registry" "lab" {
  count               = local.lab.apps ? 1 : 0
  name                = "crsc500lab${local.sfx}"
  location            = local.loc
  resource_group_name = local.rg
  sku                 = "Basic"
  admin_enabled       = true # lab task: turn the admin user off
  tags                = local.tags
}

resource "azurerm_api_management" "lab" {
  count               = local.lab.apps ? 1 : 0
  name                = "apim-sc500-lab-${local.sfx}"
  location            = local.loc
  resource_group_name = local.rg
  publisher_name      = "SC-500 Lab"
  publisher_email     = var.apim_publisher_email
  sku_name            = "Consumption_0"
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }
}

# A WAF policy on its own is free. It starts in Detection mode.
resource "azurerm_web_application_firewall_policy" "lab" {
  count               = local.lab.apps ? 1 : 0
  name                = "waf-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags

  policy_settings {
    enabled = true
    mode    = "Detection" # lab task: switch to Prevention
  }

  managed_rules {
    managed_rule_set {
      type    = "OWASP"
      version = "3.2"
    }
  }
}
