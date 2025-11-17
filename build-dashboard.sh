#!/bin/bash
# Build script for React dashboard

set -e

echo "Building Arthayukti React Dashboard..."
echo "========================================"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed"
    echo "Please install Node.js 20.x or later from https://nodejs.org/"
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "Error: npm is not installed"
    echo "Please install npm or use another package manager"
    exit 1
fi

echo "Node version: $(node --version)"
echo "npm version: $(npm --version)"
echo ""

# Navigate to frontend directory
cd "$(dirname "$0")/ui/frontend"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
    echo ""
fi

# Build the React app
echo "Building React app..."
npm run build

echo ""
echo "✓ Build complete!"
echo "Output: ui/static-react/"
echo ""
echo "To start the server:"
echo "  python -m uvicorn ui.dashboard:app --host 127.0.0.1 --port 8765"
echo ""
echo "Then open http://127.0.0.1:8765 in your browser"
