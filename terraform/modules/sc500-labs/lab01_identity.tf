# Lab 1: Secure access to resources by using Microsoft Entra ID.
# Most of this lab is tenant work in the Entra admin center.
# Terraform gives you one managed identity to assign roles to.

resource "azurerm_user_assigned_identity" "lab" {
  count               = local.lab.identity ? 1 : 0
  name                = "id-sc500-lab-${local.sfx}"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags
}
