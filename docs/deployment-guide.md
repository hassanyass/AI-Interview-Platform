# Path2Hire Deployment Guide

This guide provides step-by-step instructions for deploying the Path2Hire platform using Vercel (for the frontend) and Render (for the backend and agent worker).

## Prerequisites
- A GitHub repository containing the latest code.
- A Vercel account.
- A Render account.
- Your existing Supabase project credentials.
- Your LiveKit project credentials.
- Your Groq / LLM / TTS provider credentials.

---

## Step 1: Render (Backend & Agent Worker)

We deploy the backend and agent first so that we have the final `BACKEND_INTERNAL_URL` and `VITE_API_BASE_URL` ready for the frontend. The project includes a `render.yaml` Blueprint which makes this straightforward.

1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** -> **Blueprint**.
3. Connect your GitHub repository.
4. Render will read the `render.yaml` file and automatically propose two services:
   - `ai-interview-backend` (Web Service)
   - `ai-interview-agent` (Background Worker)
5. **Instance Types**: 
   - You can select the **Free** instance type for the Web Service (note: it will spin down after 15 mins of inactivity, resulting in ~45s cold starts).
   - For the Background Worker, you must select a paid instance (Starter - $7/month) because Render does not allow background workers on the free tier.
6. **Environment Variables**: Render will prompt you to fill in the required environment variables. Refer to the list below:
   - `ENVIRONMENT`: `production`
   - `SUPABASE_URL`: Your Supabase Project URL
   - `SUPABASE_SECRET_KEY`: Your Supabase `service_role` secret
   - `SUPABASE_JWKS_URL`: `https://<your-project-id>.supabase.co/auth/v1/.well-known/jwks.json`
   - `DATABASE_URL`: Your Supabase **Supavisor connection pooler string** (usually port 6543)
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
   - `GROQ_API_KEY`, `GROQ_MODEL`
   - `STT_PROVIDER`, `STT_MODEL`, `STT_LANGUAGE`
   - `LLM_PROVIDER`, `LLM_MODEL`
   - `TTS_PROVIDER`, `TTS_MODEL`, `TTS_LANGUAGE`
   - `AGENT_API_SECRET`: A secure random string you generate (e.g., `my_super_secret_agent_key_123`)
7. Click **Apply**. Render will begin building and deploying both services.
8. Once the backend is deployed, note its public URL (e.g., `https://ai-interview-backend.onrender.com`).
9. **Update Internal Links**: Go back to the **Environment** settings for the `ai-interview-agent` worker and add:
   - `BACKEND_INTERNAL_URL`: The backend URL you just copied (e.g., `https://ai-interview-backend.onrender.com`).

---

## Step 2: Vercel (Frontend)

1. Go to your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New** -> **Project**.
3. Import your GitHub repository.
4. **Configure Project**:
   - **Framework Preset**: Vite
   - **Root Directory**: Click `Edit` and select `frontend`.
5. **Environment Variables**: Add the following:
   - `VITE_SUPABASE_URL`: Your Supabase Project URL
   - `VITE_SUPABASE_PUBLISHABLE_KEY`: Your Supabase `anon`/`public` key
   - `VITE_API_BASE_URL`: The Render backend URL you copied in Step 1 (e.g., `https://ai-interview-backend.onrender.com`).
6. Click **Deploy**.
7. Once deployed, note your new Vercel public URL (e.g., `https://path2hire-frontend.vercel.app`).

---

## Step 3: Final Configurations (CORS & Supabase Auth)

Now that we have all the deployed URLs, we need to finalize the security and authentication handshakes.

1. **Update Backend CORS in Render**:
   - Go to your Render Dashboard -> `ai-interview-backend` -> **Environment**.
   - Add/Update the `BACKEND_CORS_ORIGINS` variable to include your exact Vercel URL.
   - Format: `["https://path2hire-frontend.vercel.app"]`
   - Save and Render will automatically restart the backend with the new CORS policy.

2. **Update Supabase Redirect URLs**:
   - Go to your [Supabase Dashboard](https://supabase.com/dashboard).
   - Navigate to **Authentication** -> **URL Configuration**.
   - Under **Site URL**, ensure it is set to your primary Vercel frontend URL (e.g., `https://path2hire-frontend.vercel.app`).
   - Under **Redirect URLs**, add your Vercel URL (e.g., `https://path2hire-frontend.vercel.app/**`).
   - *This step is critical for the magic link and OTP login flows to successfully redirect candidates back to the deployed app instead of localhost.*

## Validation
1. Open your Vercel frontend URL.
2. Log in / apply as a candidate.
3. Start the interview. The UI should successfully request a token from the backend, connect to LiveKit, and the Render agent should immediately join the room and begin speaking.
