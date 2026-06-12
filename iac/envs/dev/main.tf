locals {
  name = "${var.project_name}-${var.environment}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "vpc" {
  source = "../../modules/vpc"

  name     = local.name
  vpc_cidr = var.vpc_cidr
  az_count = var.az_count
  tags     = local.tags
}

module "security_groups" {
  source = "../../modules/security_groups"

  name             = local.name
  vpc_id           = module.vpc.vpc_id
  vpc_cidr         = module.vpc.vpc_cidr
  allowed_ssh_cidr = var.allowed_ssh_cidr
  tags             = local.tags
}

module "ec2" {
  source = "../../modules/ec2"

  name               = "${local.name}-app"
  subnet_id          = module.vpc.private_subnet_ids[0]
  security_group_ids = [module.security_groups.app_sg_id]
  key_name           = var.key_name
  tags               = local.tags
}
