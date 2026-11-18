terraform {
  required_version = ">= 1.9"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "4.7.0"
    }
  }
}

provider "docker" {}

variable "prefix" {
  type    = string
  default = "mbxread-tf"
}

variable "app_port" {
  type    = number
  default = 18002
}

variable "enable_models" {
  type    = bool
  default = false
}

module "stack" {
  source        = "./stack"
  prefix        = var.prefix
  app_port      = var.app_port
  enable_models = var.enable_models
  build_context = "${path.root}/.."
}

output "app_url" {
  value = module.stack.app_url
}
