def job_to_public(job: dict) -> dict:
    has_result = job["status"] == "done" and bool(job.get("result_path"))
    return {
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "stats": job["stats"],
        "params": job["params"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "result_url": f"/api/jobs/{job['id']}/result" if has_result else None,
    }
