variable "resource_group_name" {
  description = "Existing resource group for all lab resources."
  type        = string
}

variable "location" {
  description = "Region for every lab resource."
  type        = string
  default     = "uksouth"
}

variable "enabled_labs" {
  description = "Labs to deploy."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([for l in var.enabled_labs : contains([
      "identity", "keyvault", "governance", "storage", "database", "network",
      "ai", "vm", "apps", "posture", "sentinel", "copilot"
    ], l)])
    error_message = "Valid labs: identity, keyvault, governance, storage, database, network, ai, vm, apps, posture, sentinel, copilot."
  }
}

variable "deploy_firewall" {
  description = "Deploy Azure Firewall Basic in the network lab. Bills by the hour."
  type        = bool
  default     = false
}

variable "apim_publisher_email" {
  description = "Contact email for the API Management instance in the apps lab."
  type        = string
  default     = "lab@example.com"
}

variable "tags" {
  description = "Extra tags merged with Purpose = SC-500 Lab."
  type        = map(string)
  default     = {}
}
