# Remote state in Azure Storage. Settings live in backend.hcl, which is not committed.
# Copy backend.hcl.example to backend.hcl, fill it in, then run:
#   terraform init -backend-config=backend.hcl
terraform {
  backend "azurerm" {}
}
