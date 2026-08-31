import time
import httpx
import logging
from typing import Optional
import jwt

from core.config import settings

logger = logging.getLogger(__name__)

class GitHubAppAuth:
    """Manages GitHub App authentication and installation tokens."""
    
    # Simple in-memory cache to avoid regenerating tokens for every commit
    # Structure: { installation_id: (token, expiry_timestamp) }
    _token_cache = {}

    @staticmethod
    def get_jwt() -> Optional[str]:
        """Generate the JWT needed to authenticate as the GitHub App."""
        if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
            return None
            
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60), # maximum 10 minute expiration for GitHub App JWT
            "iss": settings.GITHUB_APP_ID
        }
        
        # Handle newlines if passed directly in an environment variable string
        private_key = settings.GITHUB_APP_PRIVATE_KEY.replace('\\n', '\n')
        
        try:
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as e:
            logger.error(f"Failed to generate GitHub App JWT: {e}")
            return None

    @classmethod
    async def get_installation_token_for_repo(cls, repo_url: str) -> Optional[str]:
        """
        Gets an installation access token for a specific repository.
        Falls back to GITHUB_TOKEN (PAT) if the App isn't configured.
        """
        jwt_token = cls.get_jwt()
        if not jwt_token:
            return settings.GITHUB_TOKEN # fallback to PAT
            
        # Parse owner/repo from URL
        # e.g., https://github.com/kartick026/MDT or kartick026/MDT
        repo_path = repo_url.replace("https://github.com/", "").replace(".git", "")
        if repo_path.startswith("http"):
            # fallback if it's a weird url
            repo_path = "/".join(repo_path.split("/")[-2:])
            
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MDT-App"
        }
        
        async with httpx.AsyncClient() as client:
            # 1. Look up the installation ID for this specific repository
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo_path}/installation",
                    headers=headers
                )
                resp.raise_for_status()
                installation_id = resp.json()["id"]
            except Exception as e:
                logger.warning(f"Could not find GitHub App installation for {repo_path}: {e}")
                return settings.GITHUB_TOKEN

            # Check cache
            cached = cls._token_cache.get(installation_id)
            if cached and cached[1] > time.time() + 60:
                return cached[0]

            # 2. Generate the temporary installation access token
            try:
                resp = await client.post(
                    f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                    headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                token = data["token"]
                
                # Cache it (GitHub tokens usually expire in 1 hour)
                cls._token_cache[installation_id] = (token, time.time() + 3500)
                return token
            except Exception as e:
                logger.error(f"Failed to generate installation token for ID {installation_id}: {e}")
                return settings.GITHUB_TOKEN
