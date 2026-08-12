import logging
from dotenv import load_dotenv
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def main():
    logger.info("Initializing Agent foundation...")
    
    # Check configurations
    required_vars = [
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
        "GROQ_API_KEY", "GROQ_MODEL",
        "STT_PROVIDER", "TTS_PROVIDER", "LLM_PROVIDER"
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
            
    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")
    else:
        logger.info("All essential agent environment configurations loaded successfully.")

if __name__ == "__main__":
    main()
