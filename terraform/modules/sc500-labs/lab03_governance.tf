# Lab 3: Implement governance to enforce security and regulatory compliance.

# Built-in policy "Allowed locations", scoped to the lab resource group only.
resource "azurerm_resource_group_policy_assignment" "allowed_locations" {
  count                = local.lab.governance ? 1 : 0
  name                 = "sc500-allowed-locations"
  display_name         = "SC-500 Lab: allowed locations (UK South)"
  resource_group_id    = data.azurerm_resource_group.lab.id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c"

  parameters = jsonencode({
    listOfAllowedLocations = { value = [local.loc] }
  })
}

# Custom policy definition. Audit only, so it never blocks a deployment.
resource "azurerm_policy_definition" "audit_shared_key" {
  count        = local.lab.governance ? 1 : 0
  name         = "sc500-audit-storage-shared-key-${local.sfx}"
  display_name = "SC-500 Lab: audit storage accounts that allow shared key access"
  description  = "Flags storage accounts where shared key authorization is not disabled."
  policy_type  = "Custom"
  mode         = "Indexed"

  metadata = jsonencode({ category = "SC-500 Lab" })

  policy_rule = jsonencode({
    if = {
      allOf = [
        { field = "type", equals = "Microsoft.Storage/storageAccounts" },
        { field = "Microsoft.Storage/storageAccounts/allowSharedKeyAccess", notEquals = false }
      ]
    }
    then = { effect = "audit" }
  })
}

resource "azurerm_resource_group_policy_assignment" "audit_shared_key" {
  count                = local.lab.governance ? 1 : 0
  name                 = "sc500-audit-shared-key"
  display_name         = "SC-500 Lab: audit storage shared key access"
  resource_group_id    = data.azurerm_resource_group.lab.id
  policy_definition_id = azurerm_policy_definition.audit_shared_key[0].id
}

# Custom Azure role, assignable in the lab resource group only.
resource "azurerm_role_definition" "vm_operator" {
  count       = local.lab.governance ? 1 : 0
  name        = "SC500 Lab VM Operator ${local.sfx}"
  scope       = data.azurerm_resource_group.lab.id
  description = "Can start, restart and deallocate virtual machines. Cannot create or delete them."

  permissions {
    actions = [
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/start/action",
      "Microsoft.Compute/virtualMachines/restart/action",
      "Microsoft.Compute/virtualMachines/deallocate/action",
      "Microsoft.Resources/subscriptions/resourceGroups/read"
    ]
    not_actions = []
  }

  assignable_scopes = [data.azurerm_resource_group.lab.id]
}

# Empty Recovery Services vault for the Azure Backup security tasks.
resource "azurerm_recovery_services_vault" "lab" {
  count               = local.lab.governance ? 1 : 0
  name                = "rsv-sc500-lab-${local.sfx}"
  location            = local.loc
  resource_group_name = local.rg
  sku                 = "Standard"
  storage_mode_type   = "LocallyRedundant"
  tags                = local.tags
}
