variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region for scheduler jobs"
}

variable "service_account_email" {
  type        = string
  description = "Service account email for OIDC authentication"
}

variable "fn_daily_pipeline_url" {
  type        = string
  description = "URL of fn-daily-pipeline Cloud Function (legacy single-tenant)"
}

variable "fn_tenant_pipelines_url" {
  type        = string
  description = "URL of fn-tenant-pipelines Cloud Function (multi-tenant orchestrator)"
  default     = ""
}

variable "fn_scheduled_publisher_url" {
  type        = string
  description = "URL of fn-scheduled-publisher Cloud Function"
  default     = ""
}

variable "fn_analytics_sync_url" {
  type        = string
  description = "URL of fn-analytics-sync Cloud Function"
  default     = ""
}

variable "scheduler_timezone" {
  type        = string
  description = "Timezone used for scheduler jobs"
  default     = "Asia/Singapore"
}

variable "publisher_schedule" {
  type        = string
  description = "Cron schedule for the scheduled publisher"
  default     = "*/15 * * * *"
}

variable "analytics_sync_schedule" {
  type        = string
  description = "Cron schedule for the analytics sync job"
  default     = "15 8 * * *"
}
