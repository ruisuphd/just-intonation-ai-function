variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region"
}

variable "service_account_email" {
  type        = string
  description = "Service account email for Cloud Run"
}
