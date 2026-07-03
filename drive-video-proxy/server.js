// server.js
const express = require("express");
const { GoogleAuth } = require("google-auth-library");
const { Readable } = require("stream");

const app = express();
const PORT = process.env.PORT || 5000;

// Path to your service account JSON file (override with GOOGLE_APPLICATION_CREDENTIALS)
const KEYFILE = process.env.GOOGLE_APPLICATION_CREDENTIALS || "./service-account2.json";
const SCOPES = ["https://www.googleapis.com/auth/drive.readonly"];

// ✅ Initialize Google Auth client once
const auth = new GoogleAuth({
  keyFile: KEYFILE,
  scopes: SCOPES,
});
let count = 0;
app.get("/video/:fileId", async (req, res) => {
  const { fileId } = req.params;
  const range = req.headers.range;
  console.log("Count:", count);
  if (!range) {
    return res.status(400).send("Requires Range header");
  }

  try {
    // Get a client and access token
    const client = await auth.getClient();
    const tokenResponse = await client.getAccessToken();
    const accessToken = tokenResponse.token;

    const driveUrl = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`;

    const driveRes = await fetch(driveUrl, {
      headers: {
        Range: range,
        Authorization: `Bearer ${accessToken}`,
      },
      redirect: "follow",
    });

    const headers = {};
    driveRes.headers.forEach((val, key) => {
      headers[key] = val;
    });

    res.writeHead(driveRes.status, headers);

    const nodeStream = Readable.fromWeb(driveRes.body);
    nodeStream.pipe(res);
    count = count + 1;
    console.log("Range requested:", range);
    console.log("Drive response status:", driveRes.status);
    console.log("Drive headers:", [...driveRes.headers]);
  } catch (err) {
    console.error("Proxy error:", err);
    if (!res.headersSent) {
      res.status(500).send("Error streaming video");
    }
  }
});

app.listen(PORT, () => {
  console.log(`🎬 Proxy server running at http://localhost:${PORT}`);
});
