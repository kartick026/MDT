"""
LLM Explainer Service
Generates human-readable explanations using LLM
"""
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from core.config import settings

logger = logging.getLogger(__name__)


class LLMExplainer:
    """
    Generates explanations using LLM with RAG context
    Part of the HMDA algorithm's AI-assisted reasoning
    """

    def __init__(self):
        self.client = None
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your_openai_api_key_here":
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

    async def explain(
        self,
        changes: List,
        impacted_services: List[str],
        risk_score: float,
        context: Dict[str, Any]
    ) -> str:
        """
        Generate a human-readable explanation of the impact analysis

        Args:
            changes: List of code changes
            impacted_services: Services likely affected
            risk_score: Calculated risk score (0-100)
            context: Retrieved context from ChromaDB

        Returns:
            Human-readable explanation string
        """
        if not self.client:
            return self._fallback_explanation(changes, impacted_services, risk_score)

        try:
            # Build prompt with retrieved context
            prompt = self._build_explanation_prompt(
                changes, impacted_services, risk_score, context
            )

            response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a software engineering expert analyzing code changes for impact. Provide concise, actionable explanations. Avoid speculating beyond what the data shows."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.3  # Low temperature for factual responses
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LLM explanation failed: {e}")
            return self._fallback_explanation(changes, impacted_services, risk_score)

    def _build_explanation_prompt(
        self,
        changes: List,
        impacted_services: List[str],
        risk_score: float,
        context: Dict[str, Any]
    ) -> str:
        """Build the prompt for LLM explanation"""
        changed_files = [getattr(c, 'file_path', str(c)) for c in changes]
        severity = self._get_severity_label(risk_score)

        # Get retrieved context if available
        retrieved_docs = context.get("documents", [])
        context_section = ""
        if retrieved_docs:
            context_section = f"\n\nRelevant historical context:\n" + "\n".join(
                f"- {doc[:200]}..." for doc in retrieved_docs[:3]
            )

        return f"""
Analyze the following code change impact:

Risk Score: {risk_score}/100 ({severity})
Changed Files: {', '.join(changed_files)}
Potentially Impacted Services: {', '.join(impacted_services) if impacted_services else 'None identified'}

Provide a brief explanation (2-3 sentences) of:
1. Why these changes might impact the listed services
2. What developers should review before deployment{context_section}
"""

    def _fallback_explanation(
        self,
        changes: List,
        impacted_services: List[str],
        risk_score: float
    ) -> str:
        """Fallback explanation when LLM is unavailable"""
        changed_files = [getattr(c, 'file_path', str(c)) for c in changes]
        severity = self._get_severity_label(risk_score)

        explanation = f"This change has a {severity} risk score of {risk_score}/100. "
        explanation += f"{len(changes)} file(s) were modified: {', '.join(changed_files[:5])}"

        if impacted_services:
            explanation += f"\n\nPotentially impacted services: {', '.join(impacted_services)}"
        else:
            explanation += "\n\nNo downstream services are expected to be impacted based on the dependency graph."

        return explanation

    def _get_severity_label(self, risk_score: float) -> str:
        """Convert score to severity label"""
        if risk_score >= 75:
            return "Critical"
        elif risk_score >= 50:
            return "High"
        elif risk_score >= 25:
            return "Medium"
        else:
            return "Low"

    async def suggest_remediation(
        self,
        impacted_services: List[str],
        changes: List,
        risk_score: float
    ) -> List[str]:
        """
        Suggest specific remediation actions
        Uses LLM to generate targeted recommendations
        """
        if not self.client or not impacted_services:
            return self._fallback_remediation(impacted_services, risk_score)

        try:
            prompt = f"""
Risk Score: {risk_score}/100
Impacted Services: {', '.join(impacted_services)}
Changes: {[getattr(c, 'file_path', str(c)) for c in changes]}

Provide 3-5 specific remediation steps to take before deploying these changes.
Focus on testing, coordination, and safeguards. Be specific and actionable.
"""

            response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a DevOps expert. Provide specific, actionable remediation steps."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=300,
                temperature=0.4
            )

            suggestions = response.choices[0].message.content
            return [s.strip() for s in suggestions.split('\n') if s.strip()]

        except Exception as e:
            logger.error(f"Remediation suggestion failed: {e}")
            return self._fallback_remediation(impacted_services, risk_score)

    def _fallback_remediation(
        self,
        impacted_services: List[str],
        risk_score: float
    ) -> List[str]:
        """Fallback remediation suggestions"""
        suggestions = []

        if risk_score >= 50:
            suggestions.append("Schedule a code review with impacted service owners")

        if impacted_services:
            suggestions.append(
                f"Notify teams for: {', '.join(impacted_services[:3])}"
            )

        suggestions.append("Run integration tests for affected services")
        suggestions.append("Enable gradual rollout with canary deployment")

        return suggestions