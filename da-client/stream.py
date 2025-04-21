from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import logging
import asyncio
import datetime
import json
import sys
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, AsyncGenerator
import aiohttp
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Ensure logger level is set to DEBUG

# Configuration
# DATAVTAR_BASE_URL = "http://127.0.0.1:8000"
DATAVTAR_BASE_URL = "https://dev.ai.datavtar.com"
DATAVTAR_API_KEY = "dvt_228496802c7f4f02bcef4c361b56aece"  # Replace with environment variable in production


def get_python_config():
    """Get configuration settings."""
    return {
        'datavtar_model_code': '3a-buildit-first-conv-text',
    }


class DatavtarAIClient:
    def __init__(self, api_key: str, base_url: str):
        logger.debug(f"Initializing DatavtarAIClient with API Key: {api_key[:5]}*** and Base URL: {base_url}")
        
        if not api_key:
            raise ValueError("DatavtarAI API key must be provided")
            
        self.api_key = api_key
        self.base_url = base_url
        self.session = None
        self.config = get_python_config()
        self.auth_token = None
        self.token_expiry = None
        self.refresh_lock = asyncio.Lock()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        await self.get_auth_token()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_auth_token(self) -> str:
        """Get a valid authentication token, refreshing if necessary."""
        async with self.refresh_lock:
            current_time = datetime.datetime.now(datetime.timezone.utc)
            
            # If token doesn't exist or will expire in next 2 minutes, refresh it
            if (not self.auth_token or not self.token_expiry or 
                self.token_expiry - current_time < datetime.timedelta(minutes=2)):
                await self.refresh_token()
            
            return self.auth_token

    async def ensure_session(self):
        """Ensure an aiohttp session exists and is active."""
        if not self.session or self.session.closed:
            # Create a session with no buffering
            timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
            connector = aiohttp.TCPConnector(force_close=True)  # Force close connections to avoid buffering
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            logger.debug("Created new aiohttp session with force_close=True")
        return self.session

    async def refresh_token(self):
        """Refresh the authentication token."""
        try:
            session = await self.ensure_session()
            auth_url = f"{self.base_url}/api/v1/auth/token"
            
            headers = {
                'X-API-Key': self.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'username': 'regular_user',
                'password': 'userPassword123',
                'scope': 'user'
            }
            
            logger.debug(f"Requesting new auth token from {auth_url}")
            async with session.post(auth_url, headers=headers, data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Auth token refresh failed: {response.status} - {error_text}")
                    raise Exception(f"Auth token refresh failed: {response.status} - {error_text}")
                
                auth_data = await response.json()
                self.auth_token = auth_data['access_token']
                # Set expiry 2 minutes before actual expiry for safety margin
                self.token_expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=auth_data['expires_in'] - 120)
                
                logger.info(f"Successfully refreshed auth token. Expires at {self.token_expiry}")
        except Exception as e:
            logger.error(f"Error refreshing auth token: {str(e)}")
            raise

    async def stream_api_content_unbuffered(self, request_data: dict) -> AsyncGenerator[bytes, None]:
        """
        Stream content from the API with no buffering.
        This is achieved by:
        1. Using a TCP connector with force_close=True
        2. Using chunked encoding to prevent buffering
        3. Setting specific headers to disable buffering
        4. Processing each chunk immediately
        """
        token = await self.get_auth_token()
        
        # Create a special unbuffered session for this request
        connector = aiohttp.TCPConnector(force_close=True, limit=1)
        async with aiohttp.ClientSession(connector=connector) as session:
            
            # Set headers to discourage buffering
            headers = {
                'Authorization': f'Bearer {token}',
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',  # Request plain text instead of SSE
                'Cache-Control': 'no-cache',  # Discourage caching
                'Connection': 'close',  # Don't keep connection alive
                # Curl-like headers
                'User-Agent': 'curl/7.79.1',
                'Accept-Encoding': 'identity'  # No compression to avoid buffering
            }
            
            logger.debug(f"Making unbuffered API request to {self.base_url}/api/v1/stream")
            async with session.post(
                f'{self.base_url}/api/v1/stream',
                json=request_data,
                headers=headers,
                chunked=True,  # Use chunked encoding
                timeout=None   # No timeout for streaming
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API error: {response.status} - {error_text}")
                    yield f"Error: {response.status} - {error_text}".encode()
                    return
                
                # Use the lowest-level iterator for maximum control over buffering
                logger.debug("Beginning to read response bytes...")
                chunk_count = 0
                
                # Process chunks as they arrive
                async for chunk in response.content.iter_any():
                    chunk_count += 1
                    if chunk:
                        logger.debug(f"Received chunk #{chunk_count}: {len(chunk)} bytes")
                        # Yield the chunk directly without any processing
                        # chunk_str = chunk.decode('utf-8')
                        # if chunk_str.startswith('data:'):
                        #     chunk_str = chunk_str[5:]  # Only remove 'data:' prefix, preserve all spaces
                        # yield chunk_str.encode('utf-8')
                        yield chunk
                
                logger.debug(f"Streaming complete. Received {chunk_count} chunks total.")

    # Close method for cleanup
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("Session closed")


# Create a global client
datavtar_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    # Initialize the Datavtar AI client at startup
    global datavtar_client
    logger.info("Initializing Datavtar AI client")
    datavtar_client = DatavtarAIClient(api_key=DATAVTAR_API_KEY, base_url=DATAVTAR_BASE_URL)
    await datavtar_client.get_auth_token()  # Initialize token
    logger.info("Application startup complete")
    
    yield
    
    # Clean up at shutdown
    logger.info("Application shutting down")
    if datavtar_client:
        await datavtar_client.close()


app = FastAPI(title="Datavtar AI Streaming API", lifespan=lifespan)

@app.middleware("http")
async def log_request(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    if request.method == "POST":
        try:
            body = await request.body()
            logger.debug(f"Request body: {body.decode()}")
        except Exception as e:
            logger.error(f"Error reading request body: {e}")
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request model
class StreamRequest(BaseModel):
    chat: str = Field(..., description="Chat message content")
    history: List[Dict[str, Any]] = Field(default=[], description="Chat history")
    model_code: str = Field(default="3a-buildit-first-conv-text", description="Model code to use")
    input_type: str = Field(default="text", description="Input type")
    output_format: str = Field(default="code", description="Output format")
    priority: int = Field(default=2, description="Priority level")
    format: str = Field(default="simple", description="Format type")
    additional_params: Optional[Dict[str, Any]] = Field(default=None, description="Additional parameters")
    
    model_config = {
        "protected_namespaces": ()  # Disable protected namespace warnings
    }

@app.post("/stream")
async def stream_content_endpoint(request_data: StreamRequest):
    """Stream content from Datavtar API with unbuffered streaming."""
    logger.info(f"Received streaming request for chat: {request_data.chat[:30]}...")
    logger.debug(f"Full request data: {request_data.dict()}")
    
    global datavtar_client
    if not datavtar_client:
        logger.warning("Client not initialized, creating new client")
        datavtar_client = DatavtarAIClient(api_key=DATAVTAR_API_KEY, base_url=DATAVTAR_BASE_URL)
        await datavtar_client.get_auth_token()
    
    # Prepare payload - map chat to content for the API
    payload = request_data.dict(exclude_none=True)
    
    # Format the history and current message into a single content string
    formatted_history = ""
    # Reverse the history to show most recent messages first
    for msg in reversed(request_data.history):
        role = msg['role']
        text = msg['parts'][0]['text']  # Assuming single part messages
        formatted_history += f"{role}: {text}\n"
    
    # Combine history with current message
    current_message = payload.pop('chat')
    payload['content'] = f"{formatted_history}user: {current_message}"
    
    if request_data.additional_params:
        additional_params = payload.pop("additional_params")
        payload.update(additional_params)
    logger.debug(f"Prepared payload: {payload}")

    async def stream_generator():
        try:
            logger.info("Starting unbuffered streaming")
            # Use the unbuffered streaming approach
            async for chunk in datavtar_client.stream_api_content_unbuffered(payload):
                yield chunk
                
        except Exception as e:
            logger.error(f"Streaming error: {str(e)}", exc_info=True)
            error_message = f"Error: {str(e)}"
            if isinstance(error_message, str):
                yield error_message.encode()
            else:
                yield error_message
    
    logger.info("Returning StreamingResponse")
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
        # media_type="text/plain"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("Health check requested")
    try:
        global datavtar_client
        if datavtar_client:
            token = await datavtar_client.get_auth_token()
            token_status = "valid" if token else "invalid"
        else:
            token_status = "client not initialized"
        
        logger.info(f"Health check successful, token status: {token_status}")
        return {
            "status": "ok",
            "token_status": token_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server")
    uvicorn.run(app, host="0.0.0.0", port=9000)