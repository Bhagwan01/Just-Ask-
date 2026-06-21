import time
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
PDF_PATH = r"D:\Downloads\Blood_lab_report.pdf"

print("Waiting for backend to start...")
for _ in range(60):
    try:
        r = httpx.get(f"{BASE_URL}/health")
        if r.status_code == 200:
            print("Backend is up!")
            break
    except httpx.ConnectError:
        time.sleep(2)
else:
    print("Backend failed to start in time.")
    exit(1)

print("\nUploading document...")
with open(PDF_PATH, "rb") as f:
    files = {"file": open(PDF_PATH, "rb")}
    upload_res = httpx.post(f"{BASE_URL}/documents/upload", files=files)

print("Upload response:", upload_res.status_code, upload_res.text)
if upload_res.status_code not in (200, 202):
    exit(1)

doc_id = upload_res.json()["id"]

print("\nWaiting for document processing...")
for _ in range(30):
    status_res = httpx.get(f"{BASE_URL}/documents/{doc_id}/status")
    status_data = status_res.json()
    status = status_data["status"]
    print(f"Status: {status}")
    if status == "completed":
        print("Processing finished!")
        break
    elif status == "failed":
        print("Processing failed:", status_data.get("error_message"))
        exit(1)
    time.sleep(2)
else:
    print("Processing timed out.")
    exit(1)

print("\nQuerying LLM...")
query_payload = {
    "query": "What is the name of the patient and their blood group?",
    "document_ids": [doc_id],
    "top_k": 5
}
chat_res = httpx.post(f"{BASE_URL}/chat/query", json=query_payload, timeout=60.0)
print("Chat response status:", chat_res.status_code)
try:
    print("Answer:", chat_res.json().get("answer"))
except:
    print(chat_res.text)
