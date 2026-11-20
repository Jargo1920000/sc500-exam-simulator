# Lab 8: Implement security for servers and virtual machines.
# A small Linux VM with no public IP. vTPM is on, Secure Boot is off for you to turn on.
# The VM shuts down every evening to save money.

resource "tls_private_key" "vm" {
  count     = local.lab.vm ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "azurerm_network_interface" "vm" {
  count               = local.lab.vm ? 1 : 0
  name                = "nic-vm-sc500-lab"
  location            = local.loc
  resource_group_name = local.rg
  tags                = local.tags

  ip_configuration {
    name                          = "ipconfig"
    subnet_id                     = azurerm_subnet.vm.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "lab" {
  count                 = local.lab.vm ? 1 : 0
  name                  = "vm-sc500-lab"
  location              = local.loc
  resource_group_name   = local.rg
  size                  = "Standard_B1s"
  admin_username        = "labadmin"
  network_interface_ids = [azurerm_network_interface.vm[0].id]
  vtpm_enabled          = true
  secure_boot_enabled   = false # lab task: turn Secure Boot on
  tags                  = local.tags

  admin_ssh_key {
    username   = "labadmin"
    public_key = tls_private_key.vm[0].public_key_openssh
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_dev_test_global_vm_shutdown_schedule" "vm" {
  count                 = local.lab.vm ? 1 : 0
  virtual_machine_id    = azurerm_linux_virtual_machine.lab[0].id
  location              = local.loc
  enabled               = true
  daily_recurrence_time = "1900"
  timezone              = "GMT Standard Time"
  tags                  = local.tags

  notification_settings {
    enabled = false
  }
}
