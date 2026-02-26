from fastapi import FastAPI

app = FastAPI(title="Technical Service")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "technical"}

@app.get("/")
async def root():
    return {"message": "Hello World from Technical Service"}
