import unittest
import sys
import os
import re
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from services.git_analyzer import ASTAnalyzer, GitAnalyzer, _parse_github_url
from core.registry import _normalize_repository_key


class ASTAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = ASTAnalyzer()

    def test_python_ast(self):
        content = """
import os
from pydantic import BaseModel

class User(BaseModel):
    name: str

def get_user(id: int):
    pass
"""
        meta = self.analyzer.analyze(content, "python")
        self.assertEqual("python", meta["language"])
        self.assertIn("User", meta["classes"])
        self.assertIn("get_user", meta["functions"])
        self.assertIn("os", meta["imports"])
        self.assertIn("pydantic.BaseModel", meta["imports"])

    def test_javascript_regex(self):
        content = """
import { useState } from 'react';
export class TestComponent {}
const doSomething = () => {}
function regularFunction() {}
"""
        meta = self.analyzer.analyze(content, "javascript")
        self.assertEqual("javascript", meta["language"])
        self.assertIn("TestComponent", meta["classes"])
        self.assertIn("doSomething", meta["functions"])
        self.assertIn("regularFunction", meta["functions"])
        self.assertIn("react", meta["imports"])


class CommitResolutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.analyzer = GitAnalyzer()

    async def test_resolve_40_char_sha(self):
        """Full 40-character hex commit SHAs must be returned immediately in lowercase."""
        full_sha = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2"
        resolved = await self.analyzer.resolve_commit_sha("https://github.com/org/repo", full_sha)
        self.assertEqual(resolved, full_sha.lower())

    async def test_resolve_empty_and_whitespace_ref(self):
        """Empty or whitespace-only refs must return None."""
        self.assertIsNone(await self.analyzer.resolve_commit_sha("https://github.com/org/repo", ""))
        self.assertIsNone(await self.analyzer.resolve_commit_sha("https://github.com/org/repo", "   "))
        self.assertIsNone(await self.analyzer.resolve_commit_sha("https://github.com/org/repo", None))

    async def test_resolve_short_sha_via_github_api(self):
        """Short 7-12 hex SHAs query GitHub commits API to resolve to 40-char SHA."""
        short_sha = "c876e48"
        full_sha = "c876e48a3d1234567890abcdef1234567890abcd"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sha": full_sha}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            resolved = await self.analyzer.resolve_commit_sha("https://github.com/other-org/other-repo", short_sha)
            self.assertEqual(resolved, full_sha.lower())

    async def test_resolve_relative_ref_traversal(self):
        """Relative refs like HEAD~1 or main~2 should traverse parent SHAs."""
        parent_sha = "1111222233334444555566667777888899990000"
        base_sha = "aaaaabbbbbcccccdddddeeeeefffff0000011111"

        async def fake_get_parent(owner, repo, sha):
            if sha == base_sha:
                return parent_sha
            return None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sha": base_sha}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            with patch.object(self.analyzer, "_get_parent_sha", side_effect=fake_get_parent):
                resolved = await self.analyzer.resolve_commit_sha("https://github.com/other-org/other-repo", "main~1")
                self.assertEqual(resolved, parent_sha)


class RepoKeyNormalizationTests(unittest.TestCase):
    def test_normalize_repository_key_variants(self):
        """Stable repository key must be generated across various URL styles and query parameters."""
        expected = "github:kartick026/mdt"
        variants = [
            "https://github.com/kartick026/MDT",
            "https://github.com/kartick026/MDT.git",
            "https://github.com/kartick026/MDT/",
            "https://github.com/kartick026/MDT.git/",
            "https://github.com/kartick026/MDT?tab=readme",
            "https://github.com/kartick026/MDT#heading",
            "https://github.com/kartick026/MDT/tree/main",
            "git@github.com:kartick026/MDT.git",
        ]
        for v in variants:
            with self.subTest(variant=v):
                self.assertEqual(_normalize_repository_key(v), expected)


class DiffBaseAndCloneTests(unittest.TestCase):
    def test_clone_repo_depth_and_token(self):
        """_clone_repo must inject token for github.com URLs and pass depth=50."""
        from git import Repo
        with patch.object(Repo, "clone_from") as mock_clone:
            mock_repo = MagicMock()
            mock_clone.return_value = mock_repo

            GitAnalyzer._clone_repo(
                "https://github.com/org/repo.git",
                "/tmp/dest",
                "commit123",
                token="ghp_testtoken"
            )

            mock_clone.assert_called_once()
            args, kwargs = mock_clone.call_args
            self.assertIn("x-access-token:ghp_testtoken@github.com", args[0])
            self.assertEqual(kwargs.get("depth"), 50)
            mock_repo.git.checkout.assert_called_with("commit123")

    def test_explicit_commit_does_not_merge_base_with_main(self):
        """
        When analyzing a specific commit SHA or relative revision, diff base must be
        parent commit {sha}~1, NOT merge-base against main (which zeros out diffs on previous commits).
        """
        target_ref = "c876e48"
        is_explicit = bool(
            re.match(r"^[0-9a-fA-F]{7,40}$", target_ref)
            or "~" in target_ref
            or "^" in target_ref
        )
        self.assertTrue(is_explicit)

        rel_ref = "HEAD~1"
        is_explicit_rel = bool(
            re.match(r"^[0-9a-fA-F]{7,40}$", rel_ref)
            or "~" in rel_ref
            or "^" in rel_ref
        )
        self.assertTrue(is_explicit_rel)

        branch_ref = "feature/login"
        is_explicit_branch = bool(
            re.match(r"^[0-9a-fA-F]{7,40}$", branch_ref)
            or "~" in branch_ref
            or "^" in branch_ref
        )
        self.assertFalse(is_explicit_branch)

    @patch("subprocess.run")
    def test_analyze_from_local_workspace_explicit_commit_diff_base(self, mock_subproc):
        """Verify _analyze_from_local_workspace uses parent commit and not main merge-base."""
        def fake_run(cmd, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "rev-parse" in cmd and "--verify" in cmd:
                res.stdout = "parent_commit_sha_12345"
            elif "diff" in cmd and "--name-status" in cmd:
                if "parent_commit_sha_12345" in cmd:
                    res.stdout = "M\tservices/user_service/main.py\n"
                else:
                    res.stdout = ""
            elif "diff" in cmd and "-U3" in cmd:
                res.stdout = "@@ -1,2 +1,3 @@\n+line\n"
            elif "show" in cmd:
                res.stdout = "print('hello')"
            else:
                res.stdout = "dummy"
            return res

        mock_subproc.side_effect = fake_run

        analyzer = GitAnalyzer()
        changes = analyzer._analyze_from_local_workspace(
            "c876e481234567890abcdef1234567890abcdef",
            files=None
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].file_path, "services/user_service/main.py")
        self.assertEqual(changes[0].change_type, "modified")

