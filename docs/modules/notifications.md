# Module: Notifications

## Overview
Detailed documentation for the `notifications` module in ProcureSphere 360.

## Database Models
### Notification
Notification(id, created_at, updated_at, created_by, recipient, notification_type, title, message, is_read, target_url)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `recipient` | `ForeignKey` | to: User |
| `notification_type` | `CharField` | - |
| `title` | `CharField` | - |
| `message` | `TextField` | - |
| `is_read` | `BooleanField` | - |
| `target_url` | `CharField` | blank |
