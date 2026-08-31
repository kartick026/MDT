import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from services.git_analyzer import ASTAnalyzer

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
