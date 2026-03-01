from app.db.session import SessionLocal
from app.services.cluster_service import run_clustering_job


if __name__ == "__main__":
    db = SessionLocal()
    try:
        result = run_clustering_job(db, similarity_threshold=0.88, min_cluster_size=2)
        print(
            {
                "clusters_created": result.clusters_created,
                "assignments_created": result.assignments_created,
                "processed_messages": result.processed_messages,
            }
        )
    finally:
        db.close()
