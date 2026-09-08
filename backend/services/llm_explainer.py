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
            kwargs = {"api_key": settings.OPENAI_API_KEY}
            if settings.LLM_BASE_URL:
                kwargs["base_url"] = settings.LLM_BASE_URL
            self.client = AsyncOpenAI(**kwargs)

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

    async def suggest_remediation_with_edits(
        self,
        smells: List[Dict[str, Any]],
        impacted_services: List[str],
        changes: List,
        risk_score: float,
        connection_bugs: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Suggest remediations with structured GraphEdit actions.

        Each returned dict has:
          - ``text``: human-readable recommendation string
          - ``edits``: list of GraphEdit-compatible dicts

        Falls back to deterministic edits when LLM is offline.
        """
        from services.remediation_simulator import GraphEdit, generate_edits_for_smells

        if not self.client:
            return self._fallback_remediation_with_edits(
                smells, impacted_services, risk_score, connection_bugs
            )

        try:
            smell_summary = "\n".join(
                f"- [{s.get('severity', '?')}] {s.get('type', '?')}: "
                f"{s.get('description', '')}"
                for s in smells[:6]
            )

            prompt = f"""
Risk Score: {risk_score}/100
Impacted Services: {', '.join(impacted_services)}
Detected Architectural Smells:
{smell_summary or 'None detected'}

For the architecture and impacted services above, suggest specific remediations and provide the
corresponding graph edits as JSON.  Each edit is one of:
  {{"action": "remove_edge", "from_service": "X", "to_service": "Y"}}
  {{"action": "add_edge",    "from_service": "X", "to_service": "Y"}}
  {{"action": "add_node",    "from_service": "NEW_SERVICE_NAME"}}

Respond as a JSON array of objects, each with "text" (string) and
"edits" (array of edit objects).  Return ONLY the JSON array.
"""

            response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a software architect. Output valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                temperature=0.3,
            )

            import json

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                results = []
                for item in parsed:
                    text = item.get("text", "")
                    edits = []
                    for e in item.get("edits", []):
                        try:
                            edits.append(GraphEdit(**e).model_dump())
                        except Exception:
                            pass
                    if text and edits:
                        results.append({"text": text, "edits": edits})
                if results:
                    return results

        except Exception as e:
            logger.error(f"Structured remediation suggestion failed: {e}")

        return self._fallback_remediation_with_edits(
            smells, impacted_services, risk_score, connection_bugs
        )

    def _fallback_remediation_with_edits(
        self,
        smells: List[Dict[str, Any]],
        impacted_services: Optional[List[str]] = None,
        risk_score: float = 0.0,
        connection_bugs: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Deterministic remediation with graph edits — no LLM needed."""
        from services.remediation_simulator import GraphEdit, generate_edits_for_smells

        all_edits = generate_edits_for_smells(smells)
        results: List[Dict[str, Any]] = []

        # 1. Group edits by smell
        edit_idx = 0
        for smell in smells:
            stype = smell.get("type", "")
            services = smell.get("services", [])
            text = ""
            edits_for_smell: List[Dict[str, Any]] = []

            if "Circular" in stype:
                text = (
                    f"Break the circular dependency involving "
                    f"{', '.join(services)} by removing the back-edge."
                )
                while edit_idx < len(all_edits) and all_edits[edit_idx].action == "remove_edge":
                    edits_for_smell.append(all_edits[edit_idx].model_dump())
                    edit_idx += 1
                    break

            elif "Bottleneck" in stype or "God" in stype:
                text = (
                    f"Introduce a facade service in front of {services[0]} "
                    f"to redistribute incoming traffic."
                )
                for _ in range(2):
                    if edit_idx < len(all_edits):
                        edits_for_smell.append(all_edits[edit_idx].model_dump())
                        edit_idx += 1

            elif "Coupling" in stype:
                text = (
                    f"Add a gateway in front of {services[0]} to reduce "
                    f"direct coupling."
                )
                for _ in range(2):
                    if edit_idx < len(all_edits):
                        edits_for_smell.append(all_edits[edit_idx].model_dump())
                        edit_idx += 1

            elif "Dead" in stype or "Isolated" in stype:
                if services:
                    text = f"Integrate isolated service '{services[0]}' into topology or decommission unused service."
                    if edit_idx < len(all_edits):
                        edits_for_smell.append(all_edits[edit_idx].model_dump())
                        edit_idx += 1
                    else:
                        edits_for_smell.append(
                            GraphEdit(action="add_edge", from_service="order-service", to_service=services[0]).model_dump()
                        )

            if text and edits_for_smell:
                results.append({"text": text, "edits": edits_for_smell})

        # 2. Connection bugs remediations
        if connection_bugs:
            for bug in connection_bugs[:2]:
                btype = getattr(bug, "bug_type", "") if not isinstance(bug, dict) else bug.get("bug_type", "")
                btarget = getattr(bug, "target_service", "") if not isinstance(bug, dict) else bug.get("target_service", "")
                source_svc = getattr(bug, "source_service", "") if not isinstance(bug, dict) else bug.get("source_service", "")
                caller = source_svc or (impacted_services[0] if impacted_services else "orders-maker-service")
                text = f"Resolve {btype}: Register '{btarget or 'service'}' or configure endpoint proxy in network topology."
                bug_edits = [
                    GraphEdit(action="add_node", from_service=btarget or "service_proxy").model_dump(),
                    GraphEdit(action="add_edge", from_service=caller, to_service=btarget or "service_proxy").model_dump(),
                ]
                results.append({
                    "text": text,
                    "edits": bug_edits
                })

        # 3. Impacted services architecture remediations (circuit breaker / resilience facade)
        impacted = [s for s in (impacted_services or []) if s and s != "unknown"]
        primary_svc = impacted[0] if impacted else "order-service"

        results.append({
            "text": f"Introduce circuit breaker / resilience facade for '{primary_svc}' to isolate downstream failure propagation.",
            "edits": [
                GraphEdit(action="add_node", from_service=f"{primary_svc}_facade").model_dump(),
                GraphEdit(action="add_edge", from_service=f"{primary_svc}_facade", to_service=primary_svc).model_dump(),
            ]
        })

        if risk_score >= 30.0:
            results.append({
                "text": f"Decouple '{primary_svc}' with an asynchronous message queue (e.g. event-bus) to eliminate synchronous blocking.",
                "edits": [
                    GraphEdit(action="add_node", from_service="event_broker").model_dump(),
                    GraphEdit(action="add_edge", from_service=primary_svc, to_service="event_broker").model_dump(),
                ]
            })

        return results