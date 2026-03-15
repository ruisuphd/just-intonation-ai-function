output "brand_documents_bucket_name" {
  value       = google_storage_bucket.brand_documents.name
  description = "Brand documents bucket name"
}

output "brand_documents_bucket_url" {
  value       = google_storage_bucket.brand_documents.url
  description = "Brand documents bucket gs:// URL"
}

output "packages_bucket_name" {
  value       = google_storage_bucket.packages.name
  description = "Content packages bucket name"
}

output "packages_bucket_url" {
  value       = google_storage_bucket.packages.url
  description = "Content packages bucket gs:// URL"
}
