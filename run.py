import uvicorn  # type: ignore
from loguru import logger  # type: ignore
import config  # type: ignore

if __name__ == "__main__":
    logger.info("Starting Document AI + RAG Pipeline Server...")
    logger.info(f"Access the frontend at: http://{config.API_HOST}:{config.API_PORT}")
    
    # Run the FastAPI application using uvicorn programmatically
    uvicorn.run(
        "api.app:app", 
        host=config.API_HOST, 
        port=config.API_PORT, 
        reload=False  # Set to True for development mode
    )
