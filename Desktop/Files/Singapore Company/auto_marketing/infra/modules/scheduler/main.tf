# Scheduler job is created only after the daily pipeline URL is known.
# On first `terraform apply` with function_urls = {}, this is skipped.
# After deploying the function, populate function_urls["fn-daily-pipeline"] and re-apply.

resource "google_cloud_scheduler_job" "daily_pipeline" {
  count       = var.fn_daily_pipeline_url != "" ? 1 : 0
  project     = var.project_id
  region      = var.region
  name        = "daily-pipeline"
  description = "Daily marketing pipeline trigger"
  schedule    = "0 7 * * *"
  time_zone   = "Asia/Singapore"
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = var.fn_daily_pipeline_url

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
