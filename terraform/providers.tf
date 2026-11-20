provider "azurerm" {
  subscription_id = var.subscription_id

  features {
    # The labs ask you to harden resources by hand. These settings keep
    # "terraform destroy" clean after you change things in the portal.
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
    api_management {
      purge_soft_delete_on_destroy = true
    }
    storage {
      # Skip data plane calls, so a storage firewall you add in a lab cannot block Terraform.
      data_plane_available = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
