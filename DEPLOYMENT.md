# AI Interview Platform — Deployment Guide

This guide details the exact steps required to deploy the AI Interview Platform to production using Vercel (Frontend), Render (Backend & Agent), and Supabase (Database & Storage).

## 1. Prerequisites

Before starting, ensure you have the following credentials ready:
- **Supabase**: URL, Publishable Key, Service Role Secret Key, and Connection Pooler URL (Port 6543).
- **LiveKit Cloud**: URL, API Key, and API Secret.
- **Groq**: API Key.
- **Agent API Secret**: Generate a strong random string (e.g., `openssl rand -hex 32`) to secure internal communication between the Backend and Agent.

---

## 2. Supabase Configuration

1. Log in to your [Supabase Dashboard](https://supabase.com/dashboard).
2. **Database Settings**: Navigate to **Project Settings > Database**. Under "Connection pooling", copy the connection string. Ensure the port is `6543`. This will be your `DATABASE_URL`.
3. **Storage**: Navigate to **Storage**. Ensure a bucket named exactly `resumes` exists and is configured to accept PDF uploads.

---

## 3. Render Deployment (Backend & Agent)

The repository uses Render's **Blueprint** feature to automatically configure the infrastructure.

1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** and select **Blueprint**.
3. Connect this GitHub repository.
4. Render will automatically read the `render.yaml` file and propose two services:
   - `ai-interview-backend` (Web Service)
   - `ai-interview-agent` (Background Worker)
5. Click **Apply**.
6. Render will prompt you for the required Secret Environment Variables. Fill them in:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY` (Service Role Key, NOT the anon key)
   - `DATABASE_URL` (The Supavisor connection string on port 6543)
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `GROQ_API_KEY`
   - `AGENT_API_SECRET` (The strong random string you generated)
   - `BACKEND_CORS_ORIGINS`: Temporarily leave this blank or guess your Vercel URL. We will update this in Step 5.
7. Click **Save and Deploy**.
8. Wait for the `ai-interview-backend` to finish deploying. Render will run `alembic upgrade head` automatically. Once it finishes, copy the Backend's public URL (e.g., `https://ai-interview-backend-xxxx.onrender.com`).

---

## 4. Vercel Deployment (Frontend)

1. Log in to your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New... > Project**.
3. Import this GitHub repository.
4. Vercel will auto-detect the framework as **Vite**.
5. Set the **Root Directory** to `frontend`.
6. Open the **Environment Variables** section and add:
   - `VITE_SUPABASE_URL`: (Your Supabase Project URL)
   - `VITE_SUPABASE_PUBLISHABLE_KEY`: (Your Supabase Anon/Public Key)
   - `VITE_API_BASE_URL`: (The Render Backend public URL you copied in Step 3. **Do not include a trailing slash**).
7. Click **Deploy**.
8. Once deployment is complete, copy your Vercel project's public domain URL (e.g., `https://your-project.vercel.app`).

---

## 5. Final Wiring (CORS)

1. Return to the Render Dashboard.
2. Select the `ai-interview-backend` Web Service.
3. Navigate to the **Environment** tab.
4. Update the `BACKEND_CORS_ORIGINS` variable to include your newly generated Vercel domain.
   - Format: `["https://your-project.vercel.app"]`
   - Make sure it's valid JSON syntax.
5. Save the changes. Render will automatically trigger a new deployment of the backend.

---

## 6. Post-Deployment Verification (Smoke Test)

1. Open your Vercel frontend URL in a browser.
2. Log in or create a test account.
3. Upload a test Resume PDF.
4. Verify the PDF successfully uploads and triggers the session creation.
5. Join the interview room. You should hear the LiveKit Agent introduce itself.
6. Speak a response. Verify that the agent replies correctly via Groq.
7. Refresh the page during the interview; verify that the `vercel.json` routing rules successfully bring you back to the active session.

## Important Production Notes
- **Groq Rate Limits**: The platform uses Groq for STT, LLM, and TTS in rapid succession. Concurrent users may trigger HTTP 429 Rate Limits, degrading TTS performance. Monitor this closely during rollout.
- **Secrets**: Ensure no `.env` files are accidentally pushed to the repository in the future. The frontend should never contain keys like `SUPABASE_SECRET_KEY` or `GROQ_API_KEY`.
