"""Quick test to debug init endpoint."""
import asyncio
import sys

async def main():
    from app.config import get_settings
    from app.models import init_db, get_db
    from app.core.task_coordinator import TaskCoordinator
    from app.core.risk_scorer import RiskScorer
    from app.utils.redis_client import init_redis, get_redis
    import uuid
    
    settings = get_settings()
    print(f"Settings loaded. Database: {settings.database_url}")
    
    # Initialize
    await init_db()
    print("Database initialized")
    
    await init_redis()
    print("Redis initialized")
    
    # Get DB session
    async for db in get_db():
        try:
            redis = await get_redis()
            print("Got Redis connection")
            
            risk_scorer = RiskScorer(redis)
            task_coordinator = TaskCoordinator(db, redis)
            print("Created services")
            
            # Test risk score
            risk_score = await risk_scorer.compute_risk_score(
                client_ip="127.0.0.1",
                user_agent="Test",
                site_key="pk_test"
            )
            print(f"Risk score: {risk_score}")
            
            # Test difficulty
            difficulty = task_coordinator.get_difficulty_tier(risk_score)
            print(f"Difficulty: {difficulty}")
            
            # Test task assignment
            session_id = uuid.uuid4()
            print(f"Testing task assignment for session: {session_id}")
            
            task, sample, shard_task = await task_coordinator.assign_task(
                session_id=session_id,
                difficulty=difficulty
            )
            print(f"Task assigned: {task.id}")
            print(f"Run assigned: {shard_task.run_id}")
            print(f"Sample: {sample.id}")
            print(f"Sample data_url: {sample.data_url}")
            print(f"Sample data_type: {sample.data_type}")
            
            await db.commit()
            print("SUCCESS!")
            
        except Exception as e:
            import traceback
            print(f"ERROR: {e}")
            traceback.print_exc()
        break

if __name__ == "__main__":
    asyncio.run(main())
