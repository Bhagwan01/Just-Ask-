#!/usr/bin/env bash
# ================================================================
# Just Ask Backend — Render Build Script
# ================================================================
# This script runs during Render's build phase.
# It installs dependencies and pre-downloads the embedding model.
# ================================================================

set -o errexit  # Exit on error

echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

# Pre-install CPU-only PyTorch (saves ~5GB by avoiding CUDA)
echo "🔧 Installing CPU-only PyTorch..."
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Pre-download the embedding model during build (not at runtime)
echo "🤖 Pre-downloading embedding model..."
python -c "
from sentence_transformers import SentenceTransformer
print('Downloading sentence-transformers/all-MiniLM-L6-v2...')
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print(f'Model downloaded. Dimension: {model.get_sentence_embedding_dimension()}')
print('✓ Embedding model ready')
"

# Create required directories
echo "📁 Creating data directories..."
mkdir -p data models logs data/uploads data/chroma_db

# Fix DATABASE_URL for asyncpg compatibility
# Render provides postgresql:// but asyncpg needs postgresql+asyncpg://
if [ -n "$DATABASE_URL" ]; then
    export DATABASE_URL=$(echo $DATABASE_URL | sed 's|^postgres://|postgresql+asyncpg://|; s|^postgresql://|postgresql+asyncpg://|')
    echo "✓ DATABASE_URL configured for asyncpg"
fi

echo "✅ Build complete!"
