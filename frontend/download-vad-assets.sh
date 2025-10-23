#!/bin/bash
# Download VAD assets for self-hosting
# Eliminates dependency on jsdelivr CDN and improves loading speed

set -e

echo "📦 Downloading VAD assets for self-hosting..."

# Create directories
mkdir -p public/vad-assets/vad-web
mkdir -p public/vad-assets/onnxruntime

# Download VAD models and worklet from vad-web@0.0.28 (using jsdelivr.net - more reliable)
echo "⬇️  Downloading Silero VAD models (~1.8 MB each)..."
curl -L "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.28/dist/silero_vad.onnx" \
  -o public/vad-assets/vad-web/silero_vad.onnx

curl -L "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.28/dist/silero_vad_legacy.onnx" \
  -o public/vad-assets/vad-web/silero_vad_legacy.onnx

echo "⬇️  Downloading VAD worklet..."
curl -L "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.28/dist/vad.worklet.bundle.min.js" \
  -o public/vad-assets/vad-web/vad.worklet.bundle.min.js

# Download ONNX Runtime WASM files from onnxruntime-web@1.23.0 (using jsdelivr.net - more reliable)
echo "⬇️  Downloading ONNX Runtime WASM files (~12 MB)..."
curl -L "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.23.0/dist/ort-wasm-simd-threaded.wasm" \
  -o public/vad-assets/onnxruntime/ort-wasm-simd-threaded.wasm

curl -L "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.23.0/dist/ort-wasm-simd-threaded.jsep.wasm" \
  -o public/vad-assets/onnxruntime/ort-wasm-simd-threaded.jsep.wasm

curl -L "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.23.0/dist/ort-wasm-simd-threaded.jsep.mjs" \
  -o public/vad-assets/onnxruntime/ort-wasm-simd-threaded.jsep.mjs

echo ""
echo "✅ VAD assets downloaded successfully!"
echo "📊 Total size:"
du -sh public/vad-assets/
echo ""
echo "📁 Assets location: public/vad-assets/"
echo "   - VAD model: public/vad-assets/vad-web/"
echo "   - ONNX WASM: public/vad-assets/onnxruntime/"
echo ""
echo "💡 Build process workflow:"
echo "   1. These assets stay in public/vad-assets/ (checked into git)"
echo "   2. Vite copies them to dist/demo/vad-assets/ during build"
echo "   3. deploy-demo.sh uploads from dist/demo/vad-assets/ to GCS"
echo ""
echo "💡 Benefits:"
echo "   - Version controlled (no repeated downloads)"
echo "   - Served locally in development (faster, no CDN dependency)"
echo "   - Uploaded to GCS during deployment (reliable, same region)"
echo "   - Cached for 1 year by browsers (downloaded once per device)"
