"""Webhook payload schemas"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class PushEvent(BaseModel):
    """Git push event data"""
    repo_url: str
    branch: str
    commit_sha: str
    changed_files: List[str]
    commit_message: str
    author: str


class WebhookPayload(BaseModel):
    """Generic webhook payload wrapper"""
    event: str
    data: Dict[str, Any]