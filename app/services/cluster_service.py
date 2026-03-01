import math
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AnalysisCluster, AnalysisVersion, Message, MessageClusterAssignment
from app.schemas.jobs import ClusterJobResponse


class _MutableCluster:
    def __init__(self, message_id: str, embedding: list[float], topic: str, future: str) -> None:
        self.message_ids = [message_id]
        self.centroid = embedding[:]
        self.topics = [topic]
        self.futures = [future]
        self.similarities: dict[str, float] = {message_id: 1.0}

    def add(self, message_id: str, embedding: list[float], similarity: float, topic: str, future: str) -> None:
        n = len(self.message_ids)
        self.centroid = [((self.centroid[i] * n) + embedding[i]) / (n + 1) for i in range(len(embedding))]
        self.message_ids.append(message_id)
        self.topics.append(topic)
        self.futures.append(future)
        self.similarities[message_id] = similarity


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _cluster_label(topics: list[str], futures: list[str]) -> str:
    topic = Counter(topics).most_common(1)[0][0]
    future = Counter(futures).most_common(1)[0][0]
    return f"{topic}::{future}"


def run_clustering_job(db: Session, similarity_threshold: float, min_cluster_size: int) -> ClusterJobResponse:
    if similarity_threshold <= 0 or similarity_threshold > 1:
        similarity_threshold = 0.88
    if min_cluster_size < 2:
        min_cluster_size = 2

    latest_versions = db.execute(
        select(AnalysisVersion)
        .order_by(AnalysisVersion.message_id.asc(), AnalysisVersion.version.desc())
    ).scalars().all()

    latest_by_message: dict[str, AnalysisVersion] = {}
    for version in latest_versions:
        if version.message_id not in latest_by_message:
            latest_by_message[version.message_id] = version

    messages = db.execute(select(Message).where(Message.embedding.is_not(None))).scalars().all()

    mutable_clusters: list[_MutableCluster] = []
    for message in messages:
        if not message.embedding:
            continue

        analysis = latest_by_message.get(message.id)
        topic = analysis.primary_topic if analysis else "other"
        future = analysis.desired_future if analysis else "other"

        best_idx = -1
        best_similarity = -1.0
        for idx, cluster in enumerate(mutable_clusters):
            sim = _cosine_similarity(message.embedding, cluster.centroid)
            if sim > best_similarity:
                best_similarity = sim
                best_idx = idx

        if best_similarity >= similarity_threshold and best_idx >= 0:
            mutable_clusters[best_idx].add(message.id, message.embedding, best_similarity, topic, future)
        else:
            mutable_clusters.append(_MutableCluster(message.id, message.embedding, topic, future))

    valid_clusters = [c for c in mutable_clusters if len(c.message_ids) >= min_cluster_size]

    db.execute(delete(MessageClusterAssignment))
    db.execute(delete(AnalysisCluster))

    assignments = 0
    for cluster in valid_clusters:
        cluster_row = AnalysisCluster(
            label=_cluster_label(cluster.topics, cluster.futures),
            centroid_embedding=cluster.centroid,
            size=len(cluster.message_ids),
            algorithm_version="v1-cosine-greedy",
        )
        db.add(cluster_row)
        db.flush()

        for message_id in cluster.message_ids:
            db.add(
                MessageClusterAssignment(
                    message_id=message_id,
                    cluster_id=cluster_row.id,
                    similarity_score=cluster.similarities.get(message_id, 0.0),
                )
            )
            assignments += 1

    db.commit()

    return ClusterJobResponse(
        clusters_created=len(valid_clusters),
        assignments_created=assignments,
        processed_messages=len(messages),
    )
