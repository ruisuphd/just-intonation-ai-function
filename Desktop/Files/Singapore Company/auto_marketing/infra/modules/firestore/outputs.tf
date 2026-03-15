output "database_name" {
  value       = google_firestore_database.default.name
  description = "Firestore database name"
}

output "database_id" {
  value       = google_firestore_database.default.id
  description = "Firestore database resource ID"
}
