# DEPRECATED: This module is unused. The frontend is deployed via Firebase App
# Hosting (automark-web), not classic Firebase Hosting. The API runs as
# automark-api on Cloud Run, deployed via `make deploy-api`. None of the
# resources below are referenced from infra/main.tf.
#
# The classic Hosting site (intonation-labs-marketing-dashboard) that was
# created from this module shows "Site Not Found". To remove it:
#   firebase hosting:sites:delete intonation-labs-marketing-dashboard --project intonation-labs-marketing

resource "google_artifact_registry_repository" "docker" {
  project       = var.project_id
  location      = var.region
  repository_id = "marketing-toolkit"
  format        = "DOCKER"
  description   = "Docker images for the AI Marketing Toolkit"
}

resource "google_cloud_run_v2_service" "dashboard" {
  project  = var.project_id
  name     = "dashboard"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      startup_probe {
        http_get {
          path = "/"
        }
        initial_delay_seconds = 0
        period_seconds        = 10
        failure_threshold     = 3
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_firebase_hosting_site" "default" {
  provider = google-beta
  project  = var.project_id
  site_id  = "${var.project_id}-dashboard"
}
