import uvicorn
import logging
import sys
import os

# Set up extremely heavy logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("main_server.log")
    ]
)
logger = logging.getLogger("main_server")

logger.debug("Starting main.py execution...")

def main():
    logger.debug("Entering main() function in main.py")
    
    os.environ.setdefault("LLM_BACKEND", "external")
    os.environ.setdefault("API_PORT", "8000")
    os.environ.setdefault("API_HOST", "0.0.0.0")
    
    logger.debug(f"Environment LLM_BACKEND set to: {os.environ.get('LLM_BACKEND')}")
    logger.debug("About to import app.api.model_server:app")
    
    try:
        from app.api.model_server import app
        logger.debug("Successfully imported model server")
        
    except Exception as e:
        logger.exception(f"Failed to import or initialize model_server: {e}")
        sys.exit(1)
        
    port = int(os.environ.get("API_PORT", 8000))
    logger.debug(f"Starting uvicorn server on {os.environ['API_HOST']}:{port}")
    
    try:
        uvicorn.run(app, host=os.environ["API_HOST"], port=port, log_level="info")
    except Exception as e:
        logger.exception(f"Uvicorn server crashed: {e}")
        
if __name__ == "__main__":
    logger.debug("main.py __main__ block triggered")
    main()
