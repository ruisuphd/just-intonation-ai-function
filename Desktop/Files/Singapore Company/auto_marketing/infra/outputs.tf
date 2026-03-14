output "service_account_email" {
  value       = module.project.service_account_email
  description = "Cloud Functions service account email"
}

output "firestore_database" {
  value       = module.firestore.database_name
  description = "Firestore database name"
}

output "brand_documents_bucket" {
  value       = module.storage.brand_documents_bucket_name
  description = "Brand documents GCS bucket name"
}

output "packages_bucket" {
  value       = module.storage.packages_bucket_name
  description = "Content packages GCS bucket name"
}

output "scheduler_jobs" {
  value       = module.scheduler.job_names
  description = "Map of scheduler job names"
}

output "secret_ids" {
  value       = module.secrets.secret_ids
  description = "Map of secret names to their Secret Manager resource IDs"
}

output "monitoring_notification_channel_id" {
  value       = module.monitoring.notification_channel_id
  description = "Monitoring notification channel resource name"
}

output "content_generate_topic_name" {
  value       = module.pubsub.content_generate_topic_name
  description = "Pub/Sub topic name for content generation events"
}

output "batch_complete_topic_name" {
  value       = module.pubsub.batch_complete_topic_name
  description = "Pub/Sub topic name for batch completion events"
}
