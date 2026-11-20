variable "subscription_id" {
  description = "Azure subscription that holds the lab resource group."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group. Terraform reads it and never deletes it."
  type        = string
  default     = "rg-sc500-lab"
}

variable "location" {
  description = "Region for every lab resource."
  type        = string
  default     = "uksouth"

  validation {
    condition     = var.location == "uksouth"
    error_message = "These labs deploy to UK South only."
  }
}

variable "enabled_labs" {
  description = "Labs to deploy. Add or remove names, then run terraform apply."
  type        = set(string)
  default     = []
}

variable "deploy_firewall" {
  description = "Network lab only. Azure Firewall Basic bills by the hour, so keep this false until you need it."
  type        = bool
  default     = false
}

variable "apim_publisher_email" {
  description = "Apps lab only. Contact email shown on the API Management instance."
  type        = string
  default     = "lab@example.com"
}

variable "tags" {
  description = "Extra tags. Purpose = SC-500 Lab is always set."
  type        = map(string)
  default     = {}
}
