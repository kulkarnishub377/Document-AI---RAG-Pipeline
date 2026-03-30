import uvicorn  # type: ignore
from loguru import logger  # type: ignore
import config  # type: ignore

if __name__ == "__main__":
    logger.info(f"Starting DocuAI Studio v{config.__version__}...")
    logger.info(f"Access the frontend at: http://{config.API_HOST}:{config.API_PORT}")
    logger.info(f"LLM Provider: {config.LLM_PROVIDER}")

    if config.LLM_PROVIDER == "openai" and config.OPENAI_API_KEY:
        logger.info(f"  OpenAI model: {config.OPENAI_MODEL}")
    else:
        logger.info(f"  Ollama model: {config.OLLAMA_MODEL} @ {config.OLLAMA_BASE_URL}")
        logger.info("  (If Ollama is offline, the app runs in Demo Mode with heuristic answers)")

    # Run the FastAPI application using uvicorn programmatically
    uvicorn.run(
        "api.app:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=False  # Set to True for development mode
    )
