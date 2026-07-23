"""
Git Analysis Service
Handles git diff parsing, AST extraction, and code change analysis
"""
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from git import Repo
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class ChangeInfo:
    """Information about a code change"""
    file_path: str
    change_type: str  # added, modified, deleted
    diff_content: str
    additions: int
    deletions: int
    old_content: str
    new_content: str


class GitAnalyzer:
    """Analyzes git changes for impact assessment"""

    def __init__(self):
        self.supported_extensions = {
            '.py', '.js', '.ts', '.java', '.go', '.rs',
            '.cpp', '.c', '.h', '.rb', '.php', '.cs'
        }

    async def analyze_push(
        self,
        repo_url: str,
        commit_sha: str,
        changed_files: List[str]
    ) -> List[ChangeInfo]:
        """
        Analyze a push event and extract change information

        Args:
            repo_url: Repository URL
            commit_sha: Commit SHA that was pushed
            changed_files: List of files that changed

        Returns:
            List of ChangeInfo objects
        """
        logger.info(f"Analyzing push: repo={repo_url}, commit={commit_sha}")

        changes = []
        for file_path in changed_files:
            # Filter by supported extensions
            ext = file_path.split('.')[-1] if '.' in file_path else ''
            if f'.{ext}' in self.supported_extensions:
                # In a real implementation, this would clone the repo and get diffs
                # For now, return placeholder data
                change = await self._analyze_file(file_path, commit_sha)
                changes.append(change)

        return changes

    async def _analyze_file(self, file_path: str, commit_sha: str) -> ChangeInfo:
        """Analyze a single file change"""
        # Placeholder - in production, this would use PyGitLib to get actual diffs
        return ChangeInfo(
            file_path=file_path,
            change_type="modified",
            diff_content="",
            additions=0,
            deletions=0,
            old_content="",
            new_content=""
        )

    async def get_file_diff(self, repo_path: str, commit_sha: str, file_path: str) -> str:
        """Get the diff for a specific file at a specific commit"""
        try:
            repo = Repo(repo_path)
            commit = repo.commit(commit_sha)
            diff = repo.git.diff(f"{commit_sha}^", commit_sha, "--", file_path)
            return diff
        except Exception as e:
            logger.error(f"Failed to get diff for {file_path}: {e}")
            return ""

    async def extract_ast_metadata(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Extract AST metadata from code file
        Uses tree-sitter for parsing
        """
        # Placeholder for tree-sitter integration
        return {
            "file": file_path,
            "functions": [],
            "classes": [],
            "imports": [],
            "exports": []
        }



class ASTAnalyzer:
    """AST-based code analysis using tree-sitter"""

    def __init__(self):
        try:
            import tree_sitter_languages
            self.parser_available = True
        except ImportError:
            logger.warning("tree-sitter-languages not available, using fallback")
            self.parser_available = False

    async def parse_file(self, content: str, language: str) -> Dict[str, Any]:
        """Parse a file and extract AST information"""
        if not self.parser_available:
            return await self._fallback_parse(content, language)

        # In production, use tree-sitter to parse
        return await self._fallback_parse(content, language)

    async def _fallback_parse(self, content: str, language: str) -> Dict[str, Any]:
        """Fallback parsing when tree-sitter is not available"""
        functions = []
        classes = []

        # Simple regex-based extraction as fallback
        import re

        if language == "python":
            functions = re.findall(r'def (\w+)\(', content)
            classes = re.findall(r'class (\w+)', content)
        elif language in ("javascript", "typescript"):
            functions = re.findall(r'function (\w+)\(', content)
            functions += re.findall(r'const (\w+)\s*=', content)
            classes = re.findall(r'class (\w+)', content)

        return {
            "functions": functions,
            "classes": classes,
            "language": language
        }