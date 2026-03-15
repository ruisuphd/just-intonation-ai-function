output "job_names" {
  value = {
    daily_pipeline      = length(google_cloud_scheduler_job.daily_pipeline) > 0 ? google_cloud_scheduler_job.daily_pipeline[0].name : null
    scheduled_publisher = length(google_cloud_scheduler_job.scheduled_publisher) > 0 ? google_cloud_scheduler_job.scheduled_publisher[0].name : null
    analytics_sync      = length(google_cloud_scheduler_job.analytics_sync) > 0 ? google_cloud_scheduler_job.analytics_sync[0].name : null
  }
  description = "Map of scheduler job names (null if not yet created)"
}
