# Path2Hire Deployment Guide (100% Free Tier, No Credit Card)

This guide provides step-by-step instructions for deploying the Path2Hire platform completely for free with **no credit card required**. We use Vercel for the frontend and a special Render configuration for the backend and agent.

## Architecture & How the Free Tier Hack Works
- **Frontend (Vercel)**: 100% free, always fast.
- **Backend (Render Web Service)**: 100% free, but naturally spins down after 15 minutes of inactivity, causing ~45s cold starts.
- **Agent Worker (Render Web Service)**: 100% free. We have modified the agent's code to run a "dummy" HTTP server alongside the LiveKit worker. This tricks Render into allowing it on their free "Web Service" tier instead of forcing you into a $7/month Background Worker plan.
- **The "Always Awake" Hack**: To prevent both the backend and the agent from sleeping and dropping candidate interviews, we will use a free uptime monitor (`cron-job.org`) to ping both services every 14 minutes. This keeps your entire stack awake 24/7 for zero cost.

## Prerequisites
- A GitHub repository containing the latest code.
- A [Vercel account](https://vercel.com/).
- A [Render account](https://render.com/) (No credit card required).
- A [cron-job.org account](https://cron-job.org/) (100% free).
- Your existing Supabase and LiveKit credentials.

---

## Step 1: Render (Backend & Agent Worker)

We deploy the backend and agent first so that we have their URLs ready for the frontend. 

1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** -> **Blueprint**.
3. Connect your GitHub repository.
4. Render will read the `render.yaml` file and automatically propose two **Web Services**:
   - `ai-interview-backend`
   - `ai-interview-agent`
5. **Instance Types**: Select the **Free** instance type for **BOTH** services. 
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
8. Once they are deployed, note **both** public URLs (e.g., `https://ai-interview-backend.onrender.com` and `https://ai-interview-agent.onrender.com`).
9. **Update Internal Links**: Go to the **Environment** settings for the `ai-interview-agent` service and add:
   - `BACKEND_INTERNAL_URL`: The backend URL you just copied (e.g., `https://ai-interview-backend.onrender.com`).

---

## Step 2: Keep-Alive Monitor (cron-job.org)

To prevent your free Render services from falling asleep and causing delays/dropped connections:

1. Go to [cron-job.org](https://cron-job.org/en/) and log in.
2. Click **Create Cronjob**.
3. **Backend Monitor**:
   - Title: `Path2Hire Backend`
   - URL: `https://ai-interview-backend.onrender.com/docs` (Your backend URL + `/docs`)
   - Execution Schedule: **Every 14 minutes**
   - Click Create.
4. **Agent Monitor**:
   - Click **Create Cronjob** again.
   - Title: `Path2Hire Agent`
   - URL: `https://ai-interview-agent.onrender.com/` (Your agent URL)
   - Execution Schedule: **Every 14 minutes**
   - Click Create.

*Your backend and agent are now awake 24/7, mimicking a paid server for free.*

---

## Step 3: Vercel (Frontend)

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

## Step 4: Final Configurations (CORS & Supabase Auth)

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
3. Start the interview. The UI should successfully request a token from the backend, connect to LiveKit, and the agent should immediately join the room and begin speaking with zero delay.
