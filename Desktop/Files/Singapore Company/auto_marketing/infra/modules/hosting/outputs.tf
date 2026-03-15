output "cloud_run_url" {
  value       = google_cloud_run_v2_service.dashboard.uri
  description = "Dashboard Cloud Run service URL"
}

output "cloud_run_name" {
  value       = google_cloud_run_v2_service.dashboard.name
  description = "Dashboard Cloud Run service name"
}

output "artifact_registry_id" {
  value       = google_artifact_registry_repository.docker.id
  description = "Artifact Registry repository resource ID"
}

output "artifact_registry_url" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
  description = "Artifact Registry repository URL for docker push"
}

output "firebase_hosting_site" {
  value       = google_firebase_hosting_site.default.site_id
  description = "Firebase Hosting site ID"
}
