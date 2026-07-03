# Drive Video Proxy Server

A lightweight server to stream videos from Google Drive without rate limits. This proxy allows direct video playback in browsers or media players without triggering Drive download throttling.

## Features
- Stream Google Drive videos directly.
- No rate limit for video playback.
- Supports partial content requests (seekable videos).
- Easy to deploy on your server or cloud instance.
- Minimal configuration.

## Requirements
- A Google Drive file ID for the video you want to serve.
- service-account2.json (from Google Cloud Console - API & Services - Credential - New Service Account - JSON key)

## Installation

### Node.js Version
```bash
git clone https://github.com/anatwork14/drive-video-proxy.git
npm install
node server.js
```
