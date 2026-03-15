variable "project_id" {
  type        = string
  default     = "intonation-labs-marketing"
  description = "GCP project ID"
}

variable "region" {
  type        = string
  default     = "asia-southeast1"
  description = "Primary GCP region for all resources"
}

variable "claude_region" {
  type        = string
  default     = "us-east5"
  description = "Region for Vertex AI Claude model access"
}

variable "environment" {
  type        = string
  default     = "prod"
  description = "Deployment environment"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "notification_email" {
  type        = string
  description = "Email address for monitoring alert notifications"
}

variable "function_urls" {
  type        = map(string)
  default     = {}
  description = "Map of Cloud Function names to deployed URLs. Populate after deploying functions."
}

variable "scheduler_timezone" {
  type        = string
  default     = "Asia/Singapore"
  description = "Timezone used by Cloud Scheduler jobs."
}

variable "publisher_schedule" {
  type        = string
  default     = "*/15 * * * *"
  description = "Cron schedule for the scheduled publisher worker."
}

variable "analytics_sync_schedule" {
  type        = string
  default     = "15 8 * * *"
  description = "Cron schedule for the daily analytics sync worker."
}
