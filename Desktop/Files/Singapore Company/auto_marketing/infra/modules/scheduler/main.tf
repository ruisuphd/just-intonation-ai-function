# Multi-tenant orchestrator — runs pipeline for all active tenants daily at 07:00 SGT.
# Falls back to single-tenant endpoint if multi-tenant URL is not set.

locals {
  pipeline_url = var.fn_tenant_pipelines_url != "" ? var.fn_tenant_pipelines_url : var.fn_daily_pipeline_url
}

resource "google_cloud_scheduler_job" "daily_pipeline" {
  count            = local.pipeline_url != "" ? 1 : 0
  project          = var.project_id
  region           = var.region
  name             = "daily-pipeline"
  description      = "Daily marketing pipeline trigger (multi-tenant)"
  schedule         = "0 7 * * *"
  time_zone        = var.scheduler_timezone
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = local.pipeline_url

    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count          = 1
    max_backoff_duration = "3600s"
    min_backoff_duration = "5s"
  }
}

resource "google_cloud_scheduler_job" "scheduled_publisher" {
  count            = var.fn_scheduled_publisher_url != "" ? 1 : 0
  project          = var.project_id
  region           = var.region
  name             = "scheduled-publisher"
  description      = "Publishes due approved social posts"
  schedule         = var.publisher_schedule
  time_zone        = var.scheduler_timezone
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = var.fn_scheduled_publisher_url

    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count          = 3
    max_backoff_duration = "900s"
    min_backoff_duration = "30s"
  }
}

resource "google_cloud_scheduler_job" "analytics_sync" {
  count            = var.fn_analytics_sync_url != "" ? 1 : 0
  project          = var.project_id
  region           = var.region
  name             = "analytics-sync"
  description      = "Daily analytics snapshot sync"
  schedule         = var.analytics_sync_schedule
  time_zone        = var.scheduler_timezone
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = var.fn_analytics_sync_url

    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count          = 2
    max_backoff_duration = "3600s"
    min_backoff_duration = "60s"
  }
}
