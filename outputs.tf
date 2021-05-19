output "log_topic" {
  value       = google_pubsub_topic.ai_platform_log
  description = "Pub/Sub topic name for log sink."
}
