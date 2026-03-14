output "secret_ids" {
  value       = { for name, secret in google_secret_manager_secret.secrets : name => secret.id }
  description = "Map of secret names to their Secret Manager resource IDs"
}

output "secret_names" {
  value       = { for name, secret in google_secret_manager_secret.secrets : name => secret.secret_id }
  description = "Map of secret names to their Secret Manager secret IDs"
}
