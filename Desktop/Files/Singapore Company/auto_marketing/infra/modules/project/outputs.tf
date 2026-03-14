output "service_account_email" {
  value       = google_service_account.cloud_functions.email
  description = "Cloud Functions service account email"
}

output "service_account_name" {
  value       = google_service_account.cloud_functions.name
  description = "Cloud Functions service account fully-qualified name"
}
