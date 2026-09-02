# Path2Hire Deployment Guide (100% Free Tier)

This guide provides step-by-step instructions for deploying the Path2Hire platform completely for free, using a combination of Vercel (Frontend), Render (Backend), and Google Cloud Platform (Agent Worker).

## Architecture & Free Tier Limitations
- **Frontend (Vercel)**: 100% free and fast.
- **Backend (Render Web Service)**: 100% free, but spins down after 15 minutes of inactivity. When a candidate clicks the link after the backend has slept, they will experience a **~45-second cold start** while the server boots up.
- **Agent Worker (GCP e2-micro VM)**: 100% free and **runs 24/7 without sleeping**. (Render's background workers require a $7/mo paid plan, so we use Google Cloud's "Always Free" tier instead).

## Prerequisites
- A GitHub repository containing the latest code.
- A [Vercel account](https://vercel.com/).
- A [Render account](https://render.com/).
- A [Google Cloud Platform account](https://cloud.google.com/) with a billing account attached (Google requires this to prevent abuse, but the `e2-micro` instance is free forever).
- Your existing Supabase and LiveKit credentials.

---

## Step 1: Render (Backend)

We deploy the backend first so we have the `BACKEND_INTERNAL_URL` ready for the frontend and agent.

1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** -> **Web Service**.
3. Connect your GitHub repository.
4. **Configuration**:
   - **Name**: `ai-interview-backend`
   - **Root Directory**: `backend`
   - **Environment**: `Docker`
   - **Instance Type**: `Free`
5. **Environment Variables**: Add the following:
   - `ENVIRONMENT`: `production`
   - `SUPABASE_URL`: Your Supabase Project URL
   - `SUPABASE_SECRET_KEY`: Your Supabase `service_role` secret
   - `SUPABASE_JWKS_URL`: `https://<your-project-id>.supabase.co/auth/v1/.well-known/jwks.json`
   - `DATABASE_URL`: Your Supabase **Supavisor connection pooler string** (usually port 6543)
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
   - `AGENT_API_SECRET`: A secure random string you generate (e.g., `my_super_secret_agent_key_123`)
6. Click **Create Web Service**. 
7. Wait for the deploy to finish, and copy your public backend URL (e.g., `https://ai-interview-backend.onrender.com`).

---

## Step 2: Google Cloud Platform (Agent Worker)

Since LiveKit agents need to maintain an active WebSocket connection waiting for jobs, we run it on a free Linux virtual machine.

### A. Create the Free VM
1. Go to the [GCP Compute Engine Console](https://console.cloud.google.com/compute/instances).
2. Click **Create Instance**.
3. **Name**: `ai-interview-agent`
4. **Region (CRITICAL FOR FREE TIER)**: You *must* choose one of the following: `us-central1`, `us-east1`, or `us-west1`.
5. **Machine Configuration**: `General purpose` -> `E2` -> **`e2-micro`**.
6. **Boot Disk**: Leave as Debian (or Ubuntu). Change size to 30 GB (the free tier maximum).
7. Click **Create**.

### B. Deploy the Agent
1. Click the **SSH** button next to your new VM in the GCP console to open a terminal.
2. Run the following commands to install Docker and Git:
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io git
   ```
3. Clone your repository:
   ```bash
   git clone https://github.com/<your-username>/AI-Interview-Platform.git
   cd AI-Interview-Platform
   ```
4. Create the environment variables file for the agent:
   ```bash
   nano agent/.env
   ```
   Paste the following into the file (update with your actual values):
   ```env
   ENVIRONMENT=production
   SUPABASE_URL=...
   SUPABASE_PUBLISHABLE_KEY=...
   SUPABASE_SECRET_KEY=...
   SUPABASE_JWKS_URL=...
   DATABASE_URL=...
   LIVEKIT_URL=...
   LIVEKIT_API_KEY=...
   LIVEKIT_API_SECRET=...
   GROQ_API_KEY=...
   GROQ_MODEL=openai/gpt-oss-120b
   STT_PROVIDER=groq
   STT_MODEL=whisper-large-v3-turbo
   STT_LANGUAGE=en
   LLM_PROVIDER=groq
   LLM_MODEL=openai/gpt-oss-120b
   TTS_PROVIDER=groq
   TTS_MODEL=inworld/inworld-tts-2
   TTS_LANGUAGE=en
   BACKEND_INTERNAL_URL=https://ai-interview-backend.onrender.com  # URL from Step 1
   AGENT_API_SECRET=my_super_secret_agent_key_123                  # Must match backend
   ```
   Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).
5. Build and run the agent Docker container in the background:
   ```bash
   cd agent
   sudo docker build -t ai-agent .
   sudo docker run -d --name agent-worker --env-file .env --restart unless-stopped ai-agent
   ```
   *Your agent is now running 24/7 for free. It will automatically restart if the server reboots.*

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
   - Add the `BACKEND_CORS_ORIGINS` variable and include your exact Vercel URL.
   - Format: `["https://path2hire-frontend.vercel.app"]`
   - Save. Render will restart the backend with the new CORS policy.

2. **Update Supabase Redirect URLs**:
   - Go to your [Supabase Dashboard](https://supabase.com/dashboard).
   - Navigate to **Authentication** -> **URL Configuration**.
   - Under **Site URL**, ensure it is set to your primary Vercel frontend URL (e.g., `https://path2hire-frontend.vercel.app`).
   - Under **Redirect URLs**, add your Vercel URL (e.g., `https://path2hire-frontend.vercel.app/**`).
   - *This step is critical for the magic link and OTP login flows to successfully redirect candidates back to the deployed app.*

## Validation
1. Open your Vercel frontend URL.
2. Log in / apply as a candidate.
3. Start the interview. The UI should successfully request a token from the backend, connect to LiveKit, and the GCP agent should immediately join the room and begin speaking.
