output "enabled_labs" {
  description = "Labs that are deployed now."
  value       = module.sc500_labs.enabled_labs
}

output "lab_resources" {
  description = "Names of the main resources in each deployed lab."
  value       = module.sc500_labs.lab_resources
}

output "vm_private_key" {
  description = "SSH private key for the lab VM. Show it with: terraform output -raw vm_private_key"
  value       = module.sc500_labs.vm_private_key
  sensitive   = true
}
