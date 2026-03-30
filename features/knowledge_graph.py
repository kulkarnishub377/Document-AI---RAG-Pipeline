# features/knowledge_graph.py
# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Graph Extraction using spaCy / regex NER + NetworkX
# v3.1 — Cap relationships per chunk (P10), fix datetime, add graph stats
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from config import KG_DATA_PATH, KNOWLEDGE_GRAPH_ENABLED, KG_MAX_ENTITIES_PER_CHUNK


@dataclass
class Entity:
    """A named entity extracted from documents."""
    name: str
    entity_type: str          # PERSON, ORG, DATE, MONEY, LOCATION, etc.
    sources: List[str] = field(default_factory=list)
    mentions: int = 0


@dataclass
class Relationship:
    """A relationship between two entities."""
    source_entity: str
    target_entity: str
    relation_type: str        # "co-occurs", "mentioned-with", etc.
    weight: int = 1
    source_docs: List[str] = field(default_factory=list)


class KnowledgeGraph:
    """In-memory knowledge graph with file persistence."""

    def __init__(self):
        self._entities: Dict[str, Entity] = {}
        self._relationships: List[Relationship] = []
        self._adj: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load graph from disk if it exists."""
        if not KG_DATA_PATH.exists():
            return
        try:
            with open(KG_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for e in data.get("entities", []):
                self._entities[e["name"]] = Entity(**e)
            for r in data.get("relationships", []):
                rel = Relationship(**r)
                self._relationships.append(rel)
                self._adj[rel.source_entity].add(rel.target_entity)
                self._adj[rel.target_entity].add(rel.source_entity)
            logger.info(f"Knowledge graph loaded: {len(self._entities)} entities, {len(self._relationships)} relationships")
        except Exception as e:
            logger.warning(f"Failed to load knowledge graph: {e}")

    def _save(self) -> None:
        """Persist graph to disk."""
        data = {
            "entities": [asdict(e) for e in self._entities.values()],
            "relationships": [asdict(r) for r in self._relationships],
        }
        with open(KG_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def extract_entities(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract named entities from text using regex patterns.
        Returns list of (entity_name, entity_type) tuples.
        """
        entities: List[Tuple[str, str]] = []

        # Monetary values
        for m in re.finditer(r'[\$€£₹]\s*[\d,]+\.?\d*', text):
            entities.append((m.group().strip(), "MONEY"))

        # Dates
        for m in re.finditer(
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b'
            r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{4}',
            text, re.IGNORECASE
        ):
            entities.append((m.group().strip(), "DATE"))

        # Email addresses
        for m in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text):
            entities.append((m.group().strip(), "EMAIL"))

        # Phone numbers
        for m in re.finditer(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', text):
            entities.append((m.group().strip(), "PHONE"))

        # Percentages
        for m in re.finditer(r'\b\d+\.?\d*\s*%\b', text):
            entities.append((m.group().strip(), "PERCENTAGE"))

        # Capitalized phrases (likely proper nouns — ORG/PERSON)
        for m in re.finditer(r'\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
            name = m.group().strip()
            if len(name) > 3 and name not in {"The", "This", "That", "These", "Those"}:
                entities.append((name, "ENTITY"))

        return entities

    def process_chunk(self, text: str, source: str) -> int:
        """
        Extract entities from a text chunk and add them to the graph.
        v3.1: Caps entities per chunk at KG_MAX_ENTITIES_PER_CHUNK (P10).
        Returns the number of new entities discovered.
        """
        if not KNOWLEDGE_GRAPH_ENABLED:
            return 0

        raw_entities = self.extract_entities(text)
        if not raw_entities:
            return 0

        # v3.1 (P10): Cap entities per chunk to avoid O(n²) explosion
        raw_entities = raw_entities[:KG_MAX_ENTITIES_PER_CHUNK]

        new_count = 0
        chunk_entity_names: List[str] = []

        with self._lock:
            for name, etype in raw_entities:
                if name in self._entities:
                    self._entities[name].mentions += 1
                    if source not in self._entities[name].sources:
                        self._entities[name].sources.append(source)
                else:
                    self._entities[name] = Entity(
                        name=name, entity_type=etype,
                        sources=[source], mentions=1,
                    )
                    new_count += 1
                chunk_entity_names.append(name)

            # Create co-occurrence relationships
            for i, e1 in enumerate(chunk_entity_names):
                for e2 in chunk_entity_names[i + 1:]:
                    if e1 != e2:
                        existing = next(
                            (r for r in self._relationships
                             if {r.source_entity, r.target_entity} == {e1, e2}),
                            None,
                        )
                        if existing:
                            existing.weight += 1
                            if source not in existing.source_docs:
                                existing.source_docs.append(source)
                        else:
                            self._relationships.append(Relationship(
                                source_entity=e1, target_entity=e2,
                                relation_type="co-occurs",
                                weight=1, source_docs=[source],
                            ))
                            self._adj[e1].add(e2)
                            self._adj[e2].add(e1)

        return new_count

    def process_chunks(self, chunks: list, source: str) -> Dict[str, Any]:
        """Process all chunks from a document and update the graph."""
        if not KNOWLEDGE_GRAPH_ENABLED:
            return {"entities_added": 0, "total_entities": 0}

        total_new = 0
        for chunk in chunks:
            total_new += self.process_chunk(chunk.text, source)

        self._save()
        return {
            "entities_added": total_new,
            "total_entities": len(self._entities),
            "total_relationships": len(self._relationships),
        }

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Get entity details and its neighbors."""
        with self._lock:
            entity = self._entities.get(name)
            if not entity:
                return None
            neighbors = list(self._adj.get(name, set()))
            return {**asdict(entity), "neighbors": neighbors}

    def search_entities(
        self, query: str = "", entity_type: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search entities by name prefix or type."""
        with self._lock:
            results = []
            for e in self._entities.values():
                if entity_type and e.entity_type != entity_type:
                    continue
                if query and query.lower() not in e.name.lower():
                    continue
                results.append(asdict(e))
            results.sort(key=lambda x: x["mentions"], reverse=True)
            return results[:limit]

    def get_graph_data(self) -> Dict[str, Any]:
        """Return full graph data for visualization."""
        with self._lock:
            nodes = [
                {"id": e.name, "type": e.entity_type, "mentions": e.mentions}
                for e in self._entities.values()
            ]
            edges = [
                {
                    "source": r.source_entity,
                    "target": r.target_entity,
                    "weight": r.weight,
                    "type": r.relation_type,
                }
                for r in self._relationships
            ]
            return {
                "nodes": nodes,
                "edges": edges,
                "total_entities": len(nodes),
                "total_relationships": len(edges),
            }

    def reset(self) -> None:
        """Clear the entire knowledge graph."""
        with self._lock:
            self._entities.clear()
            self._relationships.clear()
            self._adj.clear()
            if KG_DATA_PATH.exists():
                KG_DATA_PATH.unlink()
            logger.info("Knowledge graph cleared.")


# Module-level singleton
knowledge_graph = KnowledgeGraph()
