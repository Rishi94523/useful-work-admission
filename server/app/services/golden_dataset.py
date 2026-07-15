"""
Golden Dataset Service for managing verified labels.
"""

import logging
import uuid
from collections import Counter
from typing import Optional, List, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Verification, GoldenDataset, Sample, Session

logger = logging.getLogger(__name__)
settings = get_settings()


class GoldenDatasetService:
    """
    Manages the golden dataset of verified labels.

    Responsibilities:
    - Process verifications
    - Calculate consensus
    - Promote samples to golden dataset
    - Export dataset for ML training
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_verification(
        self,
        sample_id: uuid.UUID,
        verified_label: str,
        reputation_score: float,
        domain: str,
    ) -> Optional[GoldenDataset]:
        """
        Process a verification and update golden dataset if consensus reached.

        Args:
            sample_id: Sample UUID
            verified_label: The verified label
            reputation_score: User's reputation score
            domain: Contributing domain

        Returns:
            GoldenDataset entry if promoted, None otherwise
        """
        # Get all verifications for this sample
        verifications = await self._get_sample_verifications(sample_id)

        if len(verifications) < settings.min_verifications_for_consensus:
            logger.debug(
                f"Sample {sample_id} has {len(verifications)} verifications, "
                f"need {settings.min_verifications_for_consensus}"
            )
            return None

        # Calculate consensus
        consensus = self._calculate_consensus(verifications)

        if (
            consensus["weighted_agreement"] >= settings.consensus_threshold
            and consensus["agreement"] >= settings.discard_threshold
        ):
            # Promote to golden dataset
            return await self._promote_to_golden(
                sample_id=sample_id,
                label=consensus["label"],
                consensus=consensus,
                domain=domain,
            )
        elif consensus["agreement"] < settings.discard_threshold:
            # Discard - too much disagreement
            logger.info(
                f"Discarding sample {sample_id}: agreement={consensus['agreement']:.2f}"
            )
            # TODO: Mark sample as discarded
            return None
        else:
            # Need more verifications
            logger.debug(
                f"Sample {sample_id} needs more verifications: "
                f"agreement={consensus['agreement']:.2f}"
            )
            return None

    async def _get_sample_verifications(
        self, sample_id: uuid.UUID
    ) -> List[Verification]:
        """Get all verifications for a sample."""
        result = await self.db.execute(
            select(Verification, Session.client_fingerprint)
            .join(Session, Verification.session_id == Session.id)
            .where(Verification.sample_id == sample_id)
            .order_by(Verification.created_at.desc())
        )

        # Count at most one (latest) vote per anonymous browser identity.
        # This blocks accidental/repeated voting but is not a substitute for
        # production-grade Sybil resistance.
        seen = set()
        distinct = []
        for verification, fingerprint in result.all():
            identity = fingerprint or str(verification.session_id)
            if identity in seen:
                continue
            seen.add(identity)
            distinct.append(verification)
        return distinct

    def _calculate_consensus(
        self, verifications: List[Verification]
    ) -> Dict:
        """
        Calculate consensus from verifications.

        Uses reputation-weighted voting.
        """
        # Count labels with reputation weighting
        weighted_votes: Dict[str, float] = {}
        total_weight = 0.0

        for v in verifications:
            label = v.verified_label or v.original_label
            weight = (
                v.reputation_score
                if v.reputation_score is not None
                else settings.initial_reputation
            )

            weighted_votes[label] = weighted_votes.get(label, 0) + weight
            total_weight += weight

        if total_weight == 0:
            return {"label": None, "agreement": 0.0, "weighted_agreement": 0.0}

        # Find majority label
        top_label = max(weighted_votes, key=lambda k: weighted_votes[k])
        weighted_agreement = weighted_votes[top_label] / total_weight

        # Calculate unweighted agreement for comparison
        label_counts = Counter(
            v.verified_label or v.original_label for v in verifications
        )
        agreement = label_counts[top_label] / len(verifications)

        return {
            "label": top_label,
            "agreement": agreement,
            "weighted_agreement": weighted_agreement,
            "verification_count": len(verifications),
            "vote_distribution": dict(label_counts),
        }

    async def _promote_to_golden(
        self,
        sample_id: uuid.UUID,
        label: str,
        consensus: Dict,
        domain: str,
    ) -> GoldenDataset:
        """Promote a sample to the golden dataset."""
        # Check if already in golden dataset
        existing = await self.db.execute(
            select(GoldenDataset).where(GoldenDataset.sample_id == sample_id)
        )
        existing_entry = existing.scalar_one_or_none()

        if existing_entry:
            # Update existing entry
            existing_entry.verified_label = label
            existing_entry.confidence_score = consensus["weighted_agreement"]
            existing_entry.verification_count = consensus["verification_count"]
            existing_entry.agreement_score = consensus["agreement"]
            existing_entry.weighted_agreement = consensus["weighted_agreement"]

            logger.info(f"Updated golden dataset entry: {sample_id}")
            return existing_entry

        # Get sample info
        sample = await self.db.execute(
            select(Sample).where(Sample.id == sample_id)
        )
        sample_obj = sample.scalar_one_or_none()

        if not sample_obj:
            raise ValueError(f"Sample not found: {sample_id}")

        # Create new entry
        golden = GoldenDataset(
            sample_id=sample_id,
            data_type=sample_obj.data_type,
            verified_label=label,
            confidence_score=consensus["weighted_agreement"],
            verification_count=consensus["verification_count"],
            agreement_score=consensus["agreement"],
            weighted_agreement=consensus["weighted_agreement"],
            domain_attribution=domain,
        )

        self.db.add(golden)

        logger.info(
            f"Promoted to golden dataset: {sample_id} -> {label} "
            f"(agreement={consensus['agreement']:.2f})"
        )

        return golden

    async def get_statistics(self) -> Dict:
        """Get golden dataset statistics."""
        # Count by label
        result = await self.db.execute(
            select(
                GoldenDataset.verified_label,
                func.count(GoldenDataset.id).label("count"),
                func.avg(GoldenDataset.agreement_score).label("avg_agreement"),
            ).group_by(GoldenDataset.verified_label)
        )

        label_stats = {
            row.verified_label: {
                "count": row.count,
                "avg_agreement": float(row.avg_agreement) if row.avg_agreement else 0,
            }
            for row in result
        }

        # Total count
        total_result = await self.db.execute(
            select(func.count(GoldenDataset.id))
        )
        total = total_result.scalar()

        return {
            "total_samples": total,
            "by_label": label_stats,
        }

    async def export_dataset(
        self,
        data_type: Optional[str] = None,
        min_agreement: float = 0.8,
        limit: int = 10000,
    ) -> List[Dict]:
        """
        Export golden dataset for ML training.

        Args:
            data_type: Filter by data type
            min_agreement: Minimum agreement score
            limit: Maximum number of samples

        Returns:
            List of dataset entries
        """
        query = select(GoldenDataset, Sample).join(
            Sample, GoldenDataset.sample_id == Sample.id
        ).where(
            GoldenDataset.agreement_score >= min_agreement
        )

        if data_type:
            query = query.where(GoldenDataset.data_type == data_type)

        query = query.limit(limit)

        result = await self.db.execute(query)

        return [
            {
                "sample_id": str(golden.sample_id),
                "label": golden.verified_label,
                "confidence": golden.confidence_score,
                "agreement": golden.agreement_score,
                "data_type": golden.data_type,
                "data_url": sample.data_url,
            }
            for golden, sample in result
        ]
