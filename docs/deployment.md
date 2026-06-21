# Deployment Guide

Just Ask is fully configured for automated cloud deployment via **Render Blueprints**. The `render.yaml` file in the root of the repository acts as Infrastructure as Code (IaC) and defines the required services.

## Prerequisites
- A GitHub account.
- A free [Render](https://render.com/) account.
- A free [Groq](https://console.groq.com/) API Key.

## Step-by-Step Deployment

1. **Commit and Push to GitHub**
   Ensure all changes are committed and pushed to a remote GitHub repository.
   ```bash
   git add .
   git commit -m "Prepare for production"
   git push origin main
   ```

2. **Connect to Render**
   - Log in to your Render Dashboard.
   - Click the **New +** button in the top right corner.
   - Select **Blueprint**.
   - Connect your GitHub account (if you haven't already) and select your `JustAsk` repository.

3. **Deploy the Blueprint**
   - Render will automatically parse the `render.yaml` file.
   - It will propose the creation of three services:
     1. **`justask-db`**: A PostgreSQL Database (Free Tier).
     2. **`justask-api`**: A Python Web Service for the FastAPI backend (Free Tier).
     3. **`justask-frontend`**: A Static Site for the React frontend (Free Tier).
   - Click **Apply** to start the deployment.

4. **Configure Secrets**
   For security reasons, your Groq API key is not stored in the repository. You must add it manually to the backend service.
   - Once the deployment begins, navigate to your **`justask-api`** service in the Render Dashboard.
   - Go to the **Environment** tab.
   - Add a new environment variable:
     - **Key**: `GROQ_API_KEY`
     - **Value**: `your_actual_api_key_here`
   - Save changes. Render will automatically redeploy the backend with the new key.

## Architecture on Render

- **Database**: PostgreSQL handles structured metadata (documents, history). 
- **Backend Build Script**: `backend/render_build.sh` is executed automatically to install NLTK data and pre-cache the HuggingFace embedding models before the server starts.
- **Backend Server**: The app runs using `gunicorn` with `UvicornWorker` to manage asynchronous requests.
- **Frontend Networking**: The `render.yaml` automatically injects `VITE_API_URL` pointing to your deployed backend URL so the frontend knows exactly where to send API requests.

## Troubleshooting

- **Build Timeout**: The initial deployment downloads the `sentence-transformers` embedding model which is ~100MB. If it times out, trigger a manual redeploy in the Render dashboard.
- **Database Connection Error**: The connection string is managed via Render's Internal Network. Ensure `DATABASE_URL` is populated by the `fromDatabase` mapping in `render.yaml` (this is automatic).
