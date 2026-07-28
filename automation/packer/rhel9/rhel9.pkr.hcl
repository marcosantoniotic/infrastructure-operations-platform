packer {
  required_version = ">= 1.10.0"

  required_plugins {
    vmware = {
      version = ">= 1.2.0"
      source  = "github.com/hashicorp/vmware"
    }
    vagrant = {
      version = ">= 1.1.7"
      source  = "github.com/hashicorp/vagrant"
    }
  }
}

locals {
  kickstart_content = templatefile("${path.root}/http/kickstart.cfg.pkrtpl", {
    admin_password = var.admin_password
    admin_username = var.admin_username
    guest_hostname = var.guest_hostname
    ssh_public_key = var.ssh_public_key
  })
}

source "vmware-iso" "rhel9_validation" {
  vm_name          = var.vm_name
  guest_os_type    = "rhel9-64"
  output_directory = "${path.root}/output/vmware"

  iso_url      = var.iso_path
  iso_checksum = "sha256:${var.iso_checksum}"

  cpus      = var.cpus
  memory    = var.memory_mb
  disk_size = var.disk_size_mb

  disk_adapter_type    = "scsi"
  network              = "nat"
  network_adapter_type = "vmxnet3"
  headless             = var.headless

  http_content = {
    "/kickstart.cfg" = local.kickstart_content
  }

  boot_wait = "10s"
  boot_command = [
    "<up><wait><tab><wait>",
    " inst.text inst.ks=http://{{ .HTTPIP }}:{{ .HTTPPort }}/kickstart.cfg",
    "<enter>"
  ]

  ssh_username           = var.admin_username
  ssh_private_key_file   = var.ssh_private_key_file
  ssh_timeout            = "45m"
  ssh_handshake_attempts = 100

  shutdown_command = "sudo systemctl poweroff"

  vmx_data = {
    "mks.enable3d"                   = "FALSE"
    "tools.syncTime"                 = "TRUE"
    "virtualHW.productCompatibility" = "hosted"
  }
}

build {
  name    = "rhel9-validation-base"
  sources = ["source.vmware-iso.rhel9_validation"]

  provisioner "shell" {
    inline = [
      "sudo systemctl enable sshd vmtoolsd",
      "sudo restorecon -RFv /home/${var.admin_username}/.ssh",
      "sudo sync"
    ]
  }

  post-processors {
    post-processor "vagrant" {
      keep_input_artifact = true
      output              = "${path.root}/output/rhel-9.8-vmware.box"
    }
  }
}
