#!/usr/bin/env node
/**
 * Bookmarklet Generator - Step S8
 * 
 * Generates bookmarklet code with SRI hash for secure loading.
 * Usage: node generate-bookmarklet.js [bundle-path] [cdn-url]
 */

import fs from 'fs';
import crypto from 'crypto';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration
const BUNDLE_PATH = process.argv[2] || path.join(__dirname, '../dist/bookmarklet/bookmarklet.bundle.js');
const CDN_URL = process.argv[3] || 'http://localhost:5174/bookmarklet/bookmarklet.bundle.js';

// Read bundle file
if (!fs.existsSync(BUNDLE_PATH)) {
	console.error(`Error: Bundle not found at ${BUNDLE_PATH}`);
	console.error('Build the bundle first: npm run build:bookmarklet');
	process.exit(1);
}

const bundleContent = fs.readFileSync(BUNDLE_PATH, 'utf8');
const bundleSize = Buffer.byteLength(bundleContent, 'utf8');

// Calculate SHA-384 hash for SRI (stronger than SHA-256 for integrity)
const hash = crypto.createHash('sha384');
hash.update(bundleContent);
const integrity = `sha384-${hash.digest('base64')}`;

// Calculate SHA-256 for release notes
const sha256Hash = crypto.createHash('sha256');
sha256Hash.update(bundleContent);
const sha256 = sha256Hash.digest('hex');

// Bookmarklet loader code (will be minified and URL-encoded)
// NOTE: SRI hash is disabled during development to allow hot-reloading
const loaderCode = `
(function() {
	if (window.VoiceFormFiller && window.VoiceFormFiller.isActive()) {
		console.log('[Bookmarklet] Already active');
		return;
	}
	
	var script = document.createElement('script');
	script.src = '${CDN_URL}?v=' + Date.now();
	script.crossOrigin = 'anonymous';
	script.onload = function() {
		if (window.VoiceFormFiller) {
			window.VoiceFormFiller.inject();
		} else {
			alert('Voice Form Filler failed to load. Check console for errors.');
		}
	};
	script.onerror = function() {
		alert('Failed to load Voice Form Filler from CDN. Check your connection.');
	};
	document.head.appendChild(script);
})();
`.trim();

// Minify by removing whitespace and comments
const minified = loaderCode
	.replace(/\n\s*/g, '')
	.replace(/\s+/g, ' ')
	.replace(/\s*([{}();,:])\s*/g, '$1');

// URL-encode for bookmarklet
const bookmarklet = 'javascript:' + encodeURIComponent(minified);

// Generate output
const output = {
	bundle: {
		path: BUNDLE_PATH,
		size: bundleSize,
		sizeKB: (bundleSize / 1024).toFixed(2),
		sha256: sha256,
		integrity: integrity,
	},
	cdn: {
		url: CDN_URL,
	},
	loader: {
		raw: loaderCode,
		minified: minified,
		minifiedSize: minified.length,
		bookmarklet: bookmarklet,
		bookmarkletSize: bookmarklet.length,
	},
};

// Print results
console.log('='.repeat(80));
console.log('BOOKMARKLET GENERATOR - S8');
console.log('='.repeat(80));
console.log('');
console.log('Bundle Info:');
console.log(`  Path:       ${output.bundle.path}`);
console.log(`  Size:       ${output.bundle.sizeKB} KB (${output.bundle.size} bytes)`);
console.log(`  SHA-256:    ${output.bundle.sha256}`);
console.log(`  Integrity:  ${output.bundle.integrity}`);
console.log('');
console.log('CDN URL:');
console.log(`  ${output.cdn.url}`);
console.log('');
console.log('Loader Code (minified):');
console.log(`  Size: ${output.loader.minifiedSize} bytes`);
console.log(`  ${output.loader.minified.substring(0, 80)}...`);
console.log('');
console.log('Bookmarklet:');
console.log(`  Size: ${output.loader.bookmarkletSize} bytes (${output.loader.bookmarkletSize < 2048 ? '✓ < 2KB' : '✗ TOO LARGE'})`);
console.log(`  ${output.loader.bookmarklet.substring(0, 100)}...`);
console.log('');
console.log('='.repeat(80));
console.log('');
console.log('To use:');
console.log('1. Copy the bookmarklet code above');
console.log('2. Create a new bookmark in Chrome');
console.log('3. Paste the bookmarklet code as the URL');
console.log('4. Name it "Voice Form Filler"');
console.log('5. Click the bookmark on any webpage');
console.log('');
console.log('Output saved to: frontend/bookmarklet-output.json');
console.log('');

// Save to file
const outputPath = path.join(__dirname, '../bookmarklet-output.json');
fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));

console.log('✓ Done!');
