variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "service_account_email" {
  type        = string
  description = "Service account email for OIDC push authentication"
}

variable "fn_platform_generate_url" {
  type        = string
  description = "URL of fn-platform-generate Cloud Function"
}

variable "fn_package_builder_url" {
  type        = string
  description = "URL of fn-package-builder Cloud Function"
}
