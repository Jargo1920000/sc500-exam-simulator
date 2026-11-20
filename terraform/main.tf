module "sc500_labs" {
  source = "./modules/sc500-labs"

  resource_group_name  = var.resource_group_name
  location             = var.location
  enabled_labs         = var.enabled_labs
  deploy_firewall      = var.deploy_firewall
  apim_publisher_email = var.apim_publisher_email
  tags                 = var.tags
}
