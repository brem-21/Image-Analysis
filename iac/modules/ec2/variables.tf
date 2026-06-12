variable "name" {
  description = "Name tag for the EC2 instance"
  type        = string
}

variable "subnet_id" {
  description = "Subnet to launch the instance into"
  type        = string
}

variable "security_group_ids" {
  description = "List of security group IDs to attach"
  type        = list(string)
  default     = []
}

variable "ami_id" {
  description = "AMI ID override. Defaults to latest Amazon Linux 2023 x86_64."
  type        = string
  default     = null
}

variable "key_name" {
  description = "EC2 key pair name for SSH access"
  type        = string
  default     = null
}

variable "iam_instance_profile" {
  description = "IAM instance profile name to attach"
  type        = string
  default     = null
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB"
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_size >= 8
    error_message = "root_volume_size must be at least 8 GiB."
  }
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
