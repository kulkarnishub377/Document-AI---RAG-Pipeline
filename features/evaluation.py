# features/evaluation.py
# ─────────────────────────────────────────────────────────────────────────────
# RAGAS-inspired Evaluation Dashboard
#
# Measures RAG pipeline quality across 4 dimensions:
#   1. Faithfulness    — Is the answer grounded in context?
#   2. Answer Relevancy — Does the answer address the question?
#   3. Context Precision — Are the retrieved chunks relevant?
#   4. Context Recall   — Are all needed chunks retrieved?
#
# Uses the local LLM (Ollama/Mistral) to evaluate each dimension,
# no external API keys required.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import re
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from config import DATA_DIR


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    """Result of a single RAGAS-style evaluation."""
    question: str
    answer: str
    contexts: List[str]
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    overall_score: float = 0.0
    timestamp: str = ""
    eval_time_ms: int = 0


EVAL_HISTORY_PATH = DATA_DIR / "evaluation_history.json"


class RAGASEvaluator:
    """
    Local RAGAS-inspired evaluator using the existing Ollama LLM.
    No external API keys required — everything runs locally.
    """

    def __init__(self):
        self._history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load_history()

    def _load_history(self) -> None:
        """Load evaluation history from disk."""
        if EVAL_HISTORY_PATH.exists():
            try:
                with open(EVAL_HISTORY_PATH, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
                logger.info(f"Loaded {len(self._history)} evaluation records")
            except Exception as e:
                logger.warning(f"Failed to load eval history: {e}")

    def _save_history(self) -> None:
        """Persist evaluation history."""
        with open(EVAL_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(self._history, f, ensure_ascii=False, indent=2)

    def _ask_llm(self, prompt: str) -> str:
        """Query the LLM for evaluation scoring."""
        from llm.prompt_chains import _get_llm
        llm = _get_llm()
        return llm.invoke(prompt).strip()

    def _parse_score(self, response: str) -> float:
        """Extract a 0-1 score from LLM response."""
        # Try to find a decimal number between 0 and 1
        matches = re.findall(r'(?:^|\s)(0\.\d+|1\.0|0|1)(?:\s|$|\.)', response)
        if matches:
            return min(1.0, max(0.0, float(matches[0])))
        # Try to find percentage
        pct = re.findall(r'(\d+)%', response)
        if pct:
            return min(1.0, max(0.0, int(pct[0]) / 100.0))
        # Try to find x/10 or x/5
        frac = re.findall(r'(\d+)\s*/\s*(\d+)', response)
        if frac:
            return min(1.0, max(0.0, int(frac[0][0]) / int(frac[0][1])))
        return 0.5  # Default if parsing fails

    def eval_faithfulness(self, answer: str, contexts: List[str]) -> float:
        """
        Faithfulness: Is every claim in the answer supported by the context?
        Score 0.0 (hallucinated) to 1.0 (fully faithful).
        """
        context_text = "\n---\n".join(contexts[:5])
        prompt = f"""You are an impartial judge evaluating whether an AI answer is faithful to the provided context.

CONTEXT:
{context_text}

ANSWER:
{answer}

Rate the faithfulness from 0.0 to 1.0:
- 1.0 = Every claim is directly supported by the context
- 0.5 = Some claims supported, some not verifiable
- 0.0 = Answer contains claims not in the context (hallucination)

Return ONLY a single decimal number between 0.0 and 1.0. Nothing else.

SCORE:"""
        response = self._ask_llm(prompt)
        return self._parse_score(response)

    def eval_answer_relevancy(self, question: str, answer: str) -> float:
        """
        Answer Relevancy: Does the answer actually address the question?
        Score 0.0 (off-topic) to 1.0 (directly answers).
        """
        prompt = f"""You are evaluating whether an answer is relevant to the question asked.

QUESTION: {question}

ANSWER: {answer}

Rate the relevancy from 0.0 to 1.0:
- 1.0 = Answer directly and completely addresses the question
- 0.5 = Answer partially addresses the question
- 0.0 = Answer is completely off-topic

Return ONLY a single decimal number between 0.0 and 1.0. Nothing else.

SCORE:"""
        response = self._ask_llm(prompt)
        return self._parse_score(response)

    def eval_context_precision(self, question: str, contexts: List[str]) -> float:
        """
        Context Precision: Are the retrieved chunks actually relevant to the question?
        Score 0.0 (irrelevant chunks) to 1.0 (all chunks relevant).
        """
        if not contexts:
            return 0.0

        relevant_count = 0
        for i, ctx in enumerate(contexts[:5]):
            prompt = f"""Is this text chunk relevant to answering the question?

QUESTION: {question}
CHUNK: {ctx[:500]}

Answer YES or NO only."""
            response = self._ask_llm(prompt)
            if "yes" in response.lower():
                relevant_count += 1

        return round(relevant_count / min(len(contexts), 5), 2)

    def eval_context_recall(self, question: str, answer: str, contexts: List[str]) -> float:
        """
        Context Recall: Does the context contain all information needed for the answer?
        Score 0.0 (missing info) to 1.0 (complete context).
        """
        context_text = "\n---\n".join(contexts[:5])
        prompt = f"""Evaluate whether the retrieved context contains all information needed to produce the answer.

QUESTION: {question}
ANSWER: {answer}
CONTEXT:
{context_text}

Rate the context recall from 0.0 to 1.0:
- 1.0 = Context contains everything needed for the answer
- 0.5 = Context contains some but not all necessary information
- 0.0 = Context is missing critical information

Return ONLY a single decimal number between 0.0 and 1.0. Nothing else.

SCORE:"""
        response = self._ask_llm(prompt)
        return self._parse_score(response)

    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        run_all: bool = True,
    ) -> EvalResult:
        """
        Run a full RAGAS-style evaluation on a Q&A interaction.

        Args:
            question: The user's question
            answer: The LLM's answer
            contexts: List of retrieved context chunks
            run_all: If True, run all 4 metrics (slower but complete)

        Returns:
            EvalResult with scores for each dimension
        """
        logger.info(f"Running RAGAS evaluation for: '{question[:60]}...'")
        t0 = time.perf_counter()

        result = EvalResult(
            question=question,
            answer=answer,
            contexts=contexts[:5],
            timestamp=datetime.utcnow().isoformat(),
        )

        try:
            result.faithfulness = self.eval_faithfulness(answer, contexts)
            result.answer_relevancy = self.eval_answer_relevancy(question, answer)

            if run_all:
                result.context_precision = self.eval_context_precision(question, contexts)
                result.context_recall = self.eval_context_recall(question, answer, contexts)

            # Overall score = weighted average
            weights = [0.3, 0.3, 0.2, 0.2]
            scores = [
                result.faithfulness,
                result.answer_relevancy,
                result.context_precision,
                result.context_recall,
            ]
            result.overall_score = round(sum(w * s for w, s in zip(weights, scores)), 3)

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")

        result.eval_time_ms = int((time.perf_counter() - t0) * 1000)

        # Store in history
        with self._lock:
            self._history.append(asdict(result))
            if len(self._history) > 500:
                self._history = self._history[-500:]
            self._save_history()

        logger.info(
            f"Evaluation complete: overall={result.overall_score} "
            f"faith={result.faithfulness} rel={result.answer_relevancy} "
            f"prec={result.context_precision} recall={result.context_recall} "
            f"({result.eval_time_ms}ms)"
        )

        return result

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent evaluation history."""
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics for the dashboard."""
        with self._lock:
            if not self._history:
                return {
                    "total_evaluations": 0,
                    "avg_overall": 0.0,
                    "avg_faithfulness": 0.0,
                    "avg_answer_relevancy": 0.0,
                    "avg_context_precision": 0.0,
                    "avg_context_recall": 0.0,
                    "trend": [],
                }

            n = len(self._history)
            avg = lambda key: round(sum(h.get(key, 0) for h in self._history) / n, 3)

            # Trend: last 20 overall scores
            trend = [
                {"score": h.get("overall_score", 0), "timestamp": h.get("timestamp", "")}
                for h in self._history[-20:]
            ]

            return {
                "total_evaluations": n,
                "avg_overall": avg("overall_score"),
                "avg_faithfulness": avg("faithfulness"),
                "avg_answer_relevancy": avg("answer_relevancy"),
                "avg_context_precision": avg("context_precision"),
                "avg_context_recall": avg("context_recall"),
                "best_score": max(h.get("overall_score", 0) for h in self._history),
                "worst_score": min(h.get("overall_score", 0) for h in self._history),
                "trend": trend,
            }

    def clear_history(self) -> int:
        """Clear evaluation history. Returns count cleared."""
        with self._lock:
            count = len(self._history)
            self._history.clear()
            if EVAL_HISTORY_PATH.exists():
                EVAL_HISTORY_PATH.unlink()
            return count


# Module-level singleton
evaluator = RAGASEvaluator()
