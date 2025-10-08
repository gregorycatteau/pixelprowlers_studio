/**
 * Frontend types for Projects (Nuxt 4)
 *
 * These types mirror the DRF Project serializer on the backend:
 * - id: number
 * - owner: user PK (number)
 * - name: string
 * - slug: string (unique per owner)
 * - description: string
 * - status: "draft" | "active" | "archived"
 * - metadata: Record<string, unknown> (no PII)
 * - created_at / updated_at: ISO strings
 *
 * Endpoints (DRF ViewSet + custom action):
 * - GET    /api/v1/projects/              -> Project[]
 * - POST   /api/v1/projects/              -> Project
 * - GET    /api/v1/projects/:slug/        -> Project
 * - PATCH  /api/v1/projects/:slug/        -> Project
 * - DELETE /api/v1/projects/:slug/        -> 204 No Content
 * - GET    /api/v1/projects/mine/         -> Project[]
 */

export type ProjectStatus = 'draft' | 'active' | 'archived'

export interface Project {
  id: number
  owner: number
  name: string
  slug: string
  description: string
  status: ProjectStatus
  metadata: Record<string, unknown>
  created_at: string // ISO date-time
  updated_at: string // ISO date-time
}

/**
 * Body for creating a project.
 * - owner is inferred from the authenticated user on the server.
 * - slug is optional; if omitted/blank the backend generates it from name.
 */
export interface ProjectCreateBody {
  name: string
  description?: string
  status?: ProjectStatus
  slug?: string
  metadata?: Record<string, unknown>
}

/**
 * Body for updating a project (partial).
 * - slug may be updated; if provided as blank, backend may regenerate from name.
 */
export interface ProjectUpdateBody {
  name?: string
  description?: string
  status?: ProjectStatus
  slug?: string
  metadata?: Record<string, unknown>
}

/**
 * Responses
 * - DRF defaults return arrays for list endpoints (no envelope),
 *   and single object for detail/create/update.
 */
export type ProjectsResponse = Project[]
export type ProjectResponse = Project

/**
 * Error shape helper (DRF-style). DRF can return either:
 * - { detail: "..." } for general errors
 * - { field: ["msg1", "msg2"], ... } for validation errors
 * Consumers should handle both cases.
 */
export type ApiError =
  | { detail: string }
  | Record<string, string | string[]>
