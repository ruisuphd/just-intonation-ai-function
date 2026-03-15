output "notification_channel_id" {
  value       = google_monitoring_notification_channel.email.name
  description = "Monitoring notification channel resource name"
}

output "function_error_metric_name" {
  value       = google_logging_metric.function_errors.name
  description = "Log-based metric name for function errors"
}
