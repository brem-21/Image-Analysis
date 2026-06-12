variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as a resource name prefix"
  type        = string
  default     = "image-analysis"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to deploy across"
  type        = number
  default     = 2
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into the bastion host. Restrict to your IP in production."
  type        = string
  default     = "0.0.0.0/0"
}

variable "key_name" {
  description = "EC2 key pair name for SSH access. Leave null to disable key-based SSH."
  type        = string
  default     = null
}
