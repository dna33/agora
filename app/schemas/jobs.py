from pydantic import BaseModel


class ClusterJobRequest(BaseModel):
    similarity_threshold: float = 0.88
    min_cluster_size: int = 2


class ClusterJobResponse(BaseModel):
    clusters_created: int
    assignments_created: int
    processed_messages: int
