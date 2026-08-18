const express = require("express");
const { GoogleAuth } = require("google-auth-library");
const { Readable } = require("stream");

const app = express();
const PORT = process.env.PORT || 5000;
const API_KEY =
  process.env.GOOGLE_API_KEY || process.env.GOOGLE_DRIVE_API_KEY || "";
const KEYFILE = process.env.GOOGLE_APPLICATION_CREDENTIALS || "";
const SCOPES = ["https://www.googleapis.com/auth/drive.readonly"];
const DRIVE_USER_AGENT =
  process.env.GOOGLE_DRIVE_USER_AGENT ||
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

const auth = KEYFILE
  ? new GoogleAuth({
      keyFile: KEYFILE,
      scopes: SCOPES,
    })
  : null;

let count = 0;

app.get("/health", (_req, res) => {
  const authMode = API_KEY ? "api_key" : auth ? "service_account" : "missing";
  if (authMode === "missing") {
    return res.status(503).json({
      ok: false,
      auth: authMode,
      error: "Set GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS",
    });
  }

  res.json({
    ok: true,
    auth: authMode,
  });
});

async function authHeaders() {
  if (API_KEY) return {};
  if (!auth) {
    throw new Error(
      "Set GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS for Drive access"
    );
  }

  const client = await auth.getClient();
  const tokenResponse = await client.getAccessToken();
  const accessToken = tokenResponse.token;
  if (!accessToken) {
    throw new Error("Google auth did not return an access token");
  }

  return { Authorization: `Bearer ${accessToken}` };
}

app.get("/video/:fileId", async (req, res) => {
  const { fileId } = req.params;
  const range = req.headers.range;
  console.log("Count:", count);
  if (!range) {
    return res.status(400).send("Requires Range header");
  }

  try {
    const driveUrl =
      `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media` +
      (API_KEY ? `&key=${encodeURIComponent(API_KEY)}` : "");

    const driveRes = await fetch(driveUrl, {
      headers: {
        Range: range,
        "User-Agent": DRIVE_USER_AGENT,
        Accept: req.headers.accept || "video/mp4,video/*,*/*",
        "Accept-Language": req.headers["accept-language"] || "en-US,en;q=0.9",
        ...(await authHeaders()),
      },
      redirect: "follow",
    });

    if (!driveRes.body) {
      return res.status(502).send("Drive response did not include a body");
    }

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
  console.log(`Proxy server running at http://localhost:${PORT}`);
});
