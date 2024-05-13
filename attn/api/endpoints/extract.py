from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import logging
from typing import List, Optional
import json
from datetime import datetime
import sys
import os
from modal import Image, App, web_endpoint, Secret, Mount
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app_image = (
    Image.debian_slim(python_version="3.10")
    .pip_install(
        "requests",
        "anthropic"
    )
)

app = App(name="extract-svc", image=app_image, secrets=[Secret.from_name("my-anthropic-secret")])

class UserProfile(BaseModel):
    preferred_name: str = "Default Name"
    country_of_residence: str = "Default Country"
    age: int = 30
    job_title: str = "Default Job Title"
    job_function: str = "Default Job Function"
    interests: List[str] = ["technology", "science"]
    goals: str = "learn and explore"

class ArticleData(BaseModel):
    url: str
    accessed_date: datetime
    title: str
    keywords: List[str]
    description: str
    content: str
    article_urls: List[str]
    status: str

class ExtractRequest(BaseModel):
    articles: List[ArticleData]
    user_profile: UserProfile  # Use the UserProfile model instead of dict
    num_urls: Optional[int] = 10  # Default number of URLs to extract
    query: str = Field(default="")  # Add this line to include the query attribute

@app.function(mounts=[
    Mount.from_local_dir(
        local_path="/Users/erniesg/code/erniesg/shareshare/attn/api/endpoints",
        remote_path="/app/endpoints",
        condition=lambda pth: "extract.py" not in pth,
        recursive=True
    )
])
@web_endpoint(method="POST")
async def extract(request: ExtractRequest):
    logger.info(f"Files in the current directory: {os.listdir('.')}")
    logger.info(f"Files at root directory: {os.listdir('/')}")
    logger.info(f"Files in the /app directory: {os.listdir('/app')}")
    logger.info(f"Current working directory: {os.getcwd()}")
    sys.path.insert(0, '/app')
    sys.path.insert(0, '/app/endpoints')
    logger.info(f"Current sys.path: {sys.path}")
    logger.info(f"Files in the /app/endpoints directory: {os.listdir('/app/endpoints')}")

    article_urls = await extract_article_urls(request)
    # Placeholder for calling extract_structure
    return {"article_urls": article_urls}

async def extract_article_urls(request: ExtractRequest, model_name: str = "claude-3-haiku-20240307"):
    from llm_handler import LLMHandler
    from prompts import get_prompts
    llm_handler = LLMHandler()

    if not request.articles:
        raise HTTPException(status_code=400, detail="No articles provided")

    all_urls = []  # List to collect URLs from all articles

    # Iterate over each article in the request
    for article in request.articles:
        logger.info(f"Processing article {article.title} with URL: {article.url}")
        try:
            system_prompt, message_prompt = get_prompts(
                "extract_article_urls", request,
                url=article.url,
                title=article.title,
                keywords=','.join(article.keywords),
                description=article.description,
                content=article.content
            )
        except KeyError:
            logger.error("Prompt configuration for 'extract_article_urls' not found.")
            raise HTTPException(status_code=500, detail="Configuration error")

        # Call the LLM and handle the response for each article
        try:
            logger.info(f"Extract - Preparing to call LLM for article with URL: {article.url}")
            response_text = llm_handler.call_llm(
                "extract_article_urls",
                request,
                model_name=model_name,
                url=article.url,
                title=article.title,
                keywords=','.join(article.keywords),
                description=article.description,
                content=article.content
            )
            urls = parse_urls_from_response(response_text)
            all_urls.extend(urls)  # Add the extracted URLs to the main list
        except Exception as e:
            logger.error(f"LLM call failed for article {article.url}: {str(e)}")
            # Optionally continue to the next article or raise an HTTPException
            continue  # Continue processing next articles even if one fails

    return all_urls  # Return the collected URLs from all articles

def extract_structure():
    # Placeholder for extract_structure implementation
    pass

def parse_urls_from_response(text: str) -> List[str]:
    try:
        data = json.loads(text)
        urls = [item['url'] for item in data['urls']]
        logger.info(f"URLs parsed from response: {urls}")
        return urls
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing URLs from response: {str(e)}")
        # Fallback to regex extraction if JSON parsing fails
        return extract_urls_fallback(text)

def extract_urls_fallback(text: str) -> List[str]:
    # Fallback method to extract URLs using regular expressions
    urls = re.findall(r'https?://\S+', text)  # Adjust regex as needed
    logger.info(f"URLs parsed using fallback approach: {urls}")
    return urls