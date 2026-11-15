import uvicorn
from backend.config import HOST, PORT

if __name__ == "__main__":
    print(f"Starting Telesale Audio Recording Web Application on http://localhost:{PORT}")
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=True)

