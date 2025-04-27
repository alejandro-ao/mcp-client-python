import logging
import sys

# Configure logging
logger = logging.getLogger("MCPClient")
logger.setLevel(logging.DEBUG)

# File handler with DEBUG level
file_handler = logging.FileHandler("mcp_client.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)

# Console handler with INFO level
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)
