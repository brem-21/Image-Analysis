output "instance_id" {
  description = "The ID of the EC2 instance"
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Private IP address of the instance"
  value       = aws_instance.this.private_ip
}

output "public_ip" {
  description = "Public IP address of the instance (if in public subnet)"
  value       = aws_instance.this.public_ip
}

output "ami_id" {
  description = "AMI ID used by the instance"
  value       = aws_instance.this.ami
}
