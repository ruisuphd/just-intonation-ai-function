output "content_generate_topic_name" {
  value       = google_pubsub_topic.content_generate.name
  description = "Content generation topic name"
}

output "content_generate_topic_id" {
  value       = google_pubsub_topic.content_generate.id
  description = "Content generation topic resource ID"
}

output "batch_complete_topic_name" {
  value       = google_pubsub_topic.batch_complete.name
  description = "Batch complete topic name"
}

output "batch_complete_topic_id" {
  value       = google_pubsub_topic.batch_complete.id
  description = "Batch complete topic resource ID"
}

output "content_generate_dlq_topic_name" {
  value       = google_pubsub_topic.content_generate_dlq.name
  description = "Content generation DLQ topic name"
}

output "batch_complete_dlq_topic_name" {
  value       = google_pubsub_topic.batch_complete_dlq.name
  description = "Batch complete DLQ topic name"
}
