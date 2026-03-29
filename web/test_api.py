#!/usr/bin/env python3
"""End-to-end test for the deployed minutes Worker API."""
import urllib.request
import json
import time

BASE = "https://minutes-worker.sndworks.workers.dev/api"
PASSCODE = "s&dWks2026"
AUDIO_PATH = "/Users/marksnd/myPythonCode/Audio2Text/audio/260120.ogg"

def api_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    req.add_header("X-Passcode", PASSCODE)
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code}: {e.read().decode()}")
        return None

def upload():
    boundary = "----TestBoundary123"
    with open(AUDIO_PATH, "rb") as f:
        audio_data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="260120.ogg"\r\n'
        f"Content-Type: audio/ogg\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/upload", data=body, method="POST")
    req.add_header("X-Passcode", PASSCODE)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read().decode())

def start_process(job_id):
    data = json.dumps({}).encode()
    req = urllib.request.Request(f"{BASE}/process/{job_id}", data=data, method="POST")
    req.add_header("X-Passcode", PASSCODE)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode())

if __name__ == "__main__":
    print("=== Upload ===")
    result = upload()
    job_id = result["jobId"]
    print(f"jobId={job_id}")

    print("=== Start Processing ===")
    print(start_process(job_id))

    print("=== Polling ===")
    for i in range(60):
        time.sleep(5)
        s = api_get(f"/status/{job_id}")
        if s:
            step = s.get("step", "?")
            prog = s.get("progress", 0)
            msg = s.get("message", "")
            err = s.get("error", "")
            print(f"  [{i*5:3d}s] step={step} progress={prog} msg={msg}")
            if step == "completed":
                print("=== SUCCESS ===")
                break
            if step == "error":
                print(f"=== FAILED: {err} ===")
                break
        else:
            print(f"  [{i*5:3d}s] no response")
