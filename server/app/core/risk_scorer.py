"""
Risk Scorer for computing client risk scores.
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from redis.asyncio import Redis

from app.config import get_settings
from app.utils.security import key_prefix

logger = logging.getLogger(__name__)
settings = get_settings()


class RiskScorer:
    """
    Computes risk scores for CAPTCHA sessions.

    Risk factors:
    - Request frequency (requests per minute)
    - Session velocity (how fast sessions complete)
    - Behavioral signals (patterns in timing)
    - Reputation history (past verification accuracy)
    - Known sample accuracy (performance on honeypots)

    Higher risk score = more suspicious = harder tasks.
    """

    # Risk factor weights
    RISK_WEIGHTS = {
        "request_frequency": 0.24,
        "session_velocity": 0.18,
        "behavioral_signals": 0.18,
        "proof_failures": 0.20,
        "reputation_history": 0.10,
        "known_sample_accuracy": 0.10,
    }

    # Thresholds
    HIGH_FREQUENCY_THRESHOLD = 10  # requests per minute
    FAST_VELOCITY_THRESHOLD = 200  # ms (suspiciously fast)

    def __init__(self, redis: Redis):
        self.redis = redis

    async def compute_risk_score(
        self,
        client_ip: str,
        user_agent: str,
        site_key: str,
        fingerprint: Optional[str] = None,
    ) -> float:
        """
        Compute risk score for a client.

        Args:
            client_ip: Client IP address
            user_agent: Browser user agent
            site_key: Site API key
            fingerprint: Optional client fingerprint

        Returns:
            Risk score between 0.0 (low risk) and 1.0 (high risk)
        """
        # Generate anonymous client identifier
        client_id = self.generate_client_id(client_ip, user_agent)

        # Compute individual risk factors
        frequency_risk = await self._compute_frequency_risk(client_id)
        velocity_risk = await self._compute_velocity_risk(client_id)
        behavioral_risk = await self._compute_behavioral_risk(client_id, user_agent)
        proof_failure_risk = await self._compute_proof_failure_risk(client_id, site_key)
        reputation_risk = await self._compute_reputation_risk(fingerprint)
        known_sample_risk = await self._compute_known_sample_risk(fingerprint)

        # Weighted combination
        risk_score = (
            self.RISK_WEIGHTS["request_frequency"] * frequency_risk
            + self.RISK_WEIGHTS["session_velocity"] * velocity_risk
            + self.RISK_WEIGHTS["behavioral_signals"] * behavioral_risk
            + self.RISK_WEIGHTS["proof_failures"] * proof_failure_risk
            + self.RISK_WEIGHTS["reputation_history"] * reputation_risk
            + self.RISK_WEIGHTS["known_sample_accuracy"] * known_sample_risk
        )

        # Clamp to [0, 1]
        risk_score = max(0.0, min(1.0, risk_score))

        # Record this request
        await self._record_request(client_id)

        logger.debug(
            f"Risk score for {client_id[:8]}...: {risk_score:.2f} "
            f"(freq={frequency_risk:.2f}, vel={velocity_risk:.2f}, "
            f"beh={behavioral_risk:.2f}, fail={proof_failure_risk:.2f}, "
            f"rep={reputation_risk:.2f}, "
            f"known={known_sample_risk:.2f})"
        )

        return risk_score

    def generate_client_id(self, client_ip: str, user_agent: str) -> str:
        """Generate anonymous client identifier."""
        # Hash IP and user agent for privacy
        data = f"{client_ip}:{user_agent}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    async def _compute_frequency_risk(self, client_id: str) -> float:
        """
        Compute risk based on request frequency.

        High request rates indicate potential bot activity.
        """
        key = f"rate:{client_id}"

        # Get request count in last minute
        count = await self.redis.get(key)
        request_count = int(count) if count else 0

        if request_count <= 1:
            return 0.0
        elif request_count <= self.HIGH_FREQUENCY_THRESHOLD:
            # Linear scaling
            return request_count / self.HIGH_FREQUENCY_THRESHOLD
        else:
            # Above threshold = maximum risk
            return 1.0

    async def _compute_velocity_risk(self, client_id: str) -> float:
        """
        Compute risk based on session completion velocity.

        Suspiciously fast completions indicate automation.
        """
        key = f"velocity:{client_id}"

        # Get average completion time
        avg_time = await self.redis.get(key)

        if not avg_time:
            return 0.0

        avg_ms = float(avg_time)

        if avg_ms >= settings.normal_difficulty_time_ms:
            return 0.0
        elif avg_ms >= self.FAST_VELOCITY_THRESHOLD:
            # Linear scaling between fast threshold and normal
            range_ms = settings.normal_difficulty_time_ms - self.FAST_VELOCITY_THRESHOLD
            return 1.0 - (avg_ms - self.FAST_VELOCITY_THRESHOLD) / range_ms
        else:
            # Suspiciously fast
            return 1.0

    async def _compute_behavioral_risk(
        self, client_id: str, user_agent: str
    ) -> float:
        """
        Compute risk based on behavioral signals.

        Checks for common bot indicators in user agent and patterns.
        """
        risk = 0.0

        # Check for headless browser indicators
        headless_indicators = [
            "HeadlessChrome",
            "PhantomJS",
            "Selenium",
            "webdriver",
            "puppeteer",
        ]

        user_agent_lower = user_agent.lower()
        for indicator in headless_indicators:
            if indicator.lower() in user_agent_lower:
                risk += 0.5

        # Check for missing or suspicious user agents
        if not user_agent or len(user_agent) < 20:
            risk += 0.3

        return min(1.0, risk)

    async def _compute_proof_failure_risk(self, client_id: str, site_key: str) -> float:
        """
        Compute risk from recent invalid proofs and validation failures.

        Failed projection checks, replay attempts, and repeated invalid submits
        are among the clearest automation signals this system can observe.
        """
        client_failures = await self.redis.get(f"proof_fail:{client_id}")
        site_hash = hashlib.sha256(key_prefix(site_key).encode("utf-8")).hexdigest()[:16]
        site_failures = await self.redis.get(f"site_fail:{site_hash}")

        client_count = int(client_failures) if client_failures else 0
        site_count = int(site_failures) if site_failures else 0

        client_risk = min(1.0, client_count / 5)
        site_risk = min(1.0, site_count / 50)
        return max(client_risk, site_risk * 0.5)

    async def _compute_reputation_risk(self, fingerprint: Optional[str]) -> float:
        """
        Compute risk based on reputation history.

        Lower reputation = higher risk.
        """
        if not fingerprint:
            return 0.3  # Default risk for unknown users

        key = f"reputation:{fingerprint}"
        reputation = await self.redis.get(key)

        if not reputation:
            return 0.3

        # Reputation is 0-5, invert for risk
        rep_score = float(reputation)
        return max(0.0, 1.0 - (rep_score / 5.0))

    async def _compute_known_sample_risk(self, fingerprint: Optional[str]) -> float:
        """
        Compute risk based on known sample accuracy.

        Poor performance on honeypots indicates potential manipulation.
        """
        if not fingerprint:
            return 0.0

        key = f"known_accuracy:{fingerprint}"
        accuracy = await self.redis.get(key)

        if not accuracy:
            return 0.0

        # Lower accuracy = higher risk
        acc_score = float(accuracy)
        return max(0.0, 1.0 - acc_score)

    async def _record_request(self, client_id: str) -> None:
        """Record a request for rate limiting."""
        key = f"rate:{client_id}"

        # Increment counter with 60-second expiry
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        await pipe.execute()

    async def record_completion(
        self, client_id: str, completion_time_ms: int
    ) -> None:
        """Record session completion time for velocity tracking."""
        key = f"velocity:{client_id}"

        # Update exponential moving average
        current = await self.redis.get(key)
        if current:
            # EMA with alpha = 0.3
            current_avg = float(current)
            new_avg = 0.3 * completion_time_ms + 0.7 * current_avg
        else:
            new_avg = completion_time_ms

        await self.redis.setex(key, 3600, str(new_avg))  # 1 hour expiry

    async def record_proof_outcome(
        self,
        *,
        client_id: Optional[str],
        site_key_prefix: Optional[str],
        valid: bool,
        reason: str = "ok",
        completion_time_ms: Optional[int] = None,
    ) -> None:
        """Record proof outcome for adaptive difficulty and abuse analytics."""
        if not client_id:
            return

        pipe = self.redis.pipeline()
        if valid:
            pipe.delete(f"proof_fail:{client_id}")
        else:
            pipe.incr(f"proof_fail:{client_id}")
            pipe.expire(f"proof_fail:{client_id}", 3600)
            if site_key_prefix:
                site_hash = hashlib.sha256(site_key_prefix.encode("utf-8")).hexdigest()[:16]
                pipe.incr(f"site_fail:{site_hash}")
                pipe.expire(f"site_fail:{site_hash}", 3600)
            pipe.setex(f"proof_fail_reason:{client_id}", 3600, reason[:200])

        await pipe.execute()

        if completion_time_ms is not None:
            await self.record_completion(client_id, completion_time_ms)
