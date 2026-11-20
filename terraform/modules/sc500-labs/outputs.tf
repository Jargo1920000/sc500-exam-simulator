output "enabled_labs" {
  description = "Labs that are deployed now."
  value       = sort([for name, on in local.lab : name if on])
}

output "lab_resources" {
  description = "Names of the main resources in each deployed lab."
  value = {
    shared = {
      resource_group  = local.rg
      log_analytics   = azurerm_log_analytics_workspace.lab.name
      virtual_network = azurerm_virtual_network.lab.name
    }
    identity   = local.lab.identity ? { managed_identity = azurerm_user_assigned_identity.lab[0].name } : null
    keyvault   = local.lab.keyvault ? { key_vault = azurerm_key_vault.lab[0].name } : null
    governance = local.lab.governance ? { custom_role = azurerm_role_definition.vm_operator[0].name, custom_policy = azurerm_policy_definition.audit_shared_key[0].display_name, recovery_vault = azurerm_recovery_services_vault.lab[0].name } : null
    storage    = local.lab.storage ? { storage_account = azurerm_storage_account.lab[0].name } : null
    database   = local.lab.database ? { sql_server = azurerm_mssql_server.lab[0].name, database = azurerm_mssql_database.lab[0].name } : null
    network    = local.lab.network ? { private_storage = azurerm_storage_account.private[0].name, private_endpoint = azurerm_private_endpoint.blob[0].name, firewall = local.firewall ? azurerm_firewall.lab[0].name : "not deployed" } : null
    ai         = local.lab.ai ? { foundry_resource = azurerm_cognitive_account.foundry[0].name } : null
    vm         = local.lab.vm ? { virtual_machine = azurerm_linux_virtual_machine.lab[0].name } : null
    apps       = local.lab.apps ? { web_app = azurerm_linux_web_app.lab[0].name, container_registry = azurerm_container_registry.lab[0].name, api_management = azurerm_api_management.lab[0].name, waf_policy = azurerm_web_application_firewall_policy.lab[0].name } : null
    sentinel   = local.lab.sentinel ? { workspace = azurerm_log_analytics_workspace.lab.name } : null
  }
}

output "vm_private_key" {
  description = "SSH private key for the lab VM."
  value       = local.lab.vm ? tls_private_key.vm[0].private_key_openssh : ""
  sensitive   = true
}
