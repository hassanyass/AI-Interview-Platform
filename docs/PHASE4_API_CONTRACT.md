# Phase 4 API Contract Snapshot

This is a one-time snapshot of the real Phase 4 backend endpoints for use by Phase 5 frontend implementation. 

## Endpoints

### 1. Admin Ping
* **Method & Path:** `GET /admin/ping`
* **Purpose:** Stub route to verify Admin RBAC logic
* **Returns:** `{"status": "ok", "admin_id": "<admin_id>"}`

### 2. Jobs
* **Method & Path:** `GET /admin/jobs`
* **Returns:** Array of `JobResponse`
* **Errors:** Standard auth errors

* **Method & Path:** `POST /admin/jobs`
* **Request Body (JobCreate):**
  ```json
  {
    "title": "string",
    "description": "string?",
    "seniority": "string?",
    "location": "string?",
    "instructions": "string?",
    "required_skills": ["string"]?,
    "preferred_skills": ["string"]?,
    "responsibilities": ["string"]?
  }
  ```
* **Returns:** `JobResponse` (includes nested `definition`)
* **Status:** 201 Created

* **Method & Path:** `GET /admin/jobs/{job_id}`
* **Returns:** `JobDetailResponse` (includes `definition`, `sections`, and `questions`)
* **Errors:** 404 (Job not found)

* **Method & Path:** `PATCH /admin/jobs/{job_id}`
* **Request Body (JobUpdate):** Same fields as `JobCreate`, all optional.
* **Returns:** `JobResponse`
* **Errors:** 404 (Not found), 409 (Job is not DRAFT)

* **Method & Path:** `DELETE /admin/jobs/{job_id}`
* **Returns:** 204 No Content
* **Errors:** 404 (Not found), 409 (Cannot delete a PUBLISHED job)

* **Method & Path:** `POST /admin/jobs/{job_id}/publish`
* **Returns:** `JobResponse`
* **Errors:** 404 (Not found), 409 (Job is already PUBLISHED)

### 3. Interview Definition (Updates)
* **Method & Path:** `PATCH /admin/definitions/{definition_id}`
* **Request Body (InterviewDefinitionUpdate):**
  ```json
  {
    "duration_minutes": "int?",
    "is_public": "boolean?"
  }
  ```
* **Returns:** `JobResponse`
* **Errors:** 404 (Not found), 409 (Job is not DRAFT)

### 4. Sections
* **Method & Path:** `POST /admin/sections`
* **Request Body (SectionCreate):**
  ```json
  {
    "definition_id": "UUID",
    "section_type": "VERBAL" | "CODING" | "MCQ",
    "order_index": "int (default 0)",
    "config": "object?"
  }
  ```
* **Returns:** `SectionResponse`
* **Status:** 201 Created
* **Errors:** 404 (Definition not found), 409 (Section type already exists on this definition / Job is not DRAFT)

* **Method & Path:** `PATCH /admin/sections/{section_id}`
* **Request Body (SectionUpdate):**
  ```json
  {
    "order_index": "int?",
    "config": "object?"
  }
  ```
* **Returns:** `SectionResponse`
* **Errors:** 404 (Not found), 409 (Job is not DRAFT)

* **Method & Path:** `DELETE /admin/sections/{section_id}`
* **Returns:** 204 No Content
* **Errors:** 404 (Not found), 409 (Job is not DRAFT)

### 5. Questions (Manual CRUD)
* **Method & Path:** `POST /admin/sections/{section_id}/questions`
* **Request Body (QuestionCreate):**
  ```json
  {
    "title": "string",
    "competency": "string?",
    "text": "string",
    "eval_criteria": "object?"
  }
  ```
* **Returns:** `QuestionResponse` (auto-assigns `order_index` at the end)
* **Status:** 201 Created
* **Errors:** 404 (Section not found), 409 (Job is not DRAFT)

* **Method & Path:** `PATCH /admin/questions/{question_id}`
* **Request Body (QuestionUpdate):** All fields from `QuestionCreate`, all optional.
* **Returns:** `QuestionResponse`
* **Errors:** 404 (Not found), 409 (Job is not DRAFT)

* **Method & Path:** `DELETE /admin/questions/{question_id}`
* **Returns:** 204 No Content
* **Errors:** 404 (Not found), 409 (Job is not DRAFT)

### 6. Questions (AI Generation)
* **Method & Path:** `POST /admin/sections/{section_id}/generate-questions`
* **Request Body (QuestionGenerateRequest):**
  ```json
  {
    "num_questions": "int (default 5, 1-20)"
  }
  ```
* **Returns:** Array of `QuestionResponse`
* **Status:** 201 Created
* **Errors:** 404 (Section not found), 409 (Job is not DRAFT)

* **Method & Path:** `POST /admin/questions/{question_id}/regenerate`
* **Request Body:** None
* **Returns:** `QuestionResponse`
* **Errors:** 404 (Question not found), 409 (Job is not DRAFT), 502 (AI generation returned no results)

## Core Schemas used in Responses

* **JobResponse:** Contains `id`, `title`, `description`, `seniority`, `location`, `instructions`, `required_skills`, `preferred_skills`, `responsibilities`, `status`, `created_at`, `updated_at`, `definition` (optional, nested).
* **JobDetailResponse:** Extends `JobResponse` by replacing `definition` with `DefinitionWithSectionsResponse` which deeply nests sections and their questions.
* **SectionResponse:** `id`, `definition_id`, `section_type`, `order_index`, `config`, `created_at`.
* **QuestionResponse:** `id`, `section_id`, `order_index`, `title`, `competency`, `text`, `eval_criteria`, `created_at`.
