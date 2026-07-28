variable "iso_path" {
  type        = string
  description = "Absolute path to the RHEL 9.8 x86_64 DVD ISO."
}

variable "iso_checksum" {
  type        = string
  description = "SHA-256 checksum of the RHEL DVD ISO."
  default     = "c0dd53b73406b85b40d6168d1748e605d71361b2992d282c408b7d7d2e1d2c80"
}

variable "vm_name" {
  type        = string
  description = "Name of the temporary Packer build VM."
  default     = "RHEL9-VALIDATION-BASE"
}

variable "guest_hostname" {
  type        = string
  description = "Hostname embedded in the reusable base image."
  default     = "rhel9-validation-base"
}

variable "admin_username" {
  type        = string
  description = "Administrative account created by Kickstart."
  default     = "automation"
}

variable "admin_password" {
  type        = string
  description = "Transient local password generated outside Git."
  sensitive   = true
}

variable "ssh_public_key" {
  type        = string
  description = "Public key authorized for the administrative account."
}

variable "ssh_private_key_file" {
  type        = string
  description = "Private key used by Packer to validate the image."
  sensitive   = true
}

variable "cpus" {
  type        = number
  description = "CPU count used while building the base image."
  default     = 2
}

variable "memory_mb" {
  type        = number
  description = "Memory used while building the base image."
  default     = 4096
}

variable "disk_size_mb" {
  type        = number
  description = "Sparse virtual disk capacity shared by derived VMs."
  default     = 61440
}

variable "headless" {
  type        = bool
  description = "Run the Packer build without opening the VM console."
  default     = false
}
